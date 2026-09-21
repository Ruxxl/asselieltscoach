"""Speaking Practice: пошаговый диалог с ИИ-экзаменатором (не live-аудио стрим).

Каждый ход ученика — один аудио-клип, отправленный ОДНИМ мультимодальным запросом
в Gemini (тот же проверенный паттерн, что и в backend/services/gemini.py для
reading-check): модель одновременно (1) расшифровывает речь ученика, (2) отвечает
как экзаменатор — помогая со словами, если у ученика явный пробел, (3) решает,
закончена ли эта часть. Обычный текстовый/мультимодальный запрос на ход — надёжнее
и не зависит от квот preview-live-моделей (см. историю с gemini-3.6-flash/2.5-flash-lite).
"""

import json

import google.generativeai as genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL


class GeminiNotConfigured(RuntimeError):
    pass


_PART_GUIDANCE = {
    "part1": (
        "This is IELTS Speaking Part 1 (Introduction and Interview) practice. After the student names a "
        "topic they'd like to discuss, ask 3-4 short, simple, everyday questions about it, one at a time."
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


def _system_instruction(part: str) -> str:
    guidance = _PART_GUIDANCE.get(part, _PART_GUIDANCE["part1"])
    return f"""You are Assel, a friendly but professional IELTS Speaking examiner running a practice \
conversation with a student, one topic at a time. {guidance}

Rules:
- Speak only in English, at a natural conversational pace.
- Say or ask ONE thing at a time — keep your own turns short, you are the examiner, not the one being tested.
- If the student's answer shows a clear gap — a wrong word, an awkward phrase, or they explicitly ask how \
to say something — briefly and naturally give them the correct English word or phrase (just a few words), \
then continue the conversation. Don't turn this into a long grammar lecture.
- After a reasonable number of exchanges for this part (roughly 4-5 turns, or the long turn plus follow-ups \
for Part 2), wrap up with one short, friendly closing line thanking the student, and mark the conversation \
as finished.
"""


def _history_to_text(history: list[dict]) -> str:
    return "\n".join(f"{'Student' if t['speaker'] == 'user' else 'Examiner'}: {t['text']}" for t in history)


async def start_conversation(part: str) -> dict:
    """Первая реплика экзаменатора — до того, как ученик вообще что-то сказал."""
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY не задан в .env. Получить бесплатный ключ: https://aistudio.google.com/apikey"
        )
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=_system_instruction(part))
    response = await model.generate_content_async(
        "(Greet the student briefly in one short sentence and ask what they'd like to talk about today. "
        'Respond STRICTLY as JSON, no markdown: {"examiner_reply": "..."})',
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 25},
    )
    data = json.loads(response.text.strip())
    return {"ai_message": data.get("examiner_reply") or "Hi! What would you like to talk about today?"}


async def continue_conversation(part: str, history: list[dict], audio_bytes: bytes, mime_type: str) -> dict:
    """Один ход: аудио-ответ ученика -> {student_said, ai_message, finished}."""
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY не задан в .env. Получить бесплатный ключ: https://aistudio.google.com/apikey"
        )
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=_system_instruction(part))

    prompt = f"""Conversation so far:
{_history_to_text(history) or "(nothing yet — this is the student's first answer)"}

The attached audio is the student's spoken answer to your last message. Listen to it, then:
1. Transcribe what the student said, in English. If the audio is silent or unintelligible, say so honestly \
instead of guessing.
2. Give your next reply as the examiner (see your instructions — help with any clear word/phrase gaps, then \
continue naturally).
3. Decide whether this part of the practice should now finish.

Respond STRICTLY as JSON, no markdown:
{{"student_said": "...", "examiner_reply": "...", "finished": true/false}}
"""
    response = await model.generate_content_async(
        [{"mime_type": mime_type, "data": audio_bytes}, prompt],
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 25},
    )
    data = json.loads(response.text.strip())
    return {
        "student_said": data.get("student_said", ""),
        "ai_message": data.get("examiner_reply", ""),
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

Respond STRICTLY as JSON, no markdown wrapper:
{{"fluency_coherence": 0-9, "lexical_resource": 0-9, "grammar_accuracy": 0-9, "pronunciation": 0-9, \
"overall_band": 0-9, "summary_feedback": "..."}}
"""


async def score_session(history: list[dict], part: str) -> dict:
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY не задан в .env. Получить бесплатный ключ: https://aistudio.google.com/apikey"
        )
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
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
    }
