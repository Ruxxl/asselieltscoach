from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Course, Module

COURSES = [
    {
        "code": "A1",
        "title": "Beginner",
        "description": "Основы: алфавит, простые фразы, базовая грамматика.",
        "price_rub": 2400,
        "order": 1,
        "modules": [
            ("vocabulary", "Vocabulary", 10),
            ("grammar", "Grammar", 8),
            ("listening", "Listening", 6),
        ],
    },
    {
        "code": "A2",
        "title": "Elementary",
        "description": "Бытовые диалоги, настоящее и прошедшее время.",
        "price_rub": 2600,
        "order": 2,
        "modules": [
            ("grammar", "Grammar", 10),
            ("vocabulary", "Vocabulary", 9),
            ("listening", "Listening", 7),
            ("speaking", "Speaking", 5),
        ],
    },
    {
        "code": "B1",
        "title": "Intermediate",
        "description": "Уверенная бытовая речь, Present Perfect, начало Reading/Writing.",
        "price_rub": 2900,
        "order": 3,
        "modules": [
            ("grammar", "Grammar", 12),
            ("vocabulary", "Vocabulary", 10),
            ("listening", "Listening", 8),
            ("speaking", "Speaking", 8),
            ("reading", "Reading", 9),
            ("writing", "Writing", 6),
        ],
    },
    {
        "code": "B2",
        "title": "Upper-Intermediate",
        "description": "Свободные темы, деловой английский, сложные времена.",
        "price_rub": 3400,
        "order": 4,
        "modules": [
            ("grammar", "Grammar", 12),
            ("vocabulary", "Vocabulary", 12),
            ("reading", "Reading", 10),
            ("speaking", "Speaking", 9),
            ("writing", "Writing", 8),
        ],
    },
    {
        "code": "C1",
        "title": "Advanced",
        "description": "Нюансы, академический и деловой стиль, идиомы.",
        "price_rub": 3900,
        "order": 5,
        "modules": [
            ("vocabulary", "Vocabulary", 14),
            ("reading", "Reading", 12),
            ("writing", "Writing", 10),
            ("speaking", "Speaking", 10),
            ("pronunciation", "Pronunciation", 6),
        ],
    },
]


async def seed_if_empty(session: AsyncSession) -> None:
    existing = await session.execute(select(Course.id).limit(1))
    if existing.first():
        return

    for c in COURSES:
        course = Course(
            code=c["code"],
            title=c["title"],
            description=c["description"],
            price_rub=c["price_rub"],
            order=c["order"],
        )
        session.add(course)
        await session.flush()
        for i, (kind, title, count) in enumerate(c["modules"]):
            session.add(
                Module(
                    course_id=course.id,
                    kind=kind,
                    title=title,
                    lesson_count=count,
                    order=i,
                )
            )
    await session.commit()
