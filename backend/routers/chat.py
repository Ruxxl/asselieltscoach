import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_user
from backend.config import TEACHER_USERNAME, UPLOADS_DIR
from backend.database import get_session
from backend.models import ChatMessage
from backend.schemas import ChatMessageOut
from backend.services.audio import transcode_to_ogg_opus
from backend.services.telegram_notify import notify_teacher_text, notify_teacher_voice
from backend.telegram_auth import parse_init_data

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _to_out(msg: ChatMessage) -> ChatMessageOut:
    out = ChatMessageOut.model_validate(msg)
    if msg.voice_path:
        out.voice_url = f"/api/chat/voice/{msg.id}"
    return out


@router.get("/messages", response_model=list[ChatMessageOut])
async def list_messages(
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    result = await session.execute(
        select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at.asc())
    )
    return [_to_out(m) for m in result.scalars().all()]


@router.post("/messages", response_model=ChatMessageOut)
async def send_message(
    text: str | None = Form(default=None),
    voice: UploadFile | None = File(default=None),
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)

    if voice is not None:
        voice_bytes = await voice.read()
        if not voice_bytes:
            raise HTTPException(status_code=400, detail="Пустой аудиофайл")
        UPLOADS_DIR.mkdir(exist_ok=True)
        raw_path = UPLOADS_DIR / f"{uuid.uuid4().hex}_raw"
        raw_path.write_bytes(voice_bytes)
        ogg_path = UPLOADS_DIR / f"{uuid.uuid4().hex}.ogg"
        is_real_voice = await transcode_to_ogg_opus(raw_path, ogg_path)
        final_path = ogg_path if is_real_voice else raw_path
        msg = await notify_teacher_voice(session, user, final_path, is_real_voice)
        return _to_out(msg)

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    msg = await notify_teacher_text(session, user, text.strip())
    return _to_out(msg)


@router.get("/voice/{message_id}")
async def get_voice(
    message_id: int,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    msg = await session.get(ChatMessage, message_id)
    if not msg or not msg.voice_path:
        raise HTTPException(status_code=404, detail="Голосовое не найдено")

    # Доступ — только сам ученик (владелец сообщения) или преподаватель.
    tg_user = parse_init_data(x_telegram_init_data)
    is_teacher = bool(tg_user) and (tg_user.get("username") or "").lower() == TEACHER_USERNAME.lower()
    is_owner = bool(tg_user) and tg_user.get("id") == msg.user_id
    if not (is_teacher or is_owner):
        raise HTTPException(status_code=403, detail="Нет доступа")

    path = Path(msg.voice_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path)
