import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.config import BOT_TOKEN, DISABLE_BOT_POLLING, WEBAPP_DIR
from backend.database import SessionLocal, init_db
from backend.routers import admin, chat, courses, lessons, news, reading_test, speaking
from backend.seed_data import seed_if_empty

logger = logging.getLogger(__name__)


async def _run_bot_forever() -> None:
    # Render free tier не даёт отдельный background worker, поэтому бот
    # поллит Telegram внутри того же процесса, что и веб-сервер.
    from bot.main import main as run_bot

    try:
        await run_bot()
    except Exception:
        logger.exception("Bot polling stopped unexpectedly")


async def _run_speaking_agent_forever() -> None:
    # Та же причина, что и у бота выше: LiveKit Agents-воркер живёт в этом же процессе,
    # а не отдельным Render-сервисом. job_executor_type=THREAD (см. speaking_agent.py)
    # держит job'ы внутри процесса, а не в отдельных подпроцессах.
    from backend.services.speaking_agent import server

    try:
        await server.run()
    except Exception:
        logger.exception("Speaking agent worker stopped unexpectedly")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as session:
        await seed_if_empty(session)

    from backend.services.speaking_agent import is_configured as speaking_agent_configured

    bot_task = asyncio.create_task(_run_bot_forever()) if BOT_TOKEN and not DISABLE_BOT_POLLING else None
    agent_task = asyncio.create_task(_run_speaking_agent_forever()) if speaking_agent_configured else None
    try:
        yield
    finally:
        if bot_task:
            bot_task.cancel()
        if agent_task:
            agent_task.cancel()


app = FastAPI(title="Assel IELTS API", lifespan=lifespan)

app.include_router(courses.router)
app.include_router(lessons.router)
app.include_router(reading_test.router)
app.include_router(news.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(speaking.router)


@app.get("/api/ping")
async def ping():
    # Точка для внешнего keep-alive пинга, чтобы Render free-инстанс не засыпал.
    return {"status": "ok"}

# Мини-приложение отдаём тем же сервером на "/" — тот же домен, что и /api,
# так что запросы из WebApp не упираются в CORS.
app.mount("/", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")
