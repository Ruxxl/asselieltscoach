"""Grammar Checker: проверка орфографии, пунктуации, грамматики и стиля текста на любом языке через Gemini.

Переиспользует механику Writing Checker (backend/services/writing.py): общий вызов модели с откатом на
flash-lite и привязку правок к точным фрагментам текста. В отличие от Writing, здесь нет оценки по
критериям IELTS — только правки, по желанию общая оценка качества текста и быстрые преобразования стиля.
"""

from backend.services.writing import ask_json, locate_issues

# Языки текста и объяснений. Gemini понимает больше — это то, что показываем в выпадающем списке.
TEXT_LANGUAGES = {
    "auto": "auto-detect",
    "en": "English", "ru": "Russian", "kk": "Kazakh", "uz": "Uzbek", "ky": "Kyrgyz", "uk": "Ukrainian",
    "be": "Belarusian", "tr": "Turkish", "az": "Azerbaijani", "tg": "Tajik", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "cs": "Czech",
    "ro": "Romanian", "el": "Greek", "sv": "Swedish", "fi": "Finnish", "no": "Norwegian", "da": "Danish",
    "hu": "Hungarian", "ar": "Arabic", "fa": "Persian", "he": "Hebrew", "hi": "Hindi", "ur": "Urdu",
    "bn": "Bengali", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "vi": "Vietnamese", "th": "Thai",
    "id": "Indonesian", "ms": "Malay", "ka": "Georgian", "hy": "Armenian", "mn": "Mongolian",
}
AI_LANGUAGES = {k: v for k, v in TEXT_LANGUAGES.items() if k != "auto"}

CONTEXTS = {
    "general": "general everyday writing (messages, posts, emails to friends)",
    "formal": "formal writing (official letters, applications, complaints)",
    "business": "business writing (work emails, reports, presentations)",
    "academic": "academic writing (essays, papers, theses)",
    "school": "a school assignment or essay",
    "ielts": "IELTS exam preparation (writing judged by IELTS band descriptors)",
    "toefl": "TOEFL exam preparation",
    "cambridge": "Cambridge English exam preparation (B2 First, C1 Advanced, C2 Proficiency)",
    "jlpt": "JLPT (Japanese) exam preparation",
    "hsk": "HSK (Chinese) exam preparation",
    "topik": "TOPIK (Korean) exam preparation",
    "dele": "DELE (Spanish) exam preparation",
}

TARGET_LEVELS = {
    "none": None,
    "b2": "IELTS Band 5.5-6.5 / CEFR B2",
    "c1": "IELTS Band 7.0-8.0 / CEFR C1",
    "c2": "IELTS Band 8.5-9.0 / CEFR C2",
}

TRANSFORMS = {
    "vocabulary": "Upgrade the vocabulary: replace basic, vague or repeated words with more precise, natural and "
    "varied ones suitable for the level and context. Keep the meaning and structure.",
    "rephrase": "Rephrase it: say the same thing in different words and sentence structures, keeping the meaning.",
    "concise": "Make it concise: remove filler, redundancy and wordiness; keep every important idea.",
    "strengthen": "Strengthen it: make it more confident, persuasive and impactful (stronger verbs, clear claims, "
    "no hedging), without exaggerating facts.",
    "readability": "Improve readability: shorter, clearer sentences, simpler wording where possible, smooth flow.",
    "structure": "Improve the structure: better sentence order, logical connectors, paragraphing and transitions.",
    "polish": "Write a polished model version: correct every error and improve style so it reads like an excellent "
    "text of this kind written by a skilled native writer. Keep the author's ideas and approximate length.",
}


def _level_line(target: str) -> str:
    level = TARGET_LEVELS.get(target)
    return f"The writer is aiming for {level}." if level else ""


_CHECK_PROMPT = """You are an expert proofreader and language teacher. Check the text below.

Text language: {text_language}
Context: the text is {context}. {level}
Text:
\"\"\"{text}\"\"\"

Settings:
- Write every explanation, comment and assessment in {ai_language}. Corrections stay in the language of the text.
- {audience}
{context_rule}
Do the following:
1. "detected_language": the language the text is written in, as its English name.
2. "issues": every spelling, punctuation and grammar error, plus wrong word choice and clearly unnatural or \
inappropriate (for this context) wording{style_rule}. Up to 60. Each issue: "original" = the EXACT fragment \
copied character-for-character from the text (a few words up to one sentence — just enough to locate and fix \
the error), "suggestion" = the corrected replacement for exactly that fragment, "category" = one of spelling, \
grammar, punctuation, vocabulary, word_choice, style, coherence, "explanation" = {explanation_rule}. \
List issues in text order; never two issues for overlapping fragments. If the text has no errors, return [].
{assessment_rule}{teacher_rule}
Respond STRICTLY as JSON, no markdown:
{{"detected_language": "...", "issues": [{{"original": "...", "suggestion": "...", "category": "...", \
"explanation": "..."}}], "assessment": {{"score": 0, "level": "...", "summary": "...", "strengths": ["..."], \
"improvements": ["..."]}}, "teacher_comment": "..."}}
"""


async def check_text(
    *,
    text: str,
    text_language: str,
    ai_language: str,
    mode: str,
    context: str,
    target: str,
    explanations: bool,
    detailed: bool,
    use_context: bool,
) -> dict:
    ai_lang = AI_LANGUAGES.get(ai_language, "Russian")
    if mode == "teacher":
        audience = (
            "The reader is a TEACHER checking a student's work: name the rule behind each error precisely, "
            "using grammar terminology."
        )
        teacher_rule = (
            f'5. "teacher_comment": a ready-to-send note from the teacher TO the student (second person, in '
            f"{ai_lang}, 3-5 sentences): overall impression, the main error patterns to work on, encouragement.\n"
        )
    else:
        audience = (
            "The reader is a LEARNER: explain each rule simply, like a friendly tutor, so they learn it and "
            "don't repeat the mistake."
        )
        teacher_rule = '5. "teacher_comment": empty string.\n'

    prompt = _CHECK_PROMPT.format(
        text_language=(
            "detect it yourself" if text_language == "auto" else TEXT_LANGUAGES.get(text_language, text_language)
        ),
        context=CONTEXTS.get(context, CONTEXTS["general"]),
        level=_level_line(target),
        text=text,
        ai_language=ai_lang,
        audience=audience,
        context_rule=(
            "- Use the whole text as context: also flag inconsistencies across sentences (tense, terminology, "
            "names, register) and wording that is wrong for the chosen context, not only errors inside a sentence.\n"
            if use_context
            else "- Check sentence by sentence; do not flag style choices that depend on the wider context.\n"
        ),
        style_rule=" and weak style" if use_context else "",
        explanation_rule=(
            "one or two short sentences: what is wrong and the rule behind it"
            if explanations
            else "empty string"
        ),
        assessment_rule=(
            '4. "assessment": "score" 0-100 = overall quality of the text for its context and target level; '
            '"level" = the estimated CEFR level of the writing (e.g. "B1"), and the IELTS-like band too if the '
            'context is IELTS (e.g. "B2 · IELTS 6.0"); "summary" 2-3 sentences; "strengths" 2-3 points; '
            '"improvements" 2-4 concrete points.\n'
            if detailed
            else '4. "assessment": null.\n'
        ),
        teacher_rule=teacher_rule,
    )
    data = await ask_json(prompt, timeout=70)

    raw_assessment = data.get("assessment") if detailed else None
    assessment = None
    if isinstance(raw_assessment, dict):
        try:
            score = max(0, min(100, int(float(raw_assessment.get("score") or 0))))
        except (TypeError, ValueError):
            score = 0
        assessment = {
            "score": score,
            "level": str(raw_assessment.get("level") or "").strip(),
            "summary": str(raw_assessment.get("summary") or "").strip(),
            "strengths": [str(s) for s in raw_assessment.get("strengths") or [] if s],
            "improvements": [str(s) for s in raw_assessment.get("improvements") or [] if s],
        }
    issues = locate_issues(text, data.get("issues"))
    if not explanations:
        for issue in issues:
            issue["explanation"] = ""
    return {
        "detected_language": str(data.get("detected_language") or "").strip(),
        "issues": issues,
        "assessment": assessment,
        "teacher_comment": str(data.get("teacher_comment") or "").strip() if mode == "teacher" else "",
    }


async def transform_text(*, text: str, action: str, context: str, target: str, full_text: str | None = None) -> str:
    """Быстрые кнопки стиля: переписываем фрагмент (или весь текст) на языке оригинала."""
    surrounding = (
        f'\nFor context, this fragment is part of a longer text:\n"""{full_text[:4000]}"""\n'
        if full_text and full_text.strip() != text.strip()
        else ""
    )
    prompt = f"""{TRANSFORMS[action]}
The text is {CONTEXTS.get(context, CONTEXTS["general"])}. {_level_line(target)}
Keep the SAME language as the original and the same paragraph breaks. Fix any errors along the way. \
Never add facts, claims, details or examples that are not in the original text, and keep every \
statement at the same level of specificity (a vague "some things" must not become a specific problem). \
Return only the rewritten text — no comments, quotes or explanations.
{surrounding}
Text to rewrite:
\"\"\"{text}\"\"\"

Respond STRICTLY as JSON, no markdown: {{"text": "..."}}
"""
    data = await ask_json(prompt, timeout=45, fast=action != "polish")
    return str(data.get("text") or "").strip()


async def chat_about_text(
    *, text: str, issues: list[dict], history: list[dict], message: str, ai_language: str
) -> str:
    """ИИ-помощник: вопросы про правила, ошибки и стиль конкретного текста."""
    marked = "\n".join(f'- "{i["original"]}" -> "{i["suggestion"]}" ({i["category"]})' for i in issues[:40])
    system = f"""You are a friendly expert language tutor and writing assistant. The student is working on the \
text below{" and its proofreading results" if marked else ""}. Answer their questions: explain grammar rules \
with short examples, explain why something was corrected, suggest better wording, or rewrite parts when asked. \
Answer in {AI_LANGUAGES.get(ai_language, "Russian")} (example sentences stay in the language being learned). \
Be concise: a few short paragraphs at most, plain text without markdown symbols.

Text:
\"\"\"{text[:6000]}\"\"\"
{"Corrections already suggested:" + chr(10) + marked if marked else ""}"""
    dialogue = "\n".join(f"{'Student' if t['role'] == 'user' else 'Tutor'}: {t['text']}" for t in history[-12:])
    prompt = f"""{dialogue}
Student: {message}

Respond STRICTLY as JSON, no markdown: {{"reply": "..."}}"""
    data = await ask_json(prompt, timeout=40, system_instruction=system, fast=True)
    return str(data.get("reply") or "").strip()
