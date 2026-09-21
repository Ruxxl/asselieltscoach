"""Speaking Practice: живой голосовой ИИ-экзаменатор через LiveKit Agents.

Архитектура (в отличие от прежней попытки на Gemini Live API, которую в этом проекте
дважды пришлось откатывать из-за квот preview/live-моделей — см. память сессии):
LiveKit Cloud (бесплатный Build-тариф) для WebRTC-транспорта и определения конца фразы,
Deepgram (free $200 credit) для STT+TTS, Groq (free tier) для LLM-мозга экзаменатора.
Все три — обычные стабильные API с бесплатными тирами без карты, не preview/live.

Воркер запускается ОТДЕЛЬНЫМ Render-сервисом (см. backend/agent_worker.py), не встроен в
процесс с ботом/FastAPI — вместе с Gemini SDK и остальным стеком он не помещался в 512MB
free-инстанса Render и падал по OOM прямо во время звонка (подтверждено в логах Render:
"Ran out of memory (used over 512MB)"). Раз это отдельный процесс на отдельном диске, у него
нет доступа к SQLite основного сервиса — результат звонка отправляется обратно HTTP-запросом
(см. AGENT_CALLBACK_SECRET / SPEAKING_API_BASE_URL и backend/routers/speaking.py).
job_executor_type=THREAD (вместо дефолтного PROCESS) — чтобы не плодить подпроцессы на
ограниченной памяти free-инстанса.
"""

import logging
import os
import re

import aiohttp
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobExecutorType
from livekit.plugins import deepgram, groq, silero

from backend.config import (
    AGENT_CALLBACK_SECRET,
    DEEPGRAM_API_KEY,
    GROQ_API_KEY,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_URL,
    SPEAKING_AGENT_NAME,
    SPEAKING_API_BASE_URL,
)
from backend.services.speaking import build_examiner_instructions, score_session

logger = logging.getLogger(__name__)

_ROOM_RE = re.compile(r"^speaking-(\d+)-(part[123])$")

is_configured = bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET and DEEPGRAM_API_KEY and GROQ_API_KEY)

server = AgentServer(
    ws_url=LIVEKIT_URL or None,
    api_key=LIVEKIT_API_KEY or None,
    api_secret=LIVEKIT_API_SECRET or None,
    job_executor_type=JobExecutorType.THREAD,
    num_idle_processes=0,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8081)),
)


def _extract_transcript(session: AgentSession) -> list[dict]:
    # session.history.items может содержать не только ChatMessage (реплики), но и служебные
    # записи вроде AgentHandoff/FunctionCall без .role — getattr вместо item.role, чтобы их
    # просто пропустить, а не упасть с AttributeError.
    transcript = []
    for item in session.history.items:
        role = getattr(item, "role", None)
        if role not in ("user", "assistant"):
            continue
        text = getattr(item, "text_content", None)
        if not text:
            continue
        transcript.append({"speaker": "user" if role == "user" else "ai", "text": text})
    return transcript


async def _post_report(session_id: int, payload: dict) -> None:
    if not SPEAKING_API_BASE_URL or not AGENT_CALLBACK_SECRET:
        logger.error(
            "Speaking agent: SPEAKING_API_BASE_URL/AGENT_CALLBACK_SECRET not configured, "
            "cannot report result for session %s",
            session_id,
        )
        return
    url = f"{SPEAKING_API_BASE_URL.rstrip('/')}/api/speaking/{session_id}/report"
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                url, json=payload, headers={"X-Agent-Secret": AGENT_CALLBACK_SECRET}, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status >= 400:
                    logger.error(
                        "Speaking agent: report callback for session %s failed with %s: %s",
                        session_id,
                        resp.status,
                        await resp.text(),
                    )
    except Exception:
        logger.exception("Speaking agent: report callback failed for session %s", session_id)


async def _finalize_session(session_id: int, part: str, session: AgentSession) -> None:
    """Считает финальную оценку и шлёт результат обратно основному сервису — вызывается,
    когда звонок завершён (комната опустела/закрылась). Отдельный обычный текстовый запрос
    к Gemini, тот же надёжный паттерн, что и раньше в пошаговой версии — здесь live-часть
    только собирает транскрипт, оценка всегда посчитана одним стабильным запросом."""
    transcript = _extract_transcript(session)
    try:
        result = await score_session(transcript, part)
    except Exception:
        logger.exception("Speaking agent: scoring failed for session %s", session_id)
        await _post_report(session_id, {"transcript": transcript, "error": "Не удалось получить оценку ИИ."})
        return

    await _post_report(session_id, {"transcript": transcript, **result})


@server.rtc_session(agent_name=SPEAKING_AGENT_NAME)
async def speaking_entrypoint(ctx: JobContext) -> None:
    match = _ROOM_RE.match(ctx.room.name)
    if not match:
        logger.warning("Speaking agent dispatched to unexpected room name: %s", ctx.room.name)
        return
    session_id, part = int(match.group(1)), match.group(2)

    await ctx.connect()

    session = AgentSession(
        # sample_rate=8000 (вместо дефолтных 16000) — вдвое меньше сэмплов на кадр для VAD,
        # заметно снижает нагрузку на CPU. На free-инстансе Render (0.1 vCPU) полноразмерный
        # VAD не успевал в реальном времени ("VAD inference is slower than realtime" в логах);
        # звонок всё равно отрабатывал корректно, но определение конца фразы запаздывало.
        vad=silero.VAD.load(sample_rate=8000),
        stt=deepgram.STT(model="nova-3", language="en-US"),
        # llama-3.3-70b-versatile был снят с продакшена в Groq (модель периодически меняется —
        # если этот тоже перестанет резолвиться, актуальный список: GET
        # https://api.groq.com/openai/v1/models с твоим ключом).
        llm=groq.LLM(model="openai/gpt-oss-120b"),
        tts=deepgram.TTS(model="aura-2-asteria-en"),
    )

    async def _on_shutdown(_reason: str = "") -> None:
        try:
            await _finalize_session(session_id, part, session)
        except Exception:
            logger.exception("Speaking agent: unhandled error finalizing session %s", session_id)

    ctx.add_shutdown_callback(_on_shutdown)

    await session.start(agent=Agent(instructions=build_examiner_instructions(part)), room=ctx.room)
    await session.generate_reply(
        instructions="Greet the student in one short friendly sentence and ask what topic they'd like to talk about today."
    )
