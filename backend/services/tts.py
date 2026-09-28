"""Озвучка реплик экзаменатора Speaking Practice через Deepgram Aura-2 (тот же голос, что был
в live-версии). Платно по факту ($0.03 / 1000 символов), но на пилот покрывается бесплатным
стартовым кредитом Deepgram ($200). Если ключа нет или Deepgram не ответил — возвращаем None,
и фронтенд озвучивает текст встроенным в телефон speechSynthesis.
"""

import base64
import logging

import aiohttp

from backend.config import DEEPGRAM_API_KEY, DEEPGRAM_TTS_MODEL

logger = logging.getLogger(__name__)

_SPEAK_URL = "https://api.deepgram.com/v1/speak"
# Лимит Deepgram на один запрос — 2000 символов; реплики экзаменатора намного короче.
_MAX_CHARS = 2000


async def synthesize_b64(text: str) -> str | None:
    """mp3 в base64 (для <audio src="data:audio/mpeg;base64,...">) или None, если не вышло."""
    if not DEEPGRAM_API_KEY or not text.strip():
        return None
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                _SPEAK_URL,
                params={"model": DEEPGRAM_TTS_MODEL, "encoding": "mp3"},
                headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
                json={"text": text[:_MAX_CHARS]},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Deepgram TTS failed with %s: %s", resp.status, await resp.text())
                    return None
                return base64.b64encode(await resp.read()).decode("ascii")
    except Exception:
        logger.exception("Deepgram TTS request failed")
        return None
