import re
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_user
from backend.config import GRAMMAR_DAILY_LIMIT
from backend.database import get_session
from backend.schemas import (
    GrammarChatRequest,
    GrammarCheckOut,
    GrammarCheckRequest,
    GrammarDocxRequest,
    GrammarTransformRequest,
    WritingTextOut,
)
from backend.services.grammar import (
    AI_LANGUAGES,
    CONTEXTS,
    TARGET_LEVELS,
    TEXT_LANGUAGES,
    TRANSFORMS,
    chat_about_text,
    check_text,
    transform_text,
)
from backend.services.writing import GeminiNotConfigured

router = APIRouter(prefix="/api/grammar", tags=["grammar"])

_MAX_TEXT_CHARS = 8000

# Проверки грамматики не храним (текст живёт на устройстве ученика), поэтому и лимит считаем в памяти
# процесса: после рестарта Render он обнуляется — для защиты квоты Gemini этого достаточно.
_checks_by_user: dict[int, deque] = defaultdict(deque)


def _ai_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GeminiNotConfigured):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Ошибка ИИ: {exc}")


def _clean_text(text: str) -> str:
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустой текст")
    if len(text) > _MAX_TEXT_CHARS:
        raise HTTPException(status_code=400, detail=f"Текст длиннее {_MAX_TEXT_CHARS} символов — раздели его на части")
    return text


def _take_daily_slot(user_id: int) -> None:
    now, window = time.time(), _checks_by_user[user_id]
    while window and now - window[0] > 86400:
        window.popleft()
    if len(window) >= GRAMMAR_DAILY_LIMIT:
        raise HTTPException(status_code=429, detail=f"Лимит {GRAMMAR_DAILY_LIMIT} проверок в сутки исчерпан")
    window.append(now)


@router.post("/check", response_model=GrammarCheckOut)
async def check(
    body: GrammarCheckRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    text = _clean_text(body.text)
    if (
        body.text_language not in TEXT_LANGUAGES
        or body.ai_language not in AI_LANGUAGES
        or body.context not in CONTEXTS
        or body.target not in TARGET_LEVELS
        or body.mode not in {"student", "teacher"}
    ):
        raise HTTPException(status_code=400, detail="Неверные настройки проверки")
    _take_daily_slot(user.id)
    try:
        return await check_text(
            text=text,
            text_language=body.text_language,
            ai_language=body.ai_language,
            mode=body.mode,
            context=body.context,
            target=body.target,
            explanations=body.explanations,
            detailed=body.detailed,
            use_context=body.use_context,
        )
    except Exception as exc:
        _checks_by_user[user.id].pop()  # неудачная проверка лимит не тратит
        raise _ai_error(exc) from exc


@router.post("/transform", response_model=WritingTextOut)
async def transform(
    body: GrammarTransformRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_user(session, x_telegram_init_data)
    if body.action not in TRANSFORMS or body.context not in CONTEXTS or body.target not in TARGET_LEVELS:
        raise HTTPException(status_code=400, detail="Неизвестное действие")
    try:
        text = await transform_text(
            text=_clean_text(body.text),
            action=body.action,
            context=body.context,
            target=body.target,
            full_text=(body.full_text or "")[:_MAX_TEXT_CHARS] or None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _ai_error(exc) from exc
    if not text:
        raise HTTPException(status_code=502, detail="ИИ вернул пустой текст — попробуй ещё раз")
    return WritingTextOut(text=text)


@router.post("/chat", response_model=WritingTextOut)
async def chat(
    body: GrammarChatRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_user(session, x_telegram_init_data)
    message = body.message.strip()[:1500]
    if not message:
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    if body.ai_language not in AI_LANGUAGES:
        raise HTTPException(status_code=400, detail="Неверный язык")
    try:
        reply = await chat_about_text(
            text=body.text[:_MAX_TEXT_CHARS],
            issues=[i.model_dump() for i in body.issues],
            history=[t.model_dump() for t in body.history],
            message=message,
            ai_language=body.ai_language,
        )
    except Exception as exc:
        raise _ai_error(exc) from exc
    return WritingTextOut(text=reply)


@router.post("/docx")
async def send_docx(
    body: GrammarDocxRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Как и в Writing Checker, файл присылает бот в чат — скачивание из мини-аппа работает не везде."""
    user = await require_user(session, x_telegram_init_data)
    text = _clean_text(body.text)
    issues = [i.model_dump() for i in body.result.issues if 0 <= i.start < i.end <= len(text)]
    if any(text[i["start"] : i["end"]] != i["original"] for i in issues):
        raise HTTPException(status_code=400, detail="Текст изменился после проверки — проверь его заново")

    from aiogram.types import BufferedInputFile

    from bot.main import bot
    from backend.services.grammar_docx import build_report

    if not bot:
        raise HTTPException(status_code=503, detail="Бот не настроен — отправить файл некому")
    filename = re.sub(r"[^\w\- ]+", "", body.filename, flags=re.UNICODE).strip()[:60] or "Grammar_Check"
    author = body.author.strip()[:60] or "Assel AI"
    data = build_report(text=text, issues=issues, result=body.result.model_dump(), author=author)
    try:
        await bot.send_document(
            chat_id=user.id,
            document=BufferedInputFile(data, filename=f"{filename}.docx"),
            caption=f"Проверка текста · {len(issues)} правок",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Не удалось отправить файл: {exc}") from exc
    return {"status": "sent"}
