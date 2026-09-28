import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from backend.config import BOT_TOKEN, TEACHER_CHAT_ID, WEBAPP_URL
from backend.database import SessionLocal
from backend.models import NewsPost

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router_dp = Dispatcher()

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
    return bool(message.from_user and message.from_user.id == TEACHER_CHAT_ID)


@router_dp.message(Command("news"))
async def on_news(message: Message, command: CommandObject) -> None:
    if not _is_teacher(message):
        return  # тихо игнорируем посторонних — не выдаём, что команда вообще существует
    text = (command.args or "").strip()
    if not text:
        await message.answer("Формат: /news текст новости")
        return
    async with SessionLocal() as session:
        session.add(NewsPost(text=text))
        await session.commit()
    await message.answer("Опубликовано ✅")


@router_dp.message()
async def on_other_message(message: Message) -> None:
    if _is_teacher(message):
        await message.answer("Чтобы опубликовать новость: /news текст.")
        return
    await message.answer(
        "Всё обучение и практика — в мини-приложении ниже 👇",
        reply_markup=_webapp_keyboard(),
    )


async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан в .env")
    await router_dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
