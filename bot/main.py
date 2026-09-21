import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from backend.config import BOT_TOKEN, WEBAPP_URL

logging.basicConfig(level=logging.INFO)
router_dp = Dispatcher()


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


async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан в .env")
    bot = Bot(token=BOT_TOKEN)
    await router_dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
