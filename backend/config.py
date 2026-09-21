import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Только для локальной разработки: не запускать поллинг бота в этом процессе,
# чтобы не конфликтовать с уже поллящим прод-инстансом на Render (тот же токен —
# Telegram разрешает только один активный getUpdates на бота). BOT_TOKEN при этом
# остаётся настоящим, так как он же нужен для проверки подписи initData.
DISABLE_BOT_POLLING = os.environ.get("DISABLE_BOT_POLLING", "") == "1"
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
# Live-модель для потокового голосового разговора (Speaking Practice) — отдельная от
# GEMINI_MODEL, т.к. это другое семейство моделей (двусторонний аудио-стрим через Live API).
GEMINI_LIVE_MODEL = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.8-live")
# Numeric Telegram id преподавателя (не username — id не меняется). Определяет доступ
# к админке, /news в боте, и куда слать уведомления о сообщениях учеников в чате
# "Преподаватель". Узнать свой id можно, например, у @userinfobot.
TEACHER_CHAT_ID = int(os.environ.get("TEACHER_CHAT_ID", "998292747"))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR}/assel_ielts.db")
WEBAPP_DIR = BASE_DIR / "webapp"
UPLOADS_DIR = BASE_DIR / "uploads"
