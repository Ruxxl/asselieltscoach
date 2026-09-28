import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_user
from backend.database import get_session
from backend.models import SpeakingSession, SpeakingTopic
from backend.schemas import (
    SpeakingHelpRequest,
    SpeakingHelpResult,
    SpeakingSessionOut,
    SpeakingStartRequest,
    SpeakingStartResult,
    SpeakingTopicPublicOut,
    SpeakingTurnResult,
)
from backend.services.speaking import (
    GeminiNotConfigured,
    build_corrected_report,
    build_question_help,
    continue_conversation,
    score_session,
    start_conversation,
)
from backend.services.tts import synthesize_b64

router = APIRouter(prefix="/api/speaking", tags=["speaking"])

_VALID_PARTS = {"part1", "part2", "part3"}


def _load_history(speaking_session: SpeakingSession) -> list[dict]:
    return json.loads(speaking_session.transcript_json) if speaking_session.transcript_json else []


async def _get_own_session(session: AsyncSession, session_id: int, user_id: int) -> SpeakingSession:
    speaking_session = await session.get(SpeakingSession, session_id)
    if not speaking_session or speaking_session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return speaking_session


def _session_out(speaking_session: SpeakingSession) -> SpeakingSessionOut:
    out = SpeakingSessionOut.model_validate(speaking_session)
    if speaking_session.improvement_comments_json:
        out.improvement_comments = json.loads(speaking_session.improvement_comments_json)
    return out


@router.get("/topics", response_model=list[SpeakingTopicPublicOut])
async def list_speaking_topics(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(SpeakingTopic).where(SpeakingTopic.is_active == True).order_by(SpeakingTopic.order)  # noqa: E712
    )
    return rows.scalars().all()


@router.post("/start", response_model=SpeakingStartResult)
async def start_session(
    body: SpeakingStartRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    if body.part not in _VALID_PARTS:
        raise HTTPException(status_code=400, detail="Неизвестная часть теста")

    topic: SpeakingTopic | None = None
    if body.part == "part1":
        if body.topic_id is None:
            raise HTTPException(status_code=400, detail="Выбери тему для Part 1")
        topic = await session.get(SpeakingTopic, body.topic_id)
        if not topic or not topic.is_active:
            raise HTTPException(status_code=400, detail="Тема не найдена")
    elif body.topic_id is not None:
        raise HTTPException(status_code=400, detail="topic_id поддерживается только для Part 1")

    topic_question = topic.question_text if topic else None
    try:
        opening = await start_conversation(body.part, topic_question)
    except GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка ИИ: {exc}") from exc

    speaking_session = SpeakingSession(
        user_id=user.id,
        part=body.part,
        topic_id=topic.id if topic else None,
        topic_title=topic.title if topic else None,
        topic_question=topic_question,
        transcript_json=json.dumps([{"speaker": "ai", "text": opening["ai_message"]}], ensure_ascii=False),
    )
    session.add(speaking_session)
    await session.commit()
    await session.refresh(speaking_session)

    return SpeakingStartResult(
        session_id=speaking_session.id, **opening, audio_b64=await synthesize_b64(opening["ai_message"])
    )


@router.post("/{session_id}/turn", response_model=SpeakingTurnResult)
async def submit_turn(
    session_id: int,
    audio: UploadFile,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await _get_own_session(session, session_id, user.id)
    if speaking_session.status != "active":
        raise HTTPException(status_code=400, detail="Эта сессия уже завершена")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Пустой аудиофайл")
    # MediaRecorder на iOS пишет audio/mp4, на Android/десктопе — audio/webm;codecs=opus;
    # Gemini нужен голый MIME без параметров кодека.
    mime_type = (audio.content_type or "audio/webm").split(";")[0]

    history = _load_history(speaking_session)
    try:
        result = await continue_conversation(
            speaking_session.part, speaking_session.topic_question, history, audio_bytes, mime_type
        )
    except GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка ИИ: {exc}") from exc

    history.append({"speaker": "user", "text": result["student_said"], "correction": result["correction"]})
    history.append({"speaker": "ai", "text": result["ai_message"]})
    speaking_session.transcript_json = json.dumps(history, ensure_ascii=False)
    await session.commit()

    return SpeakingTurnResult(**result, audio_b64=await synthesize_b64(result["ai_message"]))


@router.post("/{session_id}/help", response_model=SpeakingHelpResult)
async def question_help(
    session_id: int,
    body: SpeakingHelpRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Кнопки "Подсказка"/"Пример ответа" у карточки вопроса — генерим по запросу, а не на
    каждый ход, чтобы не замедлять ответ экзаменатора."""
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await _get_own_session(session, session_id, user.id)
    question = body.question.strip()[:500]
    if not question:
        raise HTTPException(status_code=400, detail="Пустой вопрос")
    try:
        return SpeakingHelpResult(**await build_question_help(speaking_session.part, question))
    except GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка ИИ: {exc}") from exc


@router.post("/{session_id}/finish", response_model=SpeakingSessionOut)
async def finish_session(
    session_id: int,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Итог: для всех частей — 4 балла IELTS, отзыв и советы; Part 1 (с темой) дополнительно —
    исправленная версия ответа."""
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await _get_own_session(session, session_id, user.id)
    if speaking_session.status == "done":
        return _session_out(speaking_session)

    history = _load_history(speaking_session)
    try:
        if speaking_session.part == "part1":
            scores, corrected = await asyncio.gather(
                score_session(history, speaking_session.part),
                build_corrected_report(history, speaking_session.topic_question),
            )
        else:
            scores, corrected = await score_session(history, speaking_session.part), None
    except Exception as exc:
        speaking_session.status = "error"
        speaking_session.error_message = "Не удалось получить оценку ИИ."
        await session.commit()
        raise HTTPException(status_code=502, detail="Не удалось получить оценку ИИ.") from exc

    speaking_session.status = "done"
    speaking_session.fluency_coherence = scores["fluency_coherence"]
    speaking_session.lexical_resource = scores["lexical_resource"]
    speaking_session.grammar_accuracy = scores["grammar_accuracy"]
    speaking_session.pronunciation = scores["pronunciation"]
    speaking_session.overall_band = scores["overall_band"]
    speaking_session.summary_feedback = scores["summary_feedback"]
    speaking_session.improvement_comments_json = json.dumps(scores["tips"], ensure_ascii=False)
    if corrected:
        speaking_session.corrected_answer = corrected["corrected_answer"]
    speaking_session.finished_at = datetime.utcnow()
    await session.commit()
    return _session_out(speaking_session)


@router.get("/{session_id}", response_model=SpeakingSessionOut)
async def get_session_report(
    session_id: int,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    return _session_out(await _get_own_session(session, session_id, user.id))
