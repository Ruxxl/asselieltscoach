from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_session
from backend.models import Course, Lesson
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


@router.get("/{lesson_id}", response_model=LessonDetail)
async def get_lesson(lesson_id: int, session: AsyncSession = Depends(get_session)):
    lesson = await _get_lesson_with_relations(lesson_id, session)

    siblings_result = await session.execute(
        select(Lesson.id, Lesson.order).where(Lesson.module_id == lesson.module_id).order_by(Lesson.order)
    )
    siblings = siblings_result.all()
    ids_in_order = [s.id for s in siblings]
    position = ids_in_order.index(lesson.id) + 1
    prev_id = ids_in_order[position - 2] if position > 1 else None
    next_id = ids_in_order[position] if position < len(ids_in_order) else None

    course_result = await session.execute(
        select(Course.code).where(Course.modules.any(id=lesson.module_id))
    )
    course_code = course_result.scalar_one_or_none() or "?"

    return LessonDetail(
        id=lesson.id,
        title=lesson.title,
        subtitle=lesson.subtitle,
        content=lesson.content.split("\n\n"),
        course_code=course_code,
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
    lesson_id: int, payload: AnswerCheckRequest, session: AsyncSession = Depends(get_session)
):
    lesson = await _get_lesson_with_relations(lesson_id, session)
    if len(payload.answers) != len(lesson.questions):
        raise HTTPException(status_code=400, detail="Количество ответов не совпадает с количеством вопросов")

    results = [
        given.strip().lower() == q.correct_option.strip().lower()
        for given, q in zip(payload.answers, lesson.questions)
    ]
    return AnswerCheckResult(correct_count=sum(results), total=len(results), results=results)
