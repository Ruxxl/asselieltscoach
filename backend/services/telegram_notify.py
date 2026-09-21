"""Отправка ученических сообщений чата преподавателю (TEACHER_CHAT_ID) в Telegram +
запоминание message_id уведомления, чтобы бот потом нашёл нужного ученика по
Reply-ответу преподавателя (см. bot/main.py::on_teacher_reply)."""

import logging
from pathlib import Path

from aiogram.types import FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import TEACHER_CHAT_ID
from backend.models import ChatMessage, User

logger = logging.getLogger(__name__)


def _student_label(user: User) -> str:
    name = user.full_name or user.username or f"id{user.id}"
    handle = f" (@{user.username})" if user.username else ""
    return f"{name}{handle}"


async def notify_teacher_text(session: AsyncSession, user: User, text: str) -> ChatMessage:
    msg = ChatMessage(user_id=user.id, sender="student", text=text)
    session.add(msg)
    await session.flush()

    from bot.main import bot as tg_bot  # локальный импорт — избегаем цикла backend<->bot при старте

    if tg_bot:
        try:
            sent = await tg_bot.send_message(TEACHER_CHAT_ID, f"✉️ {_student_label(user)}:\n\n{text}")
            msg.telegram_message_id = sent.message_id
        except Exception:
            logger.exception("Не удалось отправить уведомление преподавателю (текст)")

    await session.commit()
    return msg


async def notify_teacher_voice(session: AsyncSession, user: User, voice_path: Path, is_real_voice: bool) -> ChatMessage:
    msg = ChatMessage(user_id=user.id, sender="student", voice_path=str(voice_path))
    session.add(msg)
    await session.flush()

    from bot.main import bot as tg_bot

    if tg_bot:
        try:
            caption = f"🎤 Голосовое от {_student_label(user)}"
            if is_real_voice:
                sent = await tg_bot.send_voice(TEACHER_CHAT_ID, FSInputFile(voice_path), caption=caption)
            else:
                sent = await tg_bot.send_document(TEACHER_CHAT_ID, FSInputFile(voice_path), caption=caption)
            msg.telegram_message_id = sent.message_id
        except Exception:
            logger.exception("Не удалось отправить уведомление преподавателю (голос)")

    await session.commit()
    return msg
