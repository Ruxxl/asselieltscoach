from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_session
from backend.models import Course, Module
from backend.schemas import CourseOut

router = APIRouter(prefix="/api/courses", tags=["courses"])

_COURSE_OPTIONS = selectinload(Course.modules).selectinload(Module.lessons)


@router.get("", response_model=list[CourseOut])
async def list_courses(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Course).options(_COURSE_OPTIONS).order_by(Course.order))
    return result.scalars().all()


@router.get("/{code}", response_model=CourseOut)
async def get_course(code: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Course).options(_COURSE_OPTIONS).where(Course.code == code.upper())
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден")
    return course
