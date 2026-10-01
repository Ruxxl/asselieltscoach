"""Writing Checker: проверка эссе IELTS Writing (Task 1 Academic / Task 1 General / Task 2) через Gemini.

Тот же паттерн, что и Speaking (backend/services/speaking.py): один JSON-запрос к модели на действие.
Баллы по 4 критериям отдаёт модель, а общий балл считаем сами по правилу IELTS — модель часто
округляет его неправильно. Ошибки возвращаются как точные фрагменты текста ученика, чтобы
фронтенд мог подсветить их прямо в эссе и дать принять/отклонить правку.
"""

import asyncio
import json
import math
import re

import google.generativeai as genai
from google.api_core.exceptions import DeadlineExceeded, InternalServerError, ResourceExhausted, ServiceUnavailable

from backend.config import GEMINI_API_KEY, GEMINI_MODEL, WRITING_GEMINI_MODEL


class GeminiNotConfigured(RuntimeError):
    pass


TASK_TYPES = {
    "task2": "IELTS Writing Task 2 (argumentative / discussion essay, at least 250 words, 40 minutes)",
    "task1_academic": (
        "IELTS Writing Task 1 Academic (report describing a graph, chart, table, process or map, "
        "at least 150 words, 20 minutes)"
    ),
    "task1_general": (
        "IELTS Writing Task 1 General Training (a formal, semi-formal or informal letter, "
        "at least 150 words, 20 minutes)"
    ),
}
MIN_WORDS = {"task2": 250, "task1_academic": 150, "task1_general": 150}

LANGUAGES = {"ru": "Russian", "en": "English", "kk": "Kazakh", "uz": "Uzbek"}

TONES = {
    "friendly": "warm and encouraging",
    "neutral": "neutral and professional",
    "strict": "strict and direct, like a demanding examiner (but never rude)",
}

ISSUE_CATEGORIES = {"grammar", "vocabulary", "spelling", "punctuation", "word_choice", "coherence", "style"}

CRITERIA = ("task_response", "coherence_cohesion", "lexical_resource", "grammar_accuracy")


def count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", text))


def ielts_overall(bands: list[float]) -> float:
    """Среднее по критериям с округлением IELTS: .25 -> вверх до .5, .75 -> вверх до целого."""
    return math.floor(sum(bands) / len(bands) * 2 + 0.5) / 2


def _band(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(9.0, max(0.0, round(v * 2) / 2))


def _model(name: str, system_instruction: str | None = None):
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY не задан в .env. Получить бесплатный ключ: https://aistudio.google.com/apikey"
        )
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(name, system_instruction=system_instruction)


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # flash-lite на длинных ответах изредка пишет битые escape-последовательности
        # (одинокий "\u" или "\'") — выкидываем лишний обратный слэш и пробуем ещё раз.
        return json.loads(re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', "", text))


async def _ask_json(parts, timeout: int = 40, system_instruction: str | None = None, fast: bool = False) -> dict:
    # У более мощной модели меньше бесплатная квота и изредка бывают ответы дольше минуты —
    # упёрлись в квоту/таймаут/сбой, отвечаем основной (flash-lite), чем ученик увидит ошибку.
    # fast=True — для коротких/английских ответов (чат, образец, скан), где важнее скорость.
    models = [GEMINI_MODEL] if fast else list(dict.fromkeys([WRITING_GEMINI_MODEL, GEMINI_MODEL]))
    for model_name in models:
        model = _model(model_name, system_instruction)
        try:
            for attempt in range(2):
                response = await model.generate_content_async(
                    parts,
                    generation_config={"response_mime_type": "application/json"},
                    request_options={"timeout": timeout},
                )
                try:
                    return _parse_json(response.text.strip())
                except json.JSONDecodeError:
                    if attempt:
                        raise
        except (ResourceExhausted, DeadlineExceeded, ServiceUnavailable, InternalServerError):
            if model_name == models[-1]:
                raise
    raise AssertionError("unreachable")


_CHECK_PROMPT = """You are a certified IELTS Writing examiner. Assess the candidate's response below for \
{task_desc}, strictly by the official public IELTS Writing band descriptors.

Task / question:
\"\"\"{topic}\"\"\"
{image_note}
Candidate's response ({word_count} words; the minimum is {min_words}):
\"\"\"{essay}\"\"\"

Settings:
- Write all explanations, comments and feedback in {language}. Corrections and suggested English wording \
stay in English.
- {audience}
- The candidate's target is band {target_band}. Score HONESTLY regardless of the target — the target only \
decides which advice to prioritise (what separates their current level from the target).

Do the following:
1. If the response is empty, not in English, or obviously not an attempt at this task (random text, a few \
words), set "assessable" to false, all bands to 0, and explain why in "summary". Otherwise "assessable" is true.
2. Score each criterion 0-9 in 0.5 steps: task_response (Task Achievement for Task 1 / Task Response for \
Task 2), coherence_cohesion, lexical_resource, grammar_accuracy. Penalise responses under the minimum word \
count in task_response as the descriptors require. For each criterion give "comment": 2-3 sentences on what \
the candidate did and what keeps them from the next band{reasoning_rule}.
3. "summary": 2-4 sentences, an overall verdict.
4. "strengths": 2-4 short points. "improvements": 3-5 short, concrete, actionable points. Both in {language}.
5. "issues": {issues_rule} Each issue: "original" = the EXACT fragment copied character-for-character from the \
candidate's response (a few words up to one sentence — just enough to locate and fix the error, never the \
whole paragraph), "suggestion" = the corrected replacement for exactly that fragment, "category" = one of \
grammar, vocabulary, spelling, punctuation, coherence, style{word_choice_category}, "explanation" = one short \
sentence why. List issues in the order they appear in the text; never two issues for overlapping fragments.
{word_choice_rule}{teacher_rule}
Respond STRICTLY as JSON, no markdown:
{{"assessable": true, "criteria": {{"task_response": {{"band": 0, "comment": "...", "reasoning": "..."}}, \
"coherence_cohesion": {{...}}, "lexical_resource": {{...}}, "grammar_accuracy": {{...}}}}, "summary": "...", \
"strengths": ["..."], "improvements": ["..."], "issues": [{{"original": "...", "suggestion": "...", \
"category": "...", "explanation": "..."}}], "teacher_comment": "..."}}
"""


def _locate_issues(essay: str, raw_issues) -> list[dict]:
    """Оставляем только правки, чей фрагмент реально есть в тексте (модель иногда «исправляет»
    цитату), и приводим его к точному написанию из эссе, чтобы фронтенд нашёл его поиском."""
    issues, used_until = [], 0
    lowered = essay.lower()
    for raw in raw_issues if isinstance(raw_issues, list) else []:
        if not isinstance(raw, dict):
            continue
        original = str(raw.get("original") or "").strip()
        suggestion = str(raw.get("suggestion") or "").strip()
        if not original or original == suggestion:
            continue
        at = essay.find(original, used_until)
        if at < 0:
            at = lowered.find(original.lower(), used_until)
        if at < 0:  # не по порядку — ищем с начала, но без пересечения с уже найденными
            at = lowered.find(original.lower())
            if at < 0 or any(at < i["end"] and i["start"] < at + len(original) for i in issues):
                continue
        category = str(raw.get("category") or "grammar").lower()
        issues.append({
            "start": at,
            "end": at + len(original),
            "original": essay[at : at + len(original)],
            "suggestion": suggestion,
            "category": category if category in ISSUE_CATEGORIES else "grammar",
            "explanation": str(raw.get("explanation") or "").strip(),
        })
        used_until = max(used_until, at + len(original))
    issues.sort(key=lambda i: i["start"])
    return issues


async def check_essay(
    *,
    task_type: str,
    topic: str,
    essay: str,
    language: str,
    mode: str,
    tone: str,
    target_band: str,
    ai_reasoning: bool,
    improve_word_choice: bool,
    detailed_feedback: bool,
    sample_essay: bool,
    image: tuple[bytes, str] | None = None,
) -> dict:
    lang_name = LANGUAGES.get(language, "Russian")
    if mode == "teacher":
        audience = (
            "The reader is the candidate's TEACHER: write comments about the student in the third person, "
            "precise and examiner-like, using IELTS terminology."
        )
        teacher_rule = (
            f'7. "teacher_comment": a ready-to-send message from the teacher TO the student (second person, '
            f"in {lang_name}, 4-6 sentences, tone: {TONES.get(tone, TONES['friendly'])}) summarising the band, "
            f"the main strengths and the 2-3 things to work on first.\n"
        )
    else:
        audience = (
            "The reader is the STUDENT themselves: address them as \"you\", explain simply without jargon, "
            "be encouraging but honest."
        )
        teacher_rule = '7. "teacher_comment": empty string.\n'

    word_count = count_words(essay)
    prompt = _CHECK_PROMPT.format(
        task_desc=TASK_TYPES[task_type],
        topic=topic or "(the candidate did not provide the question — infer it from the response)",
        image_note=(
            "The attached image is the visual (chart / table / process / map) the candidate had to describe — "
            "check their data against it.\n"
            if image
            else ""
        ),
        word_count=word_count,
        min_words=MIN_WORDS[task_type],
        essay=essay,
        language=lang_name,
        audience=audience,
        target_band=target_band,
        reasoning_rule=(
            '; and "reasoning": 1-2 sentences explaining which band descriptor features justify exactly this '
            "band (quote the descriptor wording briefly)"
            if ai_reasoning
            else '; "reasoning": empty string'
        ),
        issues_rule=(
            "list EVERY language error in the response (grammar, articles, tenses, agreement, prepositions, "
            "spelling, punctuation, wrong or unnatural words, awkward phrasing), up to 40."
            if detailed_feedback
            else "list only the 8 most important errors (the ones that most lower the band)."
        ),
        word_choice_category=", word_choice" if improve_word_choice else "",
        word_choice_rule=(
            '6. Also add to "issues" up to 10 word-choice upgrades with category "word_choice": fragments that are '
            "correct but basic or repetitive, with a more precise, academic or less-common alternative suitable for "
            f"band {target_band}.\n"
            if improve_word_choice
            else ""
        ),
        teacher_rule=teacher_rule,
    )
    parts = [{"mime_type": image[1], "data": image[0]}, prompt] if image else prompt

    if sample_essay:
        data, sample = await asyncio.gather(
            _ask_json(parts, timeout=70),
            generate_sample(
                task_type=task_type,
                topic=topic or f"(not given — infer the question from this candidate response: {essay[:800]})",
                target_band="8.0-9.0",
                image=image,
            ),
        )
    else:
        data, sample = await _ask_json(parts, timeout=70), None

    raw_criteria = data.get("criteria") if isinstance(data.get("criteria"), dict) else {}
    criteria = {}
    for key in CRITERIA:
        raw = raw_criteria.get(key) if isinstance(raw_criteria.get(key), dict) else {}
        criteria[key] = {
            "band": _band(raw.get("band")),
            "comment": str(raw.get("comment") or "").strip(),
            "reasoning": str(raw.get("reasoning") or "").strip() if ai_reasoning else "",
        }
    assessable = bool(data.get("assessable", True)) and any(c["band"] > 0 for c in criteria.values())
    return {
        "assessable": assessable,
        "overall_band": ielts_overall([c["band"] for c in criteria.values()]) if assessable else 0.0,
        "word_count": word_count,
        "criteria": criteria,
        "summary": str(data.get("summary") or "").strip(),
        "strengths": [str(s) for s in data.get("strengths") or [] if s],
        "improvements": [str(s) for s in data.get("improvements") or [] if s],
        "issues": _locate_issues(essay, data.get("issues")) if assessable else [],
        "teacher_comment": str(data.get("teacher_comment") or "").strip() if mode == "teacher" else "",
        "sample_essay": sample if assessable else None,
    }


async def generate_sample(*, task_type: str, topic: str, target_band: str, image: tuple[bytes, str] | None = None) -> str:
    """Образцовый ответ на задание (кнопка «Пример ответа» и опция Sample Essays)."""
    prompt = f"""Write a model answer for {TASK_TYPES[task_type]} at IELTS band {target_band}.
Task / question:
\"\"\"{topic}\"\"\"
{"The attached image is the visual to describe — use its real data." if image else ""}
Write {"about 280-320 words" if task_type == "task2" else "about 170-200 words"}, with clear paragraphs separated \
by a blank line, natural (not robotic) language appropriate for that band. No title, no headings, no commentary.

Respond STRICTLY as JSON, no markdown: {{"essay": "..."}}
"""
    parts = [{"mime_type": image[1], "data": image[0]}, prompt] if image else prompt
    data = await _ask_json(parts, timeout=45, fast=True)
    return str(data.get("essay") or "").strip()


async def brainstorm(*, task_type: str, topic: str, language: str) -> str:
    """AI Assistant: идеи и план ответа до того, как ученик начал писать."""
    lang_name = LANGUAGES.get(language, "Russian")
    prompt = f"""A student is preparing to write {TASK_TYPES[task_type]}.
Task / question:
\"\"\"{topic}\"\"\"

Help them plan (do NOT write the answer for them). In {lang_name}, give:
- how to understand the task and what exactly it asks (1-2 sentences);
- a recommended paragraph-by-paragraph plan with the main idea of each paragraph;
- 2-3 arguments/ideas with a short example for each (for Task 1 — the key features/trends to report);
- 6-8 useful English phrases and topic vocabulary (keep these in English).
Plain text, short lines, use "•" for bullets, a blank line between sections, no markdown symbols.

Respond STRICTLY as JSON, no markdown: {{"text": "..."}}
"""
    data = await _ask_json(prompt, timeout=40)
    return str(data.get("text") or "").strip()


async def extract_text(image_bytes: bytes, mime_type: str) -> str:
    """Scan: распознаём рукописное/напечатанное эссе с фото."""
    prompt = """The image is a photo or screenshot of a handwritten or printed English text (an IELTS essay or \
letter). Transcribe it exactly as written — keep the student's own spelling and grammar mistakes, do NOT \
correct anything — preserving paragraph breaks as blank lines. If there is no readable English text, return \
an empty string.

Respond STRICTLY as JSON, no markdown: {"text": "..."}
"""
    data = await _ask_json([{"mime_type": mime_type, "data": image_bytes}, prompt], timeout=40, fast=True)
    return str(data.get("text") or "").strip()


def _report_context(check: dict) -> str:
    result = check["result"]
    criteria = "\n".join(
        f"- {key}: {value['band']} — {value['comment']}" for key, value in result["criteria"].items()
    )
    issues = "\n".join(
        f'- "{i["original"]}" -> "{i["suggestion"]}" ({i["category"]}): {i["explanation"]}'
        for i in result["issues"][:40]
    )
    return f"""Task type: {TASK_TYPES[check["task_type"]]}
Question: {check["topic"] or "(not provided)"}
Student's essay:
\"\"\"{check["essay"]}\"\"\"

Your assessment: overall band {result["overall_band"]}
{criteria}
Summary: {result["summary"]}
Errors you marked:
{issues or "(none)"}"""


async def chat_about_essay(check: dict, history: list[dict], message: str) -> str:
    """Chat with AI: уточняющие вопросы по проверенному эссе."""
    lang_name = LANGUAGES.get(check["language"], "Russian")
    system = f"""You are an IELTS Writing tutor. You have just assessed a student's essay (details below) and \
now answer their follow-up questions about it: explain marked errors, why a criterion got its band, how to \
reach a higher band, or rewrite a paragraph/sentence in another style when asked. Stay on IELTS writing and \
this essay. Answer in {lang_name} (rewritten English text stays in English). Be concise: a few short \
paragraphs at most, plain text without markdown symbols.

{_report_context(check)}"""
    dialogue = "\n".join(f"{'Student' if t['role'] == 'user' else 'Tutor'}: {t['text']}" for t in history[-12:])
    prompt = f"""{dialogue}
Student: {message}

Respond STRICTLY as JSON, no markdown: {{"reply": "..."}}"""
    data = await _ask_json(prompt, timeout=40, system_instruction=system, fast=True)
    return str(data.get("reply") or "").strip()
