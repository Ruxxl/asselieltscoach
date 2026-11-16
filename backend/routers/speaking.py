import json
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_user
from backend.database import get_session
from backend.models import SpeakingSession, SpeakingTopic
from backend.schemas import (
    SpeakingAnswerResult,
    SpeakingEstimateResult,
    SpeakingHelpResult,
    SpeakingImproveResult,
    SpeakingSpeakRequest,
    SpeakingSpeakResult,
    SpeakingStartRequest,
    SpeakingStartResult,
    SpeakingStep,
    SpeakingStepRequest,
    SpeakingTopicPublicOut,
)
from backend.services.speaking import (
    GeminiNotConfigured,
    build_question_help,
    check_answer,
    estimate_answer,
    improve_answer,
    spoken_question,
)
from backend.services.tts import synthesize_b64

router = APIRouter(prefix="/api/speaking", tags=["speaking"])

# Меньше слов — оценивать и улучшать нечего: честнее попросить ответить подробнее.
_MIN_WORDS_TO_ASSESS = 4


def topic_questions(topic: SpeakingTopic) -> list[str]:
    """Вопросы темы: из questions_json, а у старых тем с одним вопросом — question_text."""
    if topic.questions_json:
        questions = json.loads(topic.questions_json)
        if questions:
            return questions
    return [] if topic.part == "part2" else [topic.question_text]


def build_steps(topic: SpeakingTopic) -> list[dict]:
    """Part 1 — вопросы темы по одному; Part 2 — карточка, а за ней вопросы Part 3 к ней."""
    questions = topic_questions(topic)
    if topic.part == "part2":
        return [{"kind": "part2", "question": topic.question_text}] + [
            {"kind": "part3", "question": q} for q in questions
        ]
    return [{"kind": "part1", "question": q} for q in questions]


def _load_steps(speaking_session: SpeakingSession) -> list[dict]:
    return json.loads(speaking_session.transcript_json) if speaking_session.transcript_json else []


async def _get_own_session(session: AsyncSession, session_id: int, user_id: int) -> SpeakingSession:
    speaking_session = await session.get(SpeakingSession, session_id)
    if not speaking_session or speaking_session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return speaking_session


def _step(steps: list[dict], index: int) -> dict:
    if index < 0 or index >= len(steps):
        raise HTTPException(status_code=400, detail="Нет такого вопроса")
    return steps[index]


def _ai_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GeminiNotConfigured):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Ошибка ИИ: {exc}")


def _answered_step(steps: list[dict], index: int) -> dict:
    step = _step(steps, index)
    if step.get("on_topic") is False:
        raise HTTPException(status_code=400, detail="Ответ был не по теме вопроса — ответь на сам вопрос.")
    answer = (step.get("answer") or "").strip()
    if len(answer.split()) < _MIN_WORDS_TO_ASSESS:
        raise HTTPException(status_code=400, detail="Сначала запиши ответ на этот вопрос — подробнее, чем пара слов.")
    return step


@router.get("/topics", response_model=list[SpeakingTopicPublicOut])
async def list_speaking_topics(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(SpeakingTopic).where(SpeakingTopic.is_active == True).order_by(SpeakingTopic.order)  # noqa: E712
    )
    return [
        SpeakingTopicPublicOut(
            id=t.id,
            title=t.title,
            part=t.part or "part1",
            category=t.category or "other",
            question_count=len(build_steps(t)),
        )
        for t in rows.scalars().all()
    ]


@router.post("/start", response_model=SpeakingStartResult)
async def start_session(
    body: SpeakingStartRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    topic = await session.get(SpeakingTopic, body.topic_id)
    if not topic or not topic.is_active:
        raise HTTPException(status_code=400, detail="Тема не найдена")
    steps = build_steps(topic)
    if not steps:
        raise HTTPException(status_code=400, detail="В теме пока нет вопросов")

    speaking_session = SpeakingSession(
        user_id=user.id,
        part=topic.part or "part1",
        status="active",
        topic_id=topic.id,
        topic_title=topic.title,
        topic_question=topic.question_text,
        transcript_json=json.dumps(steps, ensure_ascii=False),
    )
    session.add(speaking_session)
    await session.commit()
    await session.refresh(speaking_session)
    return SpeakingStartResult(
        session_id=speaking_session.id,
        topic_title=topic.title,
        part=speaking_session.part,
        steps=[SpeakingStep(index=i, **s) for i, s in enumerate(steps)],
    )


# Вводные фразы преподавателя перед следующим вопросом — чтобы звучало как живой урок, а не как робот.
_LEADS = ("Okay, next question.", "Good. Let's move on.", "Alright, here's another one.", "Great. Next one.")


def _teacher_line(steps: list[dict], index: int, topic_title: str | None, mode: str) -> str:
    step = steps[index]
    question = spoken_question(step["question"])
    if mode == "repeat":
        return question
    if index == 0:
        if step["kind"] == "part2":
            return f"Hello! Let's practise Part 2. Here is your topic card. {question}"
        return f"Hello! Let's talk about {topic_title or 'this topic'}. {question}"
    if step["kind"] == "part3" and steps[index - 1]["kind"] == "part2":
        return f"Thank you. Now let's discuss the topic a little more. {question}"
    return f"{_LEADS[index % len(_LEADS)]} {question}"


@router.post("/{session_id}/speak", response_model=SpeakingSpeakResult)
async def speak_question(
    session_id: int,
    body: SpeakingSpeakRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Преподаватель задаёт вопрос голосом (с вводной фразой) или повторяет его по кнопке."""
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await _get_own_session(session, session_id, user.id)
    steps = _load_steps(speaking_session)
    _step(steps, body.index)
    text = _teacher_line(steps, body.index, speaking_session.topic_title, body.mode)
    return SpeakingSpeakResult(text=text, audio_b64=await synthesize_b64(text))


@router.post("/{session_id}/help", response_model=SpeakingHelpResult)
async def question_help(
    session_id: int,
    body: SpeakingStepRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Кнопки «Подсказка» (5-6 опорных фраз) и «Готовый ответ» — по запросу, ответ кэшируется в сессии."""
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await _get_own_session(session, session_id, user.id)
    steps = _load_steps(speaking_session)
    step = _step(steps, body.index)
    if step.get("help"):
        return SpeakingHelpResult(**step["help"])
    try:
        result = await build_question_help(step["kind"], step["question"])
    except Exception as exc:
        raise _ai_error(exc) from exc
    step["help"] = result
    speaking_session.transcript_json = json.dumps(steps, ensure_ascii=False)
    await session.commit()
    return SpeakingHelpResult(**result)


@router.post("/{session_id}/answer", response_model=SpeakingAnswerResult)
async def submit_answer(
    session_id: int,
    audio: UploadFile,
    index: Annotated[int, Form()],
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Голосовой ответ ученика: расшифровка + грамматический разбор (только грамматика и темы для повторения)."""
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await _get_own_session(session, session_id, user.id)
    steps = _load_steps(speaking_session)
    step = _step(steps, index)

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Пустой аудиофайл")
    # MediaRecorder на iOS пишет audio/mp4, на Android/десктопе — audio/webm;codecs=opus;
    # Gemini нужен голый MIME без параметров кодека.
    mime_type = (audio.content_type or "audio/webm").split(";")[0]
    try:
        result = await check_answer(step["kind"], step["question"], audio_bytes, mime_type)
    except Exception as exc:
        raise _ai_error(exc) from exc

    step["answer"] = result["student_said"]
    step["on_topic"] = result["on_topic"]
    step["teacher_say"] = result["teacher_say"]
    step["corrections"] = result["corrections"]
    step["review_topics"] = result["review_topics"]
    step.pop("estimate", None)  # ответ новый — прежние оценка и улучшение к нему не относятся
    step.pop("improved", None)
    speaking_session.transcript_json = json.dumps(steps, ensure_ascii=False)
    await session.commit()
    return SpeakingAnswerResult(**result, audio_b64=await synthesize_b64(result["teacher_say"]))


@router.post("/{session_id}/estimate", response_model=SpeakingEstimateResult)
async def estimate(
    session_id: int,
    body: SpeakingStepRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Кнопка «Примерная оценка»: 4 критерия IELTS Speaking по ответу ученика."""
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await _get_own_session(session, session_id, user.id)
    steps = _load_steps(speaking_session)
    step = _answered_step(steps, body.index)
    if step.get("estimate"):
        return SpeakingEstimateResult(**step["estimate"])
    try:
        result = await estimate_answer(step["kind"], step["question"], step["answer"])
    except Exception as exc:
        raise _ai_error(exc) from exc
    step["estimate"] = result
    speaking_session.transcript_json = json.dumps(steps, ensure_ascii=False)
    await session.commit()
    return SpeakingEstimateResult(**result)


@router.post("/{session_id}/improve", response_model=SpeakingImproveResult)
async def improve(
    session_id: int,
    body: SpeakingStepRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Кнопка «Улучшить мой ответ»: тот же ответ, но на 1-1.5 балла выше (на основе слов ученика)."""
    user = await require_user(session, x_telegram_init_data)
    speaking_session = await _get_own_session(session, session_id, user.id)
    steps = _load_steps(speaking_session)
    step = _answered_step(steps, body.index)
    if step.get("improved"):
        return SpeakingImproveResult(**step["improved"])
    try:
        result = await improve_answer(step["kind"], step["question"], step["answer"])
    except Exception as exc:
        raise _ai_error(exc) from exc
    step["improved"] = result
    speaking_session.transcript_json = json.dumps(steps, ensure_ascii=False)
    await session.commit()
    return SpeakingImproveResult(**result)
