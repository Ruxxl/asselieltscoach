from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


# create_all() создаёт только отсутствующие таблицы и никогда не меняет уже существующие —
# для уже задеплоенной базы новые колонки speaking_sessions ниже сами не появятся. Это
# первая ручная "миграция" в проекте; если понадобится ещё раз менять существующую таблицу —
# добавить сюда же по тому же принципу (или наконец завести Alembic).
_SPEAKING_SESSION_NEW_COLUMNS = {
    "topic_id": "INTEGER",
    "topic_title": "VARCHAR(128)",
    "topic_question": "TEXT",
    "corrected_answer": "TEXT",
    "improvement_comments_json": "TEXT",
}


async def _add_missing_speaking_session_columns(conn: AsyncConnection) -> None:
    if conn.dialect.name != "sqlite":
        return
    exists = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='speaking_sessions'"))
    if not exists.first():
        return  # свежая база — create_all() выше уже создал таблицу сразу со всеми колонками
    result = await conn.execute(text("PRAGMA table_info(speaking_sessions)"))
    existing_columns = {row[1] for row in result.fetchall()}
    for column, coltype in _SPEAKING_SESSION_NEW_COLUMNS.items():
        if column not in existing_columns:
            await conn.execute(text(f"ALTER TABLE speaking_sessions ADD COLUMN {column} {coltype}"))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_speaking_session_columns(conn)
