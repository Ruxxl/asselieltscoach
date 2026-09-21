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
# Numeric Telegram id преподавателя (не username — id не меняется). Определяет доступ
# к админке, /news в боте, и куда слать уведомления о сообщениях учеников в чате
# "Преподаватель". Узнать свой id можно, например, у @userinfobot.
TEACHER_CHAT_ID = int(os.environ.get("TEACHER_CHAT_ID", "998292747"))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR}/assel_ielts.db")
WEBAPP_DIR = BASE_DIR / "webapp"
UPLOADS_DIR = BASE_DIR / "uploads"

# Live-голосовой ИИ-экзаменатор для Speaking Practice (backend/services/speaking_agent.py,
# backend/agent_worker.py): LiveKit Cloud (free Build tier) для WebRTC-транспорта + Deepgram
# ($200 free credit, STT+TTS) + Groq (free tier LLM) — вместо Gemini Live/preview-моделей,
# которые дважды подводили квотами в этом проекте (см. память сессии). Все три — бесплатные
# тиры без карты.
#
# Агент-воркер работает КАК ОТДЕЛЬНЫЙ Render-сервис (backend/agent_worker.py), не встроен в
# основной процесс с ботом — вместе с FastAPI/aiogram/Gemini SDK он не помещался в 512MB
# free-инстанса Render и падал по OOM прямо во время звонка (подтверждено в логах Render).
# Т.к. это отдельный процесс на отдельном диске, у него нет доступа к SQLite основного
# сервиса — результат звонка он отправляет обратно HTTP-запросом (см. AGENT_CALLBACK_SECRET
# и роутер backend/routers/speaking.py: POST /api/speaking/{id}/report).
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
# Только у основного сервиса: секрет, которым агент-воркер подписывает callback с отчётом.
AGENT_CALLBACK_SECRET = os.environ.get("AGENT_CALLBACK_SECRET", "")
# Только у агент-воркера: куда слать этот callback (публичный URL основного сервиса).
SPEAKING_API_BASE_URL = os.environ.get("SPEAKING_API_BASE_URL", "")
# Имя, под которым агент регистрируется в LiveKit (используется и при выдаче токена на
# основном сервисе, и в самом воркере) — общая константа, чтобы не завести опечатку в одном
# из двух мест.
SPEAKING_AGENT_NAME = "assel-examiner"
