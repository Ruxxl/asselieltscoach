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
# Только для локальной разработки в обычном браузере (без Telegram): запросы без initData
# считаются от этого пользователя. На проде НЕ задавать — иначе любой аноним станет этим юзером.
DEV_USER_ID = int(os.environ.get("DEV_USER_ID", "0"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
# Numeric Telegram id преподавателя (не username — id не меняется). Определяет доступ
# к админке и к /news в боте. Узнать свой id можно, например, у @userinfobot.
TEACHER_CHAT_ID = int(os.environ.get("TEACHER_CHAT_ID", "998292747"))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR}/assel_ielts.db")
WEBAPP_DIR = BASE_DIR / "webapp"
UPLOADS_DIR = BASE_DIR / "uploads"

# Озвучка реплик ИИ-экзаменатора Speaking Practice (backend/services/tts.py). Без ключа
# фронтенд озвучивает встроенным в телефон голосом.
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
DEEPGRAM_TTS_MODEL = os.environ.get("DEEPGRAM_TTS_MODEL", "aura-2-pandora-en")  # британский женский голос

# Writing Checker (backend/routers/writing.py): сколько эссе один ученик может проверить за сутки —
# защищает бесплатную квоту Gemini от одного слишком активного пользователя.
WRITING_DAILY_LIMIT = int(os.environ.get("WRITING_DAILY_LIMIT", "20"))
# Модель для Writing Checker отдельно от Speaking: длинный разбор эссе на русском/казахском
# заметно грамотнее у моделей мощнее flash-lite, а скорость тут важна меньше, чем в диалоге.
WRITING_GEMINI_MODEL = os.environ.get("WRITING_GEMINI_MODEL", "gemini-3.5-flash")
# Grammar Checker (backend/routers/grammar.py): проверок в сутки на ученика; считается в памяти процесса.
GRAMMAR_DAILY_LIMIT = int(os.environ.get("GRAMMAR_DAILY_LIMIT", "40"))

# Оплата курсов через Halyk ePay — платёжная страница банка (redirect), см. backend/services/halyk.py.
# Карта вводится только на стороне Halyk, поэтому PCI DSS не нужен. Пока не заданы все три
# значения, покупка курса работает как раньше — мгновенно, без списания (пилот).
HALYK_CLIENT_ID = os.environ.get("HALYK_CLIENT_ID", "")
HALYK_CLIENT_SECRET = os.environ.get("HALYK_CLIENT_SECRET", "")
HALYK_TERMINAL_ID = os.environ.get("HALYK_TERMINAL_ID", "")
# "1" — тестовый контур банка (test-epay...), "0" — боевой. По умолчанию тест, чтобы боевые
# ключи случайно не ушли в тестовые адреса и наоборот — переключать явно при запуске продаж.
HALYK_TEST_MODE = os.environ.get("HALYK_TEST_MODE", "1") == "1"
HALYK_ENABLED = bool(HALYK_CLIENT_ID and HALYK_CLIENT_SECRET and HALYK_TERMINAL_ID)

# Google Таблица как постоянная копия учеников, покупок, платежей и прогресса (backend/services/sheets.py):
# URL веб-приложения Apps Script (sheets/apps_script.gs) и пароль, вписанный в SECRET этого скрипта.
SHEETS_WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL", "")
SHEETS_SECRET = os.environ.get("SHEETS_SECRET", "")
SHEETS_ENABLED = bool(SHEETS_WEBHOOK_URL and SHEETS_SECRET)
