from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_or_create_user, require_user
from backend.database import get_session
from backend.models import Course, CoursePurchase, Module
from backend.schemas import CourseOut, PurchaseResult

router = APIRouter(prefix="/api/courses", tags=["courses"])

_COURSE_OPTIONS = selectinload(Course.modules).selectinload(Module.lessons)


async def _owned_course_ids(session: AsyncSession, user_id: int | None) -> set[int]:
    if not user_id:
        return set()
    result = await session.execute(select(CoursePurchase.course_id).where(CoursePurchase.user_id == user_id))
    return set(result.scalars().all())


def _to_out(course: Course, owned_ids: set[int]) -> CourseOut:
    out = CourseOut.model_validate(course)
    out.owned = course.id in owned_ids
    return out


@router.get("", response_model=list[CourseOut])
async def list_courses(
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await get_or_create_user(session, x_telegram_init_data)
    owned_ids = await _owned_course_ids(session, user.id if user else None)
    result = await session.execute(select(Course).options(_COURSE_OPTIONS).order_by(Course.order))
    return [_to_out(c, owned_ids) for c in result.scalars().all()]


@router.get("/{code}", response_model=CourseOut)
async def get_course(
    code: str,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Course).options(_COURSE_OPTIONS).where(Course.code == code.upper())
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден")
    user = await get_or_create_user(session, x_telegram_init_data)
    owned_ids = await _owned_course_ids(session, user.id if user else None)
    return _to_out(course, owned_ids)


@router.post("/{code}/purchase", response_model=PurchaseResult)
async def purchase_course(
    code: str,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Оплата пока без реального эквайринга: покупка выдаёт доступ мгновенно — заглушка
    на месте будущего платёжного провайдера (напр. ioka.kz). Владение курса (CoursePurchase)
    и её серверная проверка в lessons.py уже настоящие и не изменятся при подключении оплаты."""
    user = await require_user(session, x_telegram_init_data)

    result = await session.execute(select(Course).where(Course.code == code.upper()))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден")

    already = await session.execute(
        select(CoursePurchase.id).where(CoursePurchase.user_id == user.id, CoursePurchase.course_id == course.id)
    )
    if already.first():
        return PurchaseResult(owned=True)

    session.add(CoursePurchase(user_id=user.id, course_id=course.id, price_paid=course.price_kzt))
    await session.commit()
    return PurchaseResult(owned=True)
