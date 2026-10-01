import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_user
from backend.config import WRITING_DAILY_LIMIT
from backend.database import get_session
from backend.models import WritingCheck
from backend.schemas import (
    WritingChatRequest,
    WritingCheckOut,
    WritingHistoryItem,
    WritingIdeasRequest,
    WritingSampleRequest,
    WritingTextOut,
)
from backend.services.writing import (
    LANGUAGES,
    TASK_TYPES,
    TONES,
    GeminiNotConfigured,
    brainstorm,
    chat_about_essay,
    check_essay,
    count_words,
    extract_text,
    generate_sample,
)

router = APIRouter(prefix="/api/writing", tags=["writing"])

_TARGET_BANDS = {"5.5-6.5", "7.0-8.0", "8.5-9.0"}
_MAX_ESSAY_CHARS = 8000
_MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _ai_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GeminiNotConfigured):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Ошибка ИИ: {exc}")


async def _read_image(upload: UploadFile | None) -> tuple[bytes, str] | None:
    if not upload or not upload.filename:
        return None
    mime = (upload.content_type or "").split(";")[0]
    if not mime.startswith("image/"):
        raise HTTPException(status_code=400, detail="Нужна картинка (фото или скриншот)")
    data = await upload.read()
    if not data:
        return None
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Картинка слишком большая (максимум 8 МБ)")
    return data, mime


def _check_out(check: WritingCheck) -> WritingCheckOut:
    return WritingCheckOut(
        id=check.id,
        task_type=check.task_type,
        mode=check.mode,
        language=check.language,
        target_band=check.target_band,
        topic=check.topic,
        essay=check.essay,
        created_at=check.created_at,
        result=json.loads(check.result_json),
        chat=json.loads(check.chat_json) if check.chat_json else [],
    )


async def _get_own_check(session: AsyncSession, check_id: int, user_id: int) -> WritingCheck:
    check = await session.get(WritingCheck, check_id)
    if not check or check.user_id != user_id:
        raise HTTPException(status_code=404, detail="Проверка не найдена")
    return check


@router.post("/check", response_model=WritingCheckOut)
async def check(
    essay: str = Form(...),
    topic: str = Form(""),
    task_type: str = Form("task2"),
    mode: str = Form("student"),
    language: str = Form("ru"),
    tone: str = Form("friendly"),
    target_band: str = Form("7.0-8.0"),
    ai_reasoning: bool = Form(True),
    improve_word_choice: bool = Form(False),
    detailed_feedback: bool = Form(True),
    sample_essay: bool = Form(True),
    image: UploadFile | None = File(default=None),
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    essay, topic = essay.strip(), topic.strip()[:2000]
    if task_type not in TASK_TYPES or mode not in {"student", "teacher"} or language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Неверные настройки проверки")
    if tone not in TONES or target_band not in _TARGET_BANDS:
        raise HTTPException(status_code=400, detail="Неверные настройки проверки")
    if count_words(essay) < 20:
        raise HTTPException(status_code=400, detail="Эссе слишком короткое — напиши хотя бы 20 слов")
    if len(essay) > _MAX_ESSAY_CHARS:
        raise HTTPException(status_code=400, detail="Текст слишком длинный для одного эссе")

    # Лимит бережёт бесплатную квоту Gemini, а не монетизирует: преподавателю его хватит с запасом.
    since = datetime.utcnow() - timedelta(days=1)
    used = await session.scalar(
        select(func.count(WritingCheck.id)).where(WritingCheck.user_id == user.id, WritingCheck.created_at >= since)
    )
    if used >= WRITING_DAILY_LIMIT:
        raise HTTPException(status_code=429, detail=f"Лимит {WRITING_DAILY_LIMIT} проверок в сутки исчерпан")

    try:
        result = await check_essay(
            task_type=task_type,
            topic=topic,
            essay=essay,
            language=language,
            mode=mode,
            tone=tone,
            target_band=target_band,
            ai_reasoning=ai_reasoning,
            improve_word_choice=improve_word_choice,
            detailed_feedback=detailed_feedback,
            sample_essay=sample_essay,
            image=await _read_image(image) if task_type == "task1_academic" else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _ai_error(exc) from exc

    if not result["assessable"]:
        # Не сохраняем и не списываем лимит — как и в Speaking, «пустая» попытка не оценивается.
        raise HTTPException(status_code=422, detail=result["summary"] or "Текст не похож на ответ на задание")

    row = WritingCheck(
        user_id=user.id,
        task_type=task_type,
        mode=mode,
        language=language,
        target_band=target_band,
        topic=topic,
        essay=essay,
        overall_band=result["overall_band"],
        result_json=json.dumps(result, ensure_ascii=False),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _check_out(row)


@router.get("/history", response_model=list[WritingHistoryItem])
async def history(x_telegram_init_data: str | None = Header(default=None), session: AsyncSession = Depends(get_session)):
    user = await require_user(session, x_telegram_init_data)
    rows = await session.execute(
        select(WritingCheck).where(WritingCheck.user_id == user.id).order_by(WritingCheck.id.desc()).limit(30)
    )
    return [
        WritingHistoryItem(
            id=c.id,
            task_type=c.task_type,
            topic=c.topic,
            overall_band=c.overall_band,
            word_count=count_words(c.essay),
            created_at=c.created_at,
        )
        for c in rows.scalars()
    ]


@router.get("/{check_id}", response_model=WritingCheckOut)
async def get_check(
    check_id: int, x_telegram_init_data: str | None = Header(default=None), session: AsyncSession = Depends(get_session)
):
    user = await require_user(session, x_telegram_init_data)
    return _check_out(await _get_own_check(session, check_id, user.id))


@router.post("/scan", response_model=WritingTextOut)
async def scan(
    image: UploadFile = File(...),
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_user(session, x_telegram_init_data)
    img = await _read_image(image)
    if not img:
        raise HTTPException(status_code=400, detail="Пустой файл")
    try:
        text = await extract_text(*img)
    except Exception as exc:
        raise _ai_error(exc) from exc
    if not text:
        raise HTTPException(status_code=422, detail="Не удалось распознать английский текст на фото")
    return WritingTextOut(text=text)


@router.post("/sample", response_model=WritingTextOut)
async def sample(
    body: WritingSampleRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_user(session, x_telegram_init_data)
    if body.task_type not in TASK_TYPES or body.target_band not in _TARGET_BANDS:
        raise HTTPException(status_code=400, detail="Неверные настройки")
    if not body.topic.strip():
        raise HTTPException(status_code=400, detail="Сначала впиши задание (тему или вопрос)")
    try:
        text = await generate_sample(
            task_type=body.task_type, topic=body.topic.strip()[:2000], target_band=body.target_band
        )
    except Exception as exc:
        raise _ai_error(exc) from exc
    return WritingTextOut(text=text)


@router.post("/ideas", response_model=WritingTextOut)
async def ideas(
    body: WritingIdeasRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_user(session, x_telegram_init_data)
    if body.task_type not in TASK_TYPES or body.language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Неверные настройки")
    if not body.topic.strip():
        raise HTTPException(status_code=400, detail="Сначала впиши задание (тему или вопрос)")
    try:
        text = await brainstorm(task_type=body.task_type, topic=body.topic.strip()[:2000], language=body.language)
    except Exception as exc:
        raise _ai_error(exc) from exc
    return WritingTextOut(text=text)


def _check_dict(check: WritingCheck) -> dict:
    return {
        "task_type": check.task_type,
        "topic": check.topic,
        "essay": check.essay,
        "language": check.language,
        "created_at": check.created_at,
        "result": json.loads(check.result_json),
    }


@router.post("/{check_id}/chat", response_model=WritingTextOut)
async def chat(
    check_id: int,
    body: WritingChatRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    check = await _get_own_check(session, check_id, user.id)
    message = body.message.strip()[:1500]
    if not message:
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    turns = json.loads(check.chat_json) if check.chat_json else []
    if len(turns) >= 60:
        raise HTTPException(status_code=429, detail="Чат по этому эссе слишком длинный — начни новую проверку")
    try:
        reply = await chat_about_essay(_check_dict(check), turns, message)
    except Exception as exc:
        raise _ai_error(exc) from exc
    turns += [{"role": "user", "text": message}, {"role": "ai", "text": reply}]
    check.chat_json = json.dumps(turns, ensure_ascii=False)
    await session.commit()
    return WritingTextOut(text=reply)


@router.post("/{check_id}/docx")
async def send_docx(
    check_id: int, x_telegram_init_data: str | None = Header(default=None), session: AsyncSession = Depends(get_session)
):
    """Отчёт .docx присылает бот в чат: скачивание файлов прямо из мини-аппа в Telegram
    работает не везде, а документ в чате открывается на любом устройстве."""
    user = await require_user(session, x_telegram_init_data)
    check = await _get_own_check(session, check_id, user.id)

    from aiogram.types import BufferedInputFile

    from bot.main import bot
    from backend.services.writing_docx import build_report

    if not bot:
        raise HTTPException(status_code=503, detail="Бот не настроен — отправить файл некому")
    data = _check_dict(check)
    try:
        await bot.send_document(
            chat_id=user.id,
            document=BufferedInputFile(build_report(data), filename=f"IELTS_Writing_{check.id}.docx"),
            caption=f"Отчёт о проверке эссе · Overall Band {check.overall_band:.1f}",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Не удалось отправить файл: {exc}") from exc
    return {"status": "sent"}
