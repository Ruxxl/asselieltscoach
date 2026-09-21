"""Speaking Practice: живой голосовой ИИ-экзаменатор через LiveKit Agents.

Архитектура (в отличие от прежней попытки на Gemini Live API, которую в этом проекте
дважды пришлось откатывать из-за квот preview/live-моделей — см. память сессии):
LiveKit Cloud (бесплатный Build-тариф) для WebRTC-транспорта и определения конца фразы,
Deepgram (free $200 credit) для STT+TTS, Groq (free tier) для LLM-мозга экзаменатора.
Все три — обычные стабильные API с бесплатными тирами без карты, не preview/live.

Воркер встроен в тот же процесс, что и FastAPI + Telegram-бот (backend/main.py),
по той же причине, что и бот: Render free tier не даёт отдельный background worker.
job_executor_type=THREAD (вместо дефолтного PROCESS) — чтобы не плодить подпроцессы
на ограниченной памяти free-инстанса Render.
"""

import json
import logging
import re
from datetime import datetime

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobExecutorType
from livekit.plugins import deepgram, groq, silero

from backend.config import DEEPGRAM_API_KEY, GROQ_API_KEY, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL
from backend.database import SessionLocal
from backend.models import SpeakingSession
from backend.services.speaking import build_examiner_instructions, score_session

logger = logging.getLogger(__name__)

AGENT_NAME = "assel-examiner"
_ROOM_RE = re.compile(r"^speaking-(\d+)-(part[123])$")

is_configured = bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET and DEEPGRAM_API_KEY and GROQ_API_KEY)

server = AgentServer(
    ws_url=LIVEKIT_URL or None,
    api_key=LIVEKIT_API_KEY or None,
    api_secret=LIVEKIT_API_SECRET or None,
    job_executor_type=JobExecutorType.THREAD,
    num_idle_processes=0,
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


async def _finalize_session(session_id: int, part: str, session: AgentSession) -> None:
    """Считает финальную оценку и сохраняет результат — вызывается, когда звонок завершён
    (комната опустела/закрылась). Отдельный обычный текстовый запрос к Gemini, тот же
    надёжный паттерн, что и раньше в пошаговой версии — здесь live-часть только собирает
    транскрипт, оценка всегда посчитана одним стабильным запросом."""
    transcript = _extract_transcript(session)
    async with SessionLocal() as db_session:
        speaking_session = await db_session.get(SpeakingSession, session_id)
        if not speaking_session:
            logger.warning("Speaking agent: session %s not found when finalizing", session_id)
            return
        speaking_session.transcript_json = json.dumps(transcript, ensure_ascii=False)
        try:
            result = await score_session(transcript, part)
        except Exception:
            logger.exception("Speaking agent: scoring failed for session %s", session_id)
            speaking_session.status = "error"
            speaking_session.error_message = "Не удалось получить оценку ИИ."
            await db_session.commit()
            return

        speaking_session.status = "done"
        speaking_session.fluency_coherence = result["fluency_coherence"]
        speaking_session.lexical_resource = result["lexical_resource"]
        speaking_session.grammar_accuracy = result["grammar_accuracy"]
        speaking_session.pronunciation = result["pronunciation"]
        speaking_session.overall_band = result["overall_band"]
        speaking_session.summary_feedback = result["summary_feedback"]
        speaking_session.finished_at = datetime.utcnow()
        await db_session.commit()


@server.rtc_session(agent_name=AGENT_NAME)
async def speaking_entrypoint(ctx: JobContext) -> None:
    match = _ROOM_RE.match(ctx.room.name)
    if not match:
        logger.warning("Speaking agent dispatched to unexpected room name: %s", ctx.room.name)
        return
    session_id, part = int(match.group(1)), match.group(2)

    await ctx.connect()

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(model="nova-3", language="en-US"),
        llm=groq.LLM(model="llama-3.3-70b-versatile"),
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
