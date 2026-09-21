"""Точка входа для отдельного Render-сервиса, который держит только голосового
ИИ-экзаменатора Speaking Practice (см. backend/services/speaking_agent.py).

Раньше этот воркер был встроен в тот же процесс, что и FastAPI + Telegram-бот — вместе
с livekit-agents/onnxruntime/Gemini SDK он не помещался в 512MB free-инстанса Render
и падал по OOM прямо во время звонка. Теперь это отдельный Render Web Service (см.
render.yaml), со своим набором переменных окружения (LIVEKIT_*, DEEPGRAM_API_KEY,
GROQ_API_KEY, GEMINI_API_KEY, SPEAKING_API_BASE_URL, AGENT_CALLBACK_SECRET) — результат
звонка он отправляет обратно основному сервису HTTP-запросом, не пишет в БД напрямую
(у него нет доступа к её файлу на диске основного сервиса).

Запуск: python -m backend.agent_worker (см. startCommand в render.yaml).
"""

import asyncio
import logging

from backend.services.speaking_agent import is_configured, server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not is_configured:
        raise RuntimeError(
            "Speaking agent worker: не заданы LIVEKIT_URL/LIVEKIT_API_KEY/LIVEKIT_API_SECRET/"
            "DEEPGRAM_API_KEY/GROQ_API_KEY — нечего запускать."
        )
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
