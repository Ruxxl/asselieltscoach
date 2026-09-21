import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_user
from backend.database import get_session
from backend.models import SpeakingSession
from backend.schemas import SpeakingSessionOut, SpeakingStartRequest, SpeakingStartResult, SpeakingTurnResult
from backend.services.speaking import GeminiNotConfigured, continue_conversation, score_session, start_conversation

router = APIRouter(prefix="/api/speaking", tags=["speaking"])

_VALID_PARTS = {"part1", "part2", "part3"}


def _load_history(speaking_session: SpeakingSession) -> list[dict]:
    return json.loads(speaking_session.transcript_json) if speaking_session.transcript_json else []


@router.post("/start", response_model=SpeakingStartResult)
async def start_session(
    body: SpeakingStartRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    if body.part not in _VALID_PARTS:
        raise HTTPException(status_code=400, detail="Неизвестная часть теста")

    try:
        result = await start_conversation(body.part)
    except GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка ИИ: {exc}") from exc

    history = [{"speaker": "ai", "text": result["ai_message"]}]
    speaking_session = SpeakingSession(
        user_id=user.id, part=body.part, transcript_json=json.dumps(history, ensure_ascii=False)
    )
    session.add(speaking_session)
    await session.commit()
    await session.refresh(speaking_session)
    return SpeakingStartResult(session_id=speaking_session.id, ai_message=result["ai_message"])


@router.post("/{session_id}/turn", response_model=SpeakingTurnResult)
async def submit_turn(
    session_id: int,
    audio: UploadFile,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await session.get(SpeakingSession, session_id)
    if not speaking_session or speaking_session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if speaking_session.status != "active":
        raise HTTPException(status_code=400, detail="Эта сессия уже завершена")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Пустой аудиофайл")
    mime_type = audio.content_type or "audio/webm"

    history = _load_history(speaking_session)
    try:
        result = await continue_conversation(speaking_session.part, history, audio_bytes, mime_type)
    except GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка ИИ: {exc}") from exc

    history.append({"speaker": "user", "text": result["student_said"]})
    history.append({"speaker": "ai", "text": result["ai_message"]})
    speaking_session.transcript_json = json.dumps(history, ensure_ascii=False)
    if result["finished"]:
        speaking_session.status = "scoring"
    await session.commit()

    return SpeakingTurnResult(**result)


@router.post("/{session_id}/finish", response_model=SpeakingSessionOut)
async def finish_session(
    session_id: int,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await session.get(SpeakingSession, session_id)
    if not speaking_session or speaking_session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    if speaking_session.status == "done":
        return speaking_session

    history = _load_history(speaking_session)
    try:
        result = await score_session(history, speaking_session.part)
    except Exception as exc:
        speaking_session.status = "error"
        speaking_session.error_message = "Не удалось получить оценку ИИ."
        await session.commit()
        raise HTTPException(status_code=502, detail="Не удалось получить оценку ИИ.") from exc

    speaking_session.status = "done"
    speaking_session.fluency_coherence = result["fluency_coherence"]
    speaking_session.lexical_resource = result["lexical_resource"]
    speaking_session.grammar_accuracy = result["grammar_accuracy"]
    speaking_session.pronunciation = result["pronunciation"]
    speaking_session.overall_band = result["overall_band"]
    speaking_session.summary_feedback = result["summary_feedback"]
    speaking_session.finished_at = datetime.utcnow()
    await session.commit()
    return speaking_session


@router.get("/{session_id}", response_model=SpeakingSessionOut)
async def get_session_report(
    session_id: int,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await session.get(SpeakingSession, session_id)
    if not speaking_session or speaking_session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return speaking_session
