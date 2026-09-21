from fastapi import APIRouter, Depends, Header, HTTPException
from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_user
from backend.config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL
from backend.database import get_session
from backend.models import SpeakingSession
from backend.schemas import SpeakingSessionOut, SpeakingStartRequest, SpeakingStartResult
from backend.services.speaking_agent import AGENT_NAME, is_configured

router = APIRouter(prefix="/api/speaking", tags=["speaking"])

_VALID_PARTS = {"part1", "part2", "part3"}


@router.post("/start", response_model=SpeakingStartResult)
async def start_session(
    body: SpeakingStartRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    if body.part not in _VALID_PARTS:
        raise HTTPException(status_code=400, detail="Неизвестная часть теста")
    if not is_configured:
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
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]))
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
