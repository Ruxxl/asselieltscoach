"""Speaking Practice: живой голосовой разговор с ИИ-экзаменатором через Gemini Live API.

Два разных вызова к Gemini:
1. run_live_relay — двусторонний аудио-стрим на время разговора (WebSocket-релей
   браузер <-> Gemini Live). Модель сама держит голос, VAD (конец фразы) и транскрипцию.
2. score_speaking_session — один обычный текстовый запрос ПОСЛЕ разговора: отдаём
   накопленный транскрипт, просим оценку по 4 критериям IELTS (как отдельный
   "экзаменатор-проверяющий", отдельно от "экзаменатора-собеседника" из шага 1).

Ключ и модели берутся из .env (GEMINI_API_KEY / GEMINI_LIVE_MODEL / GEMINI_MODEL).
"""

import asyncio
import contextlib
import json
import logging

from google import genai
from google.genai import types
from starlette.websockets import WebSocket, WebSocketDisconnect

from backend.config import GEMINI_API_KEY, GEMINI_LIVE_MODEL, GEMINI_MODEL

logger = logging.getLogger(__name__)


class GeminiNotConfigured(RuntimeError):
    pass


PART_LABELS = {
    "part1": "Part 1 (Introduction and Interview)",
    "part2": "Part 2 (Individual Long Turn / Cue Card)",
    "part3": "Part 3 (Two-way Discussion)",
    "full": "Full Mock Test — Part 1, then Part 2, then Part 3, in that order",
}

TOPIC_LABELS = {
    "random": "a topic of your own choosing, typical for IELTS Speaking",
    "hometown": "the student's hometown",
    "work_study": "the student's work or studies",
    "accommodation": "where the student lives",
    "family": "the student's family",
    "hobbies": "the student's hobbies and interests",
}


def _build_system_instruction(part: str, topic: str, target_level: str, practice_mode: str) -> str:
    part_desc = PART_LABELS.get(part, part)
    topic_desc = TOPIC_LABELS.get(topic, topic)
    if practice_mode == "guided_practice":
        coaching = (
            "You may briefly (one short sentence) point out a clear grammar or vocabulary mistake "
            "right after the student's answer, then continue with the next question."
        )
    else:
        coaching = (
            "Do not interrupt or correct the student during the conversation — behave exactly like a "
            "real IELTS examiner: ask questions, listen, and move on. Save all feedback for after the test."
        )
    return f"""You are Assel, a friendly but professional IELTS Speaking examiner conducting {part_desc}.
Topic focus: {topic_desc}. The student is aiming for Band {target_level}.

Rules:
- Speak only in English, at a natural pace appropriate for a Band {target_level} candidate.
- Ask ONE question at a time and wait for the student's full answer before continuing.
- Follow the real IELTS Speaking structure for this part:
  - Part 1: ask 3-4 short, everyday questions about the topic.
  - Part 2: give the student a cue card (topic + 3-4 bullet points to cover), tell them they have \
1 minute to think and up to 2 minutes to speak, then stay quiet while they talk.
  - Part 3: ask 3-4 deeper, more abstract discussion questions related to the Part 2 topic.
  - Full Mock Test: run Part 1 first, then Part 2, then Part 3, in that order, without stopping.
- {coaching}
- Keep your own turns short — you are the examiner, not the one being tested.
- When you have asked all the questions for this part (or all parts, for Full Mock Test), say a short \
closing line thanking the student and telling them the test is complete. Do not grade or score the \
student yourself — a separate process handles that afterwards.
"""


async def run_live_relay(
    client_ws: WebSocket, part: str, topic: str, target_level: str, practice_mode: str
) -> list[dict]:
    """Релеит аудио между браузером и Gemini Live, пока сессия не завершится.

    Возвращает накопленный транскрипт [{"speaker": "user"|"ai", "text": ...}, ...]
    в порядке появления реплик.
    """
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY не задан в .env. Получить бесплатный ключ: https://aistudio.google.com/apikey"
        )

    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=_build_system_instruction(part, topic, target_level, practice_mode),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(),
        ),
    )

    transcript: list[dict] = []

    async with client.aio.live.connect(model=GEMINI_LIVE_MODEL, config=config) as session:
        # У Live API нет отдельной команды "говори первым" — просим об этом обычным
        # текстовым ходом, чтобы экзаменатор сам поздоровался и задал первый вопрос.
        await session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text="(begin the test now with a short greeting and your first question)")],
            ),
            turn_complete=True,
        )

        async def pump_client_to_gemini() -> None:
            while True:
                message = await client_ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                data = message.get("bytes")
                if data:
                    await session.send_realtime_input(audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000"))
                    continue
                text = message.get("text")
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except ValueError:
                    continue
                if payload.get("type") == "finish":
                    return

        async def pump_gemini_to_client() -> None:
            async for response in session.receive():
                if response.data:
                    await client_ws.send_bytes(response.data)
                content = response.server_content
                if not content:
                    continue
                if content.input_transcription and content.input_transcription.text:
                    entry = {"speaker": "user", "text": content.input_transcription.text}
                    transcript.append(entry)
                    await client_ws.send_json({"type": "transcript", **entry})
                if content.output_transcription and content.output_transcription.text:
                    entry = {"speaker": "ai", "text": content.output_transcription.text}
                    transcript.append(entry)
                    await client_ws.send_json({"type": "transcript", **entry})

        # Останавливаемся, как только одна из сторон закончила (клиент нажал "Завершить"/
        # отключился, либо стрим от Gemini оборвался) — вторую задачу отменяем, а не ждём,
        # иначе `async for response in session.receive()` может зависнуть без новых сообщений.
        task_client = asyncio.create_task(pump_client_to_gemini())
        task_gemini = asyncio.create_task(pump_gemini_to_client())
        try:
            done, pending = await asyncio.wait({task_client, task_gemini}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    raise exc
        except WebSocketDisconnect:
            pass

    return transcript


_SCORE_PROMPT_TEMPLATE = """You are an IELTS Speaking examiner writing an official-style band score report.
Below is the transcript of a Speaking Practice session — {part_desc}, topic: {topic_desc}, \
student's target band: {target_level}.

Transcript (each line is one turn, "student" or "examiner"):
{transcript_text}

If the transcript is empty or far too short to judge (e.g. the student barely said anything), do NOT \
invent a score — return 0 for every criterion and overall_band, and an honest summary_feedback (in \
Russian) explaining that there wasn't enough speech to assess, and inviting the student to try again \
and speak more.

Otherwise, score the STUDENT's speech only (ignore the examiner's lines) on the 4 official IELTS \
Speaking criteria, each on a 0-9 scale in 0.5 steps:
- fluency_coherence: Fluency and Coherence
- lexical_resource: Lexical Resource
- grammar_accuracy: Grammar Range and Accuracy
- pronunciation: Pronunciation — you only have a TEXT transcript, not audio, so estimate this \
cautiously from indirect signs (self-corrections, filler words, broken sentences as transcribed) \
rather than true acoustic pronunciation; do not overstate confidence in this one criterion.

overall_band = average of the 4 criteria, rounded to the nearest 0.5 (standard IELTS rounding).
summary_feedback: 3-5 sentences in Russian, friendly and constructive — what went well and what to \
improve, with concrete examples from the transcript where possible.

Respond STRICTLY as JSON, no markdown wrapper:
{{"fluency_coherence": 0-9, "lexical_resource": 0-9, "grammar_accuracy": 0-9, "pronunciation": 0-9, \
"overall_band": 0-9, "summary_feedback": "..."}}
"""


async def score_speaking_session(transcript: list[dict], part: str, topic: str, target_level: str) -> dict:
    if not GEMINI_API_KEY:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY не задан в .env. Получить бесплатный ключ: https://aistudio.google.com/apikey"
        )

    transcript_text = "\n".join(
        f"{'student' if turn['speaker'] == 'user' else 'examiner'}: {turn['text']}" for turn in transcript
    )
    prompt = _SCORE_PROMPT_TEMPLATE.format(
        part_desc=PART_LABELS.get(part, part),
        topic_desc=TOPIC_LABELS.get(topic, topic),
        target_level=target_level,
        transcript_text=transcript_text or "(пусто — студент ничего не сказал)",
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    # Без явного timeout запрос к Gemini может зависнуть без ответа и без ошибки —
    # см. аналогичный комментарий в backend/services/gemini.py.
    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            http_options=types.HttpOptions(timeout=25000),
        ),
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
