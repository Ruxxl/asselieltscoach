from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import require_user
from backend.database import get_session
from backend.models import Course, CoursePurchase, Lesson, Module
from backend.schemas import AnswerCheckRequest, AnswerCheckResult, LessonDetail, QuestionOut

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


async def _get_lesson_with_relations(lesson_id: int, session: AsyncSession) -> Lesson:
    result = await session.execute(
        select(Lesson)
        .options(
            selectinload(Lesson.questions),
            selectinload(Lesson.module),
        )
        .where(Lesson.id == lesson_id)
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Урок не найден")
    return lesson


async def _get_course_for_module(module_id: int, session: AsyncSession) -> Course:
    result = await session.execute(select(Course).where(Course.modules.any(id=module_id)))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Курс урока не найден")
    return course


async def _is_preview_module(module_id: int, course_id: int, session: AsyncSession) -> bool:
    """Первый по порядку модуль курса — бесплатный предпросмотр, доступен без покупки."""
    result = await session.execute(
        select(Module.id).where(Module.course_id == course_id).order_by(Module.order).limit(1)
    )
    return result.scalar_one_or_none() == module_id


async def _require_lesson_access(
    lesson: Lesson, course: Course, session: AsyncSession, init_data: str | None
) -> None:
    """Реальная проверка на сервере: предпросмотр — всем, остальные уроки — только купившим курс."""
    if await _is_preview_module(lesson.module_id, course.id, session):
        return
    user = await require_user(session, init_data)
    owned = await session.execute(
        select(CoursePurchase.id).where(CoursePurchase.user_id == user.id, CoursePurchase.course_id == course.id)
    )
    if not owned.first():
        raise HTTPException(
            status_code=403, detail="Курс не куплен. Купи его в каталоге, чтобы открыть остальные уроки."
        )


@router.get("/{lesson_id}", response_model=LessonDetail)
async def get_lesson(
    lesson_id: int,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    lesson = await _get_lesson_with_relations(lesson_id, session)
    course = await _get_course_for_module(lesson.module_id, session)
    await _require_lesson_access(lesson, course, session, x_telegram_init_data)

    siblings_result = await session.execute(
        select(Lesson.id, Lesson.order).where(Lesson.module_id == lesson.module_id).order_by(Lesson.order)
    )
    siblings = siblings_result.all()
    ids_in_order = [s.id for s in siblings]
    position = ids_in_order.index(lesson.id) + 1
    prev_id = ids_in_order[position - 2] if position > 1 else None
    next_id = ids_in_order[position] if position < len(ids_in_order) else None

    return LessonDetail(
        id=lesson.id,
        title=lesson.title,
        subtitle=lesson.subtitle,
        content=lesson.content.split("\n\n"),
        course_code=course.code,
        module_title=lesson.module.title,
        position=position,
        total_in_module=len(ids_in_order),
        prev_lesson_id=prev_id,
        next_lesson_id=next_id,
        questions=[
            QuestionOut(order=q.order, prompt=q.prompt, options=q.options.split("|")) for q in lesson.questions
        ],
    )


@router.post("/{lesson_id}/check", response_model=AnswerCheckResult)
async def check_lesson_answers(
    lesson_id: int,
    payload: AnswerCheckRequest,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    lesson = await _get_lesson_with_relations(lesson_id, session)
    course = await _get_course_for_module(lesson.module_id, session)
    await _require_lesson_access(lesson, course, session, x_telegram_init_data)

    if len(payload.answers) != len(lesson.questions):
        raise HTTPException(status_code=400, detail="Количество ответов не совпадает с количеством вопросов")

    results = [
        given.strip().lower() == q.correct_option.strip().lower()
        for given, q in zip(payload.answers, lesson.questions)
    ]
    return AnswerCheckResult(correct_count=sum(results), total=len(results), results=results)
