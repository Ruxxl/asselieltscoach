"""Перекодировка голосовых из чата в OGG/Opus — формат, который Telegram Bot API
принимает как настоящее голосовое сообщение (send_voice), а не файл-вложение.

Браузер (особенно Safari/iOS внутри Telegram) пишет через MediaRecorder в webm/mp4,
не в ogg/opus напрямую — перекодируем на сервере через ffmpeg. Если бинаря ffmpeg
нет в окружении, транскодинг мягко не удаётся (возвращаем False), и вызывающий код
отправляет исходный файл как обычный документ вместо голосового — деградация без падения.
"""

import asyncio
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


async def transcode_to_ogg_opus(src_path: Path, dst_path: Path) -> bool:
    if not FFMPEG_AVAILABLE:
        logger.warning("ffmpeg не найден в PATH — голосовое из чата уйдёт преподавателю обычным файлом")
        return False

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(src_path), "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", str(dst_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not dst_path.exists():
        logger.warning("ffmpeg не смог перекодировать %s: %s", src_path, stderr.decode(errors="replace")[-500:])
        return False
    return True
