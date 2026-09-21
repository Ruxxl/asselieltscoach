"""Определение текущего пользователя по Telegram WebApp initData + создание User при первом визите."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import User
from backend.telegram_auth import parse_init_data


async def get_or_create_user(session: AsyncSession, init_data: str | None) -> User | None:
    """Мягкая идентификация: без валидного initData возвращает None, не падает с ошибкой."""
    tg_user = parse_init_data(init_data)
    if not tg_user:
        return None
    user = await session.get(User, tg_user["id"])
    if not user:
        user = User(
            id=tg_user["id"],
            username=tg_user.get("username"),
            full_name=" ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])),
        )
        session.add(user)
        await session.commit()
    return user


async def require_user(session: AsyncSession, init_data: str | None) -> User:
    """Строгая идентификация для операций с деньгами/владением курсом — без неё 401."""
    user = await get_or_create_user(session, init_data)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Не удалось определить пользователя Telegram. Открой мини-апп через бота в Telegram.",
        )
    return user
