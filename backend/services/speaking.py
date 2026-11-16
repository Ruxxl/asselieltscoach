"""Speaking Practice: тренировка по одному вопросу (не диалог).

Поток ученика (см. документ преподавателя, лист «проверка speaking»):
вопрос -> подсказка (5-6 опорных фраз) -> готовый ответ -> ученик записывает свой ответ ->
грамматический разбор (только грамматика + какие темы повторить) -> по кнопкам: «примерная оценка»
по 4 критериям IELTS и «улучшить мой ответ» на 1-1.5 балла выше.

Аудио ответа уходит ОДНИМ мультимодальным запросом в Gemini (расшифровка + грамматика), как в
reading-check (backend/services/gemini.py). Остальное — текстовые запросы по расшифровке.
Озвучка вопроса — отдельно (backend/services/tts.py).
"""

import json

import google.generativeai as genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL

# Ответ на карточку Part 2 — 1-2 минуты речи: аудио длиннее, ответ ИИ тоже — таймаут щедрее.
_TIMEOUT = 45


class GeminiNotConfigured(RuntimeError):
    pass


_KIND_LABELS = {
    "part1": "Part 1 (Introduction and Interview) — short, simple, everyday answers of 2-4 sentences",
    "part2": "Part 2 (Individual Long Turn) — a 1-2 minute talk built from the cue card",
    "part3": "Part 3 (Two-way Discussion) — developed opinions of 4-6 sentences with reasons and examples",
}

# Сжатая версия публичных Band Descriptors IELTS Speaking (таблица из документа преподавателя) —
# чтобы модель оценивала по тем же формулировкам, что и экзаменатор.
_BAND_DESCRIPTORS = """IELTS Speaking public band descriptors (condensed):
- Fluency and Coherence: 9 fluent, hesitation only for content; 8 occasional repetition/self-correction, \
hesitation mostly for content, coherent topic development; 7 speaks at length without noticeable effort, some \
hesitation/repetition/self-correction, flexible use of connectives; 6 willing to speak at length but may lose \
coherence through repetition, self-correction or hesitation, uses a range of connectives imperfectly; 5 usually \
keeps going but relies on repetition/self-correction/slow speech, over-uses some connectives; 4 cannot respond \
without noticeable pauses, frequent repetition, simple sentences linked poorly.
- Lexical Resource: 9 total flexibility, precise idiomatic use; 8 wide vocabulary used readily and flexibly, \
skilful use of less common/idiomatic items with occasional inaccuracy, effective paraphrase; 7 flexible \
vocabulary to discuss a variety of topics, some less common and idiomatic items with some awareness of style \
and collocation, effective paraphrase; 6 wide enough vocabulary to discuss topics at length, generally \
appropriate even if inaccurate at times, generally successful paraphrase; 5 manages familiar and unfamiliar \
topics but with limited flexibility, attempts paraphrase with mixed success; 4 basic meanings on familiar topics, \
limited ability to paraphrase.
- Grammatical Range and Accuracy: 9 full range, consistently accurate; 8 wide range of structures, majority of \
sentences error-free, occasional inappropriate usage; 7 a range of complex structures with some flexibility, \
frequently error-free sentences though some errors persist; 6 mix of short and complex forms with limited \
flexibility, errors frequent in complex structures but rarely impede communication; 5 basic sentence forms with \
reasonable accuracy, limited range of complex structures that usually contain errors; 4 basic forms, subordinate \
clauses rare, errors frequent and may cause misunderstanding.
- Pronunciation: 9 full range of features, effortless to understand; 8 wide range of features, easy to \
understand throughout, L1 accent has minimal effect; 7 shows all positive features of band 6 and some of 8; \
6 uses a range of features with variable control, can generally be understood throughout, mispronunciation \
reduces clarity at times; 5 all positive features of band 4 and some of 6; 4 limited range of features, \
mispronunciations frequent and cause some difficulty."""


def _model(system_instruction: str | None = None):
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY не задан в .env. Получить бесплатный ключ: https://aistudio.google.com/apikey"
        )
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(GEMINI_MODEL, system_instruction=system_instruction)


async def _generate_json(parts, timeout: int = _TIMEOUT) -> dict:
    response = await _model().generate_content_async(
        parts,
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": timeout},
    )
    data = json.loads(response.text.strip())
    return data if isinstance(data, dict) else {}


def _kind_desc(kind: str) -> str:
    return _KIND_LABELS.get(kind, _KIND_LABELS["part1"])


# ---------- подсказка и готовый ответ ----------

_HELP_PROMPT_TEMPLATE = """A student is practicing IELTS Speaking {part_desc} and was asked:
"{question}"

Give them:
1. sample: a natural sample answer in English at about IELTS band 7 — {sample_length}, spoken style, first person. \
For a Part 2 cue card, cover every point of "You should say" in order.
2. vocabulary: 5-6 useful collocations or phrases (band 7+, natural, not single basic words) that are used in \
YOUR sample answer, in their dictionary form (e.g. "leave something until the last minute"), each with an \
accurate Russian translation.

Respond STRICTLY as JSON, no markdown:
{{"sample": "...", "vocabulary": [{{"phrase": "...", "translation": "..."}}]}}
"""

_SAMPLE_LENGTH = {"part1": "3-4 sentences", "part2": "10-12 sentences", "part3": "5-6 sentences"}


async def build_question_help(kind: str, question: str) -> dict:
    """Подсказка (5-6 фраз из примера с переводом) и готовый ответ на вопрос."""
    data = await _generate_json(
        _HELP_PROMPT_TEMPLATE.format(
            part_desc=_kind_desc(kind), question=question, sample_length=_SAMPLE_LENGTH.get(kind, "3-4 sentences")
        )
    )
    vocabulary = [
        {"phrase": str(v.get("phrase", "")).strip(), "translation": str(v.get("translation", "")).strip()}
        for v in data.get("vocabulary") or []
        if isinstance(v, dict) and v.get("phrase")
    ]
    return {"vocabulary": vocabulary[:6], "sample": str(data.get("sample", "")).strip()}


# ---------- ответ ученика: расшифровка + грамматика ----------

_CHECK_PROMPT_TEMPLATE = """A student is practicing IELTS Speaking {part_desc}. The question was:
"{question}"

The attached audio is the student's spoken answer. Do this:
1. Transcribe exactly what the student said, in English, with natural punctuation. Keep their mistakes — do NOT \
correct the transcript. If the audio is silent or unintelligible, set "student_said" to "" and leave the lists empty.
2. Find the student's GRAMMAR mistakes ONLY (tenses, articles, prepositions, subject-verb agreement, word order, \
plurals, countable/uncountable nouns, modal verbs, conditionals, pronouns, comparatives, etc.). Ignore vocabulary \
choice, style, naturalness, pronunciation, filler words, repetitions and punctuation. List at most 6, the most \
important first, each as: "original" = the student's exact words containing the mistake, "better" = the same words \
corrected, "why" = one short explanation in RUSSIAN naming the rule.
3. "review_topics": 1-4 grammar topics the student should revise, based on the mistakes above — "topic" = the \
grammar topic name in English (e.g. "Past Simple vs Present Perfect"), "note" = one short sentence in RUSSIAN on \
what exactly to repeat. Empty list if there were no grammar mistakes.

Respond STRICTLY as JSON, no markdown:
{{"student_said": "...", "corrections": [{{"original": "...", "better": "...", "why": "..."}}], \
"review_topics": [{{"topic": "...", "note": "..."}}]}}
"""


def _text_items(raw, keys: tuple[str, ...], limit: int) -> list[dict]:
    items = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        item = {k: str(entry.get(k, "")).strip() for k in keys}
        if item[keys[0]]:
            items.append(item)
    return items[:limit]


async def check_answer(kind: str, question: str, audio_bytes: bytes, mime_type: str) -> dict:
    data = await _generate_json(
        [
            {"mime_type": mime_type, "data": audio_bytes},
            _CHECK_PROMPT_TEMPLATE.format(part_desc=_kind_desc(kind), question=question),
        ]
    )
    return {
        "student_said": str(data.get("student_said", "")).strip(),
        "corrections": _text_items(data.get("corrections"), ("original", "better", "why"), 6),
        "review_topics": _text_items(data.get("review_topics"), ("topic", "note"), 4),
    }


# ---------- «примерная оценка» по 4 критериям ----------

_CRITERIA = ("fluency_coherence", "lexical_resource", "grammar_accuracy", "pronunciation")

_ESTIMATE_PROMPT_TEMPLATE = """You are an IELTS Speaking examiner giving an APPROXIMATE band estimate for one answer \
in a practice session ({part_desc}).
Question: "{question}"
Student's answer (transcribed from speech):
"{answer}"

{descriptors}

Score the answer on the 4 criteria, each 0-9 in 0.5 steps, using the descriptors above. This is a single short \
answer, so be realistic and cautious. Pronunciation: you only have a TEXT transcript, so estimate it cautiously \
from indirect signs and say so; do not overstate confidence. overall_band = average of the 4 criteria rounded to \
the nearest 0.5.
For EACH criterion write 1-2 sentences of feedback in ENGLISH (clear B1-B2 English, addressed to the student as \
"you"), naming one concrete strength and one concrete weakness and quoting the student's exact words in double \
quotes where possible.

Respond STRICTLY as JSON, no markdown:
{{"fluency_coherence": 0-9, "lexical_resource": 0-9, "grammar_accuracy": 0-9, "pronunciation": 0-9, \
"overall_band": 0-9, "criteria_feedback": {{"fluency_coherence": "...", "lexical_resource": "...", \
"grammar_accuracy": "...", "pronunciation": "..."}}}}
"""


def _band(value) -> float:
    try:
        return max(0.0, min(9.0, round(float(value) * 2) / 2))
    except (TypeError, ValueError):
        return 0.0


async def estimate_answer(kind: str, question: str, answer: str) -> dict:
    data = await _generate_json(
        _ESTIMATE_PROMPT_TEMPLATE.format(
            part_desc=_kind_desc(kind), question=question, answer=answer, descriptors=_BAND_DESCRIPTORS
        )
    )
    bands = {key: _band(data.get(key)) for key in _CRITERIA}
    overall = _band(data.get("overall_band")) or _band(sum(bands.values()) / len(_CRITERIA))
    feedback = data.get("criteria_feedback") or {}
    return {
        **bands,
        "overall_band": overall,
        "criteria_feedback": {k: str(feedback.get(k, "")).strip() for k in _CRITERIA if feedback.get(k)},
    }


# ---------- «улучшить мой ответ» на 1-1.5 балла ----------

_IMPROVE_PROMPT_TEMPLATE = """You are an IELTS Speaking coach. A student answered this question ({part_desc}):
"{question}"
Student's answer (transcribed from speech):
"{answer}"

{descriptors}

1. Judge the student's current overall band (0.5 steps) -> "current_band".
2. Rewrite the answer so it would score 1 to 1.5 bands HIGHER (target_band = current_band + 1 to 1.5, at most 9). \
Build it ON the student's own answer: keep THEIR ideas, facts, examples and personal details and roughly their \
structure — do not invent a different story. Upgrade grammar range and accuracy, vocabulary (natural collocations \
and some less common phrases, not rare show-off words), connectives and development of ideas. Keep a natural \
spoken style that the student could realistically say, in first person, similar length (a little longer is fine).
3. Wrap every phrase you upgraded or added in **double asterisks** so the student can see what changed.

Respond STRICTLY as JSON, no markdown:
{{"current_band": 0-9, "target_band": 0-9, "improved_answer": "..."}}
"""


async def improve_answer(kind: str, question: str, answer: str) -> dict:
    data = await _generate_json(
        _IMPROVE_PROMPT_TEMPLATE.format(
            part_desc=_kind_desc(kind), question=question, answer=answer, descriptors=_BAND_DESCRIPTORS
        )
    )
    return {
        "current_band": _band(data.get("current_band")),
        "target_band": _band(data.get("target_band")),
        "improved_answer": str(data.get("improved_answer", "")).strip(),
    }
