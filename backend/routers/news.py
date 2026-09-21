from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models import NewsPost
from backend.schemas import NewsPostOut

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("", response_model=list[NewsPostOut])
async def list_news(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(NewsPost).order_by(NewsPost.created_at.desc()))
    return result.scalars().all()
