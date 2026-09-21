import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_user
from backend.config import (
    AGENT_CALLBACK_SECRET,
    DEEPGRAM_API_KEY,
    GROQ_API_KEY,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_URL,
    SPEAKING_AGENT_NAME,
)
from backend.database import get_session
from backend.models import SpeakingSession
from backend.schemas import SpeakingReportIn, SpeakingSessionOut, SpeakingStartRequest, SpeakingStartResult

router = APIRouter(prefix="/api/speaking", tags=["speaking"])

_VALID_PARTS = {"part1", "part2", "part3"}

# Голосовой агент-воркер — отдельный сервис (см. backend/agent_worker.py и
# backend/config.py); этот роутер НЕ импортирует backend.services.speaking_agent, чтобы
# не тянуть в основной процесс livekit-agents/onnxruntime и не повторять OOM.
_agent_configured = bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET and DEEPGRAM_API_KEY and GROQ_API_KEY)


@router.post("/start", response_model=SpeakingStartResult)
async def start_session(
    body: SpeakingStartRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    if body.part not in _VALID_PARTS:
        raise HTTPException(status_code=400, detail="Неизвестная часть теста")
    if not _agent_configured:
        raise HTTPException(
            status_code=503,
            detail="Голосовой агент не настроен (нет LIVEKIT_*/DEEPGRAM_API_KEY/GROQ_API_KEY в .env).",
        )

    speaking_session = SpeakingSession(user_id=user.id, part=body.part)
    session.add(speaking_session)
    await session.commit()
    await session.refresh(speaking_session)

    # Имя комнаты кодирует id сессии и часть теста — агент (backend/services/speaking_agent.py)
    # разбирает их обратно из ctx.room.name, без отдельного канала метаданных.
    room_name = f"speaking-{speaking_session.id}-{body.part}"
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(f"student-{user.id}")
        .with_name(user.full_name or user.username or "Student")
        .with_grants(api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True))
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=SPEAKING_AGENT_NAME)]))
        .to_jwt()
    )

    return SpeakingStartResult(session_id=speaking_session.id, livekit_url=LIVEKIT_URL, token=token)


@router.get("/{session_id}", response_model=SpeakingSessionOut)
async def get_session_report(
    session_id: int,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await session.get(SpeakingSession, session_id)
    if not speaking_session or speaking_session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return speaking_session


@router.post("/{session_id}/report", include_in_schema=False)
async def receive_agent_report(
    session_id: int,
    body: SpeakingReportIn,
    x_agent_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Callback от отдельного сервиса-агента (backend/agent_worker.py) с результатом
    звонка — не для браузера, поэтому авторизация через общий секрет, а не initData."""
    if not AGENT_CALLBACK_SECRET or x_agent_secret != AGENT_CALLBACK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    speaking_session = await session.get(SpeakingSession, session_id)
    if not speaking_session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    speaking_session.transcript_json = json.dumps(body.transcript, ensure_ascii=False)
    if body.error:
        speaking_session.status = "error"
        speaking_session.error_message = body.error
    else:
        speaking_session.status = "done"
        speaking_session.fluency_coherence = body.fluency_coherence
        speaking_session.lexical_resource = body.lexical_resource
        speaking_session.grammar_accuracy = body.grammar_accuracy
        speaking_session.pronunciation = body.pronunciation
        speaking_session.overall_band = body.overall_band
        speaking_session.summary_feedback = body.summary_feedback
        speaking_session.finished_at = datetime.utcnow()
    await session.commit()
    return {"ok": True}
