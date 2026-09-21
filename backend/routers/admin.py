from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_admin
from backend.database import get_session
from backend.models import Course, CoursePurchase, Module, User
from backend.routers.courses import _COURSE_OPTIONS
from backend.schemas import (
    AdminCourseIn,
    AdminCoursePatch,
    AdminCourseStatOut,
    AdminStatsOut,
    AdminUserOut,
    CourseOut,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsOut)
async def get_stats(
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_admin(session, x_telegram_init_data)

    total_users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    purchases_count = (await session.execute(select(func.count()).select_from(CoursePurchase))).scalar_one()
    total_sales = (
        await session.execute(select(func.coalesce(func.sum(CoursePurchase.price_paid), 0)))
    ).scalar_one()

    by_course_rows = await session.execute(
        select(
            Course.code,
            Course.title,
            func.count(CoursePurchase.id),
            func.coalesce(func.sum(CoursePurchase.price_paid), 0),
        )
        .select_from(Course)
        .outerjoin(CoursePurchase, CoursePurchase.course_id == Course.id)
        .group_by(Course.id)
        .order_by(Course.order)
    )
    by_course = [
        AdminCourseStatOut(code=code, title=title, purchases_count=cnt, revenue_kzt=rev)
        for code, title, cnt, rev in by_course_rows.all()
    ]

    return AdminStatsOut(
        total_users=total_users,
        purchases_count=purchases_count,
        total_sales_kzt=total_sales,
        by_course=by_course,
    )


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_admin(session, x_telegram_init_data)
    rows = await session.execute(
        select(User, func.count(CoursePurchase.id))
        .outerjoin(CoursePurchase, CoursePurchase.user_id == User.id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    out = []
    for user, owned_count in rows.all():
        item = AdminUserOut.model_validate(user)
        item.owned_courses_count = owned_count
        out.append(item)
    return out


@router.post("/courses", response_model=CourseOut)
async def create_course(
    payload: AdminCourseIn,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_admin(session, x_telegram_init_data)

    existing = await session.execute(select(Course.id).where(Course.code == payload.code.upper()))
    if existing.first():
        raise HTTPException(status_code=400, detail="Курс с таким кодом уже существует")

    course = Course(
        code=payload.code.upper(),
        title=payload.title,
        description=payload.description,
        price_kzt=payload.price_kzt,
        order=payload.order,
    )
    course.modules = [
        Module(kind=m.kind, title=m.title, lesson_count=m.lesson_count, order=m.order) for m in payload.modules
    ]
    session.add(course)
    await session.commit()
    # session.refresh() не подтягивает вложенное modules.lessons — сериализация Pydantic
    # синхронная и не может лениво его догрузить (MissingGreenlet). Перечитываем курс
    # тем же selectinload-запросом, что и остальные роутеры.
    result = await session.execute(select(Course).options(_COURSE_OPTIONS).where(Course.id == course.id))
    return CourseOut.model_validate(result.scalar_one())


@router.patch("/courses/{code}", response_model=CourseOut)
async def patch_course(
    code: str,
    payload: AdminCoursePatch,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_admin(session, x_telegram_init_data)

    result = await session.execute(select(Course).options(_COURSE_OPTIONS).where(Course.code == code.upper()))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден")

    if payload.title is not None:
        course.title = payload.title
    if payload.description is not None:
        course.description = payload.description
    if payload.price_kzt is not None:
        course.price_kzt = payload.price_kzt
    if payload.order is not None:
        course.order = payload.order

    if payload.modules is not None:
        existing_by_id = {m.id: m for m in course.modules}
        incoming_ids = {m.id for m in payload.modules if m.id is not None}
        # Модуль с реальными уроками (Lesson-записями) нельзя молча стереть через
        # этот список — иначе случайный пропуск модуля в форме уничтожит контент.
        for old_id, old_module in list(existing_by_id.items()):
            if old_id not in incoming_ids:
                if old_module.lessons:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Нельзя удалить модуль «{old_module.title}» — в нём есть реальные уроки",
                    )
                course.modules.remove(old_module)
                await session.delete(old_module)
        for m in payload.modules:
            if m.id is not None and m.id in existing_by_id:
                mod = existing_by_id[m.id]
                mod.kind, mod.title, mod.lesson_count, mod.order = m.kind, m.title, m.lesson_count, m.order
            else:
                course.modules.append(Module(kind=m.kind, title=m.title, lesson_count=m.lesson_count, order=m.order))

    course_id = course.id
    await session.commit()
    result = await session.execute(select(Course).options(_COURSE_OPTIONS).where(Course.id == course_id))
    return CourseOut.model_validate(result.scalar_one())


@router.delete("/courses/{code}")
async def delete_course(
    code: str,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    await require_admin(session, x_telegram_init_data)

    result = await session.execute(select(Course).where(Course.code == code.upper()))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден")

    has_purchases = await session.execute(
        select(CoursePurchase.id).where(CoursePurchase.course_id == course.id).limit(1)
    )
    if has_purchases.first():
        raise HTTPException(
            status_code=400, detail="Курс уже кто-то купил — удаление отключено, чтобы не потерять историю покупок"
        )

    await session.delete(course)
    await session.commit()
    return {"deleted": True}
