import asyncio
import logging
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import select

from backend.config import BOT_TOKEN, TEACHER_USERNAME, UPLOADS_DIR, WEBAPP_URL
from backend.database import SessionLocal
from backend.models import AppSettings, ChatMessage, NewsPost

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router_dp = Dispatcher()

# Один и тот же Bot-инстанс используется и для polling (main()), и для отправки
# сообщений из backend-роутеров (backend/services/telegram_notify.py) — отправка
# не требует активного polling, поэтому это безопасно и на инстансах с
# DISABLE_BOT_POLLING=1 (см. backend/main.py).
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None


def _webapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Открыть Assel IELTS", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )


@router_dp.message(CommandStart())
async def on_start(message: Message) -> None:
    if not WEBAPP_URL.startswith("https://"):
        await message.answer(
            "⚠️ WEBAPP_URL в .env ещё не настроен на реальный https-домен — "
            "кнопка мини-приложения будет недоступна, пока не укажете хостинг."
        )
        return
    await message.answer(
        "Привет! Я Ассель — помогу подготовиться к IELTS.\n"
        "Всё обучение, тесты и голосовая проверка Reading — в мини-приложении ниже.",
        reply_markup=_webapp_keyboard(),
    )


@router_dp.message(F.text == "/app")
async def on_app(message: Message) -> None:
    await on_start(message)


def _is_teacher(message: Message) -> bool:
    username = (message.from_user.username or "") if message.from_user else ""
    return username.lower() == TEACHER_USERNAME.lower()


async def _remember_teacher_chat_id(message: Message) -> None:
    """Username преподавателя задан в конфиге, но numeric chat_id для отправки
    уведомлений Bot API заранее не даёт узнать — резолвим его тем, что он сам
    хоть раз напишет боту (например /start)."""
    if not message.from_user:
        return
    async with SessionLocal() as session:
        settings = await session.get(AppSettings, 1)
        if not settings:
            session.add(AppSettings(id=1, teacher_chat_id=message.from_user.id))
        elif settings.teacher_chat_id != message.from_user.id:
            settings.teacher_chat_id = message.from_user.id
        await session.commit()


@router_dp.message(Command("news"))
async def on_news(message: Message, command: CommandObject) -> None:
    if not _is_teacher(message):
        return  # тихо игнорируем посторонних — не выдаём, что команда вообще существует
    await _remember_teacher_chat_id(message)
    text = (command.args or "").strip()
    if not text:
        await message.answer("Формат: /news текст новости")
        return
    async with SessionLocal() as session:
        session.add(NewsPost(text=text))
        await session.commit()
    await message.answer("Опубликовано ✅")


@router_dp.message(F.reply_to_message)
async def on_teacher_reply(message: Message) -> None:
    if not _is_teacher(message):
        return
    await _remember_teacher_chat_id(message)

    voice_path = None
    if message.voice:
        UPLOADS_DIR.mkdir(exist_ok=True)
        dest = UPLOADS_DIR / f"{uuid.uuid4().hex}.ogg"
        await bot.download(message.voice, destination=dest)
        voice_path = str(dest)
    text = message.text or message.caption
    if not text and not voice_path:
        return  # стикер/фото и т.п. — нечего пересылать ученику

    async with SessionLocal() as session:
        result = await session.execute(
            select(ChatMessage).where(ChatMessage.telegram_message_id == message.reply_to_message.message_id)
        )
        original = result.scalar_one_or_none()
        if not original:
            await message.answer("Не нашёл, к какому ученику относится это сообщение.")
            return
        student_id = original.user_id
        session.add(ChatMessage(user_id=student_id, sender="teacher", text=text, voice_path=voice_path))
        await session.commit()

    try:
        if voice_path:
            await bot.send_voice(student_id, FSInputFile(voice_path), caption="✉️ Голосовое от преподавателя")
        else:
            await bot.send_message(student_id, f"✉️ Ответ от преподавателя:\n\n{text}")
    except Exception:
        logger.exception("Не удалось отправить ответ преподавателя ученику %s", student_id)


@router_dp.message()
async def on_other_message(message: Message) -> None:
    if _is_teacher(message):
        await _remember_teacher_chat_id(message)
        await message.answer(
            "Чтобы опубликовать новость: /news текст.\n"
            "Чтобы ответить ученику: сделай Reply прямо на моё уведомление с его вопросом."
        )
        return
    await message.answer(
        "Напиши мне через раздел «Преподаватель» в приложении 👇",
        reply_markup=_webapp_keyboard(),
    )


async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан в .env")
    await router_dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
