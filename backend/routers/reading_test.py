import uuid

from fastapi import APIRouter, Depends, Form, Header, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import UPLOADS_DIR
from backend.database import get_session
from backend.models import TestAnswer, TestAttempt, User
from backend.schemas import ReadingCheckResult
from backend.services.gemini import GeminiNotConfigured, grade_reading_answer
from backend.telegram_auth import parse_init_data

router = APIRouter(prefix="/api/test", tags=["test"])


async def _get_or_create_user(session: AsyncSession, init_data: str | None) -> User | None:
    tg_user = parse_init_data(init_data)
    if not tg_user:
        return None
    user = await session.get(User, tg_user["id"])
    if not user:
        user = User(
            id=tg_user["id"],
            username=tg_user.get("username"),
            full_name=" ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])),
        )
        session.add(user)
        await session.commit()
    return user


@router.post("/reading-check", response_model=ReadingCheckResult)
async def reading_check(
    audio: UploadFile,
    question: str = Form(...),
    reference_text: str = Form(...),
    kind: str = Form("final"),  # "final" (курс) или "placement" (быстрый тест)
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Пустой аудиофайл")

    mime_type = audio.content_type or "audio/webm"

    try:
        result = await grade_reading_answer(audio_bytes, mime_type, reference_text, question)
    except GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # ошибка самого API Gemini / неподдерживаемый формат аудио
        raise HTTPException(status_code=502, detail=f"Ошибка проверки ИИ: {exc}") from exc

    UPLOADS_DIR.mkdir(exist_ok=True)
    audio_path = UPLOADS_DIR / f"{uuid.uuid4().hex}.webm"
    audio_path.write_bytes(audio_bytes)

    user = await _get_or_create_user(session, x_telegram_init_data)
    attempt = TestAttempt(user_id=user.id if user else None, kind=kind)
    session.add(attempt)
    await session.flush()
    session.add(
        TestAnswer(
            attempt_id=attempt.id,
            skill="reading",
            question_text=question,
            reference_text=reference_text,
            audio_path=str(audio_path),
            transcript=result["transcript"],
            is_correct=result["is_correct"],
            accuracy_score=result["accuracy_score"],
            ai_feedback=result["feedback"],
        )
    )
    await session.commit()

    return result
