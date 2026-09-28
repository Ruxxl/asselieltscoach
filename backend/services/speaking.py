"""Speaking Practice: пошаговый диалог с ИИ-экзаменатором (не live-аудио стрим).

Каждый ход ученика — один аудио-клип, отправленный ОДНИМ мультимодальным запросом в Gemini
(тот же паттерн, что и reading-check в backend/services/gemini.py): модель расшифровывает речь,
отвечает как экзаменатор и решает, закончена ли часть. Ответ озвучивается отдельно
(backend/services/tts.py). Live-версия на LiveKit + Deepgram + Groq была заменена этим на пилот:
дешевле (один бесплатный Render-сервис вместо двух) и нечему рваться посреди звонка.
"""

import json
import re

import google.generativeai as genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL


class GeminiNotConfigured(RuntimeError):
    pass


_PART_GUIDANCE = {
    "part1": (
        "This is IELTS Speaking Part 1 (Introduction and Interview) practice. After the student names a "
        "topic they'd like to discuss, ask 3-4 short, simple, everyday questions about it, one at a time. "
        "(Fallback only — normally the topic and opening question are already chosen for Part 1.)"
    ),
    "part2": (
        "This is IELTS Speaking Part 2 (Individual Long Turn) practice. After the student names a topic, "
        "give them a short cue-card style prompt on it (the topic plus 2-3 points to cover) and ask them "
        "to speak for about 1-2 minutes. After their long turn, ask one or two brief natural follow-ups."
    ),
    "part3": (
        "This is IELTS Speaking Part 3 (Two-way Discussion) practice. After the student names a topic, ask "
        "3-4 deeper, more abstract discussion questions related to it — opinions, comparisons, speculation."
    ),
}


def build_examiner_instructions(part: str, topic_question: str | None = None) -> str:
    if part == "part1" and topic_question:
        guidance = (
            f'This is IELTS Speaking Part 1 (Introduction and Interview) practice. The topic and opening '
            f'question are already chosen: "{topic_question}" — ask exactly this question first, then ask '
            f"2-3 more short, simple, everyday follow-up questions on the same topic, one at a time."
        )
    else:
        guidance = _PART_GUIDANCE.get(part, _PART_GUIDANCE["part1"])
    return f"""You are Assel, a friendly but professional IELTS Speaking examiner having a turn-by-turn voice \
conversation with a student, one topic at a time. Your replies are read aloud by text-to-speech. {guidance}

Rules:
- Speak only in English, in plain spoken sentences — no lists, markdown, emoji or stage directions.
- Say or ask ONE thing at a time, and keep your own turns short (1-3 sentences) — you are the examiner, not \
the one being tested.
- This is practice with a coach: when the student's answer has a mistake (grammar, wrong word, unnatural \
phrase) or they ask how to say something, start your reply with ONE short, kind correction of the most \
important issue (e.g. "Small tip: we say 'I live with my parents', not 'I live with my parents together'."), \
then continue with your next question. No long grammar lectures; skip the tip when the answer was fine.
- After a reasonable number of exchanges for this part (roughly 4-5 turns, or the long turn plus follow-ups \
for Part 2), wrap up with one short, friendly closing line thanking the student for practicing.
"""


def _history_to_text(history: list[dict]) -> str:
    return "\n".join(f"{'Student' if t['speaker'] == 'user' else 'Examiner'}: {t['text']}" for t in history)


def _model(system_instruction: str | None = None):
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY не задан в .env. Получить бесплатный ключ: https://aistudio.google.com/apikey"
        )
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(GEMINI_MODEL, system_instruction=system_instruction)


# Вопрос отдельным полем — фронтенд выделяет его жирным в карточке и заводит на него
# карточку Q1/Q2... с подсказкой и примером ответа (как у экзаменаторских тренажёров).
_QUESTION_FIELD_RULE = (
    'Also copy the question you are asking the student, word for word from your reply, into "question" '
    '(empty string if your reply asks no question, e.g. the closing line).'
)


def _question_in(reply: str, question: str | None) -> str:
    # Возвращаем вопрос ровно так, как он стоит в реплике — фронтенд ищет его там, чтобы
    # выделить жирным. Модель иногда меняет регистр/обрезает "Now, ..." — ищем без учёта
    # регистра, а если не нашли, берём последнее предложение реплики со знаком вопроса.
    question = (question or "").strip()
    if question:
        at = reply.lower().find(question.lower())
        if at >= 0:
            return reply[at : at + len(question)]
    asked = re.findall(r"[^.!?]*\?", reply)
    return asked[-1].strip() if asked else ""


def _correction(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    better, tip = str(raw.get("better") or "").strip(), str(raw.get("tip") or "").strip()
    return {"better": better, "tip": tip} if better else None


async def start_conversation(part: str, topic_question: str | None = None) -> dict:
    """Первая реплика экзаменатора — до того, как ученик вообще что-то сказал -> {ai_message, question}."""
    model = _model(build_examiner_instructions(part, topic_question))
    opening = (
        f'Greet the student in one short friendly sentence, then ask exactly this question: "{topic_question}"'
        if topic_question
        else "Greet the student in one short friendly sentence and ask what topic they'd like to talk about today."
    )
    response = await model.generate_content_async(
        f"({opening} {_QUESTION_FIELD_RULE} "
        f'Respond STRICTLY as JSON, no markdown: {{"examiner_reply": "...", "question": "..."}})',

        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 25},
    )
    data = json.loads(response.text.strip())
    reply = data.get("examiner_reply") or (
        f"Hi! Let's start. {topic_question}" if topic_question else "Hi! What would you like to talk about today?"
    )
    return {"ai_message": reply, "question": _question_in(reply, data.get("question"))}


async def continue_conversation(
    part: str, topic_question: str | None, history: list[dict], audio_bytes: bytes, mime_type: str
) -> dict:
    """Один ход: аудио-ответ ученика -> {student_said, ai_message, question, finished}."""
    model = _model(build_examiner_instructions(part, topic_question))
    prompt = f"""Conversation so far:
{_history_to_text(history)}

The attached audio is the student's spoken answer to your last message. Listen to it, then:
1. Transcribe what the student said, in English. If the audio is silent or unintelligible, say so honestly \
instead of guessing, and in your reply kindly ask them to repeat.
2. Give your next reply as the examiner (see your instructions — help with any clear word/phrase gaps, then \
continue naturally).
3. If the student's answer had mistakes or unnatural phrasing, fill "correction": "better" = their answer \
rewritten the way a fluent speaker would say it (keep their ideas), "tip" = one short sentence in Russian \
explaining the main fix. If the answer was fine (or silent/unintelligible), set "correction" to null.
4. Decide whether this part of the practice should now finish (your reply is then the closing line).
5. {_QUESTION_FIELD_RULE}

Respond STRICTLY as JSON, no markdown:
{{"student_said": "...", "correction": {{"better": "...", "tip": "..."}} or null, "examiner_reply": "...", \
"question": "...", "finished": true/false}}
"""
    response = await model.generate_content_async(
        [{"mime_type": mime_type, "data": audio_bytes}, prompt],
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 25},
    )
    data = json.loads(response.text.strip())
    reply = data.get("examiner_reply", "")
    return {
        "student_said": data.get("student_said", ""),
        "ai_message": reply,
        "question": _question_in(reply, data.get("question")),
        "correction": _correction(data.get("correction")),
        "finished": bool(data.get("finished", False)),
    }


_PART_LABELS = {
    "part1": "Part 1 (Introduction and Interview)",
    "part2": "Part 2 (Individual Long Turn)",
    "part3": "Part 3 (Two-way Discussion)",
}

_SCORE_PROMPT_TEMPLATE = """You are an IELTS Speaking examiner writing an official-style band score report.
Below is the transcript of a Speaking Practice session for {part_desc}.

Transcript (each line is one turn, "Student" or "Examiner"):
{transcript_text}

If the transcript is empty or far too short to judge (e.g. the student barely said anything), do NOT invent \
a score — return 0 for every criterion and overall_band, and an honest summary_feedback (in Russian) \
explaining there wasn't enough speech to assess, and inviting the student to try again and speak more.

Otherwise, score the STUDENT's speech only (ignore the examiner's lines) on the 4 official IELTS Speaking \
criteria, each on a 0-9 scale in 0.5 steps:
- fluency_coherence: Fluency and Coherence
- lexical_resource: Lexical Resource
- grammar_accuracy: Grammar Range and Accuracy
- pronunciation: Pronunciation — you only have a TEXT transcript, not audio, so estimate this cautiously \
from indirect signs (self-corrections, filler words, broken sentences as transcribed) rather than true \
acoustic pronunciation; do not overstate confidence in this one criterion.

overall_band = average of the 4 criteria, rounded to the nearest 0.5 (standard IELTS rounding).
summary_feedback: 3-5 sentences in Russian, friendly and constructive — what went well and what to improve, \
with concrete examples from the transcript where possible.
tips: 3-5 concrete, actionable pieces of advice in Russian for raising the band next time, each tied to \
something the student actually said (quote it and give a better English variant).

Respond STRICTLY as JSON, no markdown wrapper:
{{"fluency_coherence": 0-9, "lexical_resource": 0-9, "grammar_accuracy": 0-9, "pronunciation": 0-9, \
"overall_band": 0-9, "summary_feedback": "...", "tips": ["...", "..."]}}
"""


async def score_session(history: list[dict], part: str) -> dict:
    model = _model()
    prompt = _SCORE_PROMPT_TEMPLATE.format(
        part_desc=_PART_LABELS.get(part, part),
        transcript_text=_history_to_text(history) or "(пусто — студент ничего не сказал)",
    )
    response = await model.generate_content_async(
        prompt,
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 25},
    )
    data = json.loads(response.text.strip())
    return {
        "fluency_coherence": float(data.get("fluency_coherence", 0)),
        "lexical_resource": float(data.get("lexical_resource", 0)),
        "grammar_accuracy": float(data.get("grammar_accuracy", 0)),
        "pronunciation": float(data.get("pronunciation", 0)),
        "overall_band": float(data.get("overall_band", 0)),
        "summary_feedback": data.get("summary_feedback", ""),
        "tips": [str(t) for t in data.get("tips", []) if t],
    }


_CORRECTED_REPORT_PROMPT_TEMPLATE = """You are an IELTS Speaking examiner reviewing a Part 1 practice session.
Topic question asked: "{topic_question}"

Transcript (each line is one turn, "Student" or "Examiner"):
{transcript_text}

Take ONLY the student's spoken answers (ignore the examiner's lines) and:
1. Rewrite them as a single polished, natural-sounding corrected version in English — keep the student's own \
ideas and level of detail, just fix grammar/word choice/coherence. If the transcript is empty or far too \
short to judge, return an empty string here.
2. List 3-5 concrete, specific improvement comments in Russian — short and actionable, each referencing \
something the student actually said. If there isn't enough material, say so honestly in one comment inviting \
them to try again and speak more.

Respond STRICTLY as JSON, no markdown wrapper:
{{"corrected_answer": "...", "improvement_comments": ["...", "..."]}}
"""


async def build_corrected_report(history: list[dict], topic_question: str | None = None) -> dict:
    model = _model()
    prompt = _CORRECTED_REPORT_PROMPT_TEMPLATE.format(
        topic_question=topic_question or "(не указан)",
        transcript_text=_history_to_text(history) or "(пусто — студент ничего не сказал)",
    )
    response = await model.generate_content_async(
        prompt,
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 25},
    )
    data = json.loads(response.text.strip())
    return {
        "corrected_answer": data.get("corrected_answer", ""),
        "improvement_comments": list(data.get("improvement_comments", [])),
    }


_HELP_PROMPT_TEMPLATE = """A student is practicing IELTS Speaking {part_desc} and was asked:
"{question}"

Give them:
1. hint: 2-3 short ideas in Russian for what they could talk about, each with 1-2 useful English words or \
phrases in brackets. One line per idea, no numbering.
2. sample: a natural sample answer in English at about IELTS band 7 — {sample_length}, spoken style, first person.

Respond STRICTLY as JSON, no markdown:
{{"hint": "...", "sample": "..."}}
"""


async def build_question_help(part: str, question: str) -> dict:
    """Подсказка (идеи на русском) и пример ответа на конкретный вопрос экзаменатора."""
    model = _model()
    prompt = _HELP_PROMPT_TEMPLATE.format(
        part_desc=_PART_LABELS.get(part, part),
        question=question,
        sample_length="8-10 sentences" if part == "part2" else "3-4 sentences",
    )
    response = await model.generate_content_async(
        prompt,
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 25},
    )
    data = json.loads(response.text.strip())
    return {"hint": data.get("hint", ""), "sample": data.get("sample", "")}
