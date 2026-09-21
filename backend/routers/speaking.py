import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_or_create_user, require_user
from backend.database import SessionLocal, get_session
from backend.models import SpeakingSession
from backend.schemas import SpeakingSessionOut, SpeakingStartRequest, SpeakingStartResult
from backend.services.speaking_live import GeminiNotConfigured, run_live_relay, score_speaking_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/speaking", tags=["speaking"])

_VALID_PARTS = {"part1", "part2", "part3", "full"}
_VALID_TOPICS = {"random", "hometown", "work_study", "accommodation", "family", "hobbies"}
_VALID_MODES = {"mock_test", "guided_practice"}


@router.post("/start", response_model=SpeakingStartResult)
async def start_session(
    body: SpeakingStartRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    if body.part not in _VALID_PARTS:
        raise HTTPException(status_code=400, detail="Неизвестная часть теста")
    if body.topic not in _VALID_TOPICS:
        raise HTTPException(status_code=400, detail="Неизвестная тема")
    if body.practice_mode not in _VALID_MODES:
        raise HTTPException(status_code=400, detail="Неизвестный режим практики")

    speaking_session = SpeakingSession(
        user_id=user.id,
        part=body.part,
        topic=body.topic,
        target_level=body.target_level,
        practice_mode=body.practice_mode,
    )
    session.add(speaking_session)
    await session.commit()
    await session.refresh(speaking_session)
    return SpeakingStartResult(session_id=speaking_session.id)


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


async def _safe_send_error(websocket: WebSocket, message: str) -> None:
    try:
        await websocket.send_json({"type": "error", "message": message})
    except Exception:
        pass


@router.websocket("/ws/{session_id}")
async def speaking_ws(websocket: WebSocket, session_id: int, init_data: str | None = None):
    # WebSocket из браузера не может послать кастомный заголовок X-Telegram-Init-Data —
    # передаём initData как query-параметр при подключении (см. webapp/index.html).
    await websocket.accept()

    async with SessionLocal() as db_session:
        user = await get_or_create_user(db_session, init_data)
        if not user:
            await websocket.close(code=4401, reason="unauthorized")
            return

        speaking_session = await db_session.get(SpeakingSession, session_id)
        if not speaking_session or speaking_session.user_id != user.id or speaking_session.status != "active":
            await websocket.close(code=4404, reason="session not found")
            return

        try:
            transcript = await run_live_relay(
                websocket,
                speaking_session.part,
                speaking_session.topic,
                speaking_session.target_level,
                speaking_session.practice_mode,
            )
        except GeminiNotConfigured as exc:
            await _safe_send_error(websocket, str(exc))
            speaking_session.status = "error"
            speaking_session.error_message = str(exc)
            await db_session.commit()
            await websocket.close(code=1011)
            return
        except Exception as exc:
            logger.exception("Speaking live relay failed")
            await _safe_send_error(websocket, "Соединение с ИИ прервалось. Попробуй начать заново.")
            speaking_session.status = "error"
            speaking_session.error_message = str(exc)
            await db_session.commit()
            await websocket.close(code=1011)
            return

        speaking_session.status = "scoring"
        speaking_session.transcript_json = json.dumps(transcript, ensure_ascii=False)
        await db_session.commit()

        try:
            result = await score_speaking_session(
                transcript, speaking_session.part, speaking_session.topic, speaking_session.target_level
            )
        except Exception:
            logger.exception("Speaking session scoring failed")
            speaking_session.status = "error"
            speaking_session.error_message = "Не удалось получить оценку ИИ."
            await db_session.commit()
            await _safe_send_error(
                websocket, "Разговор сохранён, но оценку получить не удалось. Попробуй открыть отчёт ещё раз позже."
            )
            await websocket.close(code=1011)
            return

        speaking_session.status = "done"
        speaking_session.fluency_coherence = result["fluency_coherence"]
        speaking_session.lexical_resource = result["lexical_resource"]
        speaking_session.grammar_accuracy = result["grammar_accuracy"]
        speaking_session.pronunciation = result["pronunciation"]
        speaking_session.overall_band = result["overall_band"]
        speaking_session.summary_feedback = result["summary_feedback"]
        speaking_session.finished_at = datetime.utcnow()
        await db_session.commit()

        try:
            await websocket.send_json({"type": "done"})
            await websocket.close(code=1000)
        except Exception:
            pass
