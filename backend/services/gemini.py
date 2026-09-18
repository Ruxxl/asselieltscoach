"""Проверка голосового Reading-ответа через Google Gemini API (free tier).

Один мультимодальный запрос: отдаём модели аудио-запись ответа ученика
плюс текст задания, просим транскрипцию и оценку правильности в JSON.
Ключ и модель берутся из .env (GEMINI_API_KEY / GEMINI_MODEL) — см. .env.example.
"""

import json

import google.generativeai as genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL

_PROMPT_TEMPLATE = """Ты — ИИ-ассистент курса английского языка, проверяешь задание Reading.
Ученику дали текст и вопрос, он должен был ответить вслух по-английски. Тебе передана аудиозапись его ответа.

Текст (passage): {passage}
Вопрос: {question}

Сделай следующее:
1. Расшифруй (transcribe) речь ученика на английском. Если в записи нет разборчивой речи (тишина, шум,
   слишком тихо/коротко) — НЕ придумывай ответ: верни transcript "" (пустая строка), is_correct false,
   accuracy_score 0, а в feedback честно напиши, что речь не удалось расслышать, и попроси записать ответ ещё раз.
2. Если речь разборчива — оцени, верный ли ответ по смыслу (учитывай неточное произношение, если смысл понятен — засчитывай).
3. Дай accuracy_score от 0 до 100 — насколько точен и понятен ответ (учитывай грамматику и произношение).
4. Дай короткий дружелюбный feedback на русском языке (1-3 предложения): что получилось хорошо и что стоит улучшить (например, конкретные звуки/слова).

Ответь СТРОГО в формате JSON без markdown-обёртки:
{{"transcript": "...", "is_correct": true/false, "accuracy_score": 0-100, "feedback": "..."}}
"""


class GeminiNotConfigured(RuntimeError):
    pass


async def grade_reading_answer(audio_bytes: bytes, mime_type: str, passage: str, question: str) -> dict:
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY не задан в .env. Получить бесплатный ключ: https://aistudio.google.com/apikey"
        )

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = _PROMPT_TEMPLATE.format(passage=passage, question=question)
    # Без явного timeout запрос к Gemini может зависнуть без ответа и без ошибки —
    # ученик будет бесконечно смотреть на "Эхо слушает и проверяет...".
    response = await model.generate_content_async(
        [
            {"mime_type": mime_type, "data": audio_bytes},
            prompt,
        ],
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 25},
    )

    text = response.text.strip()
    data = json.loads(text)
    return {
        "transcript": data.get("transcript", ""),
        "is_correct": bool(data.get("is_correct", False)),
        "accuracy_score": float(data.get("accuracy_score", 0)),
        "feedback": data.get("feedback", ""),
    }
