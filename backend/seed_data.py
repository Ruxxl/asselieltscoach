from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Course, Lesson, LessonQuestion, Module

# Реальный контент уроков — пока только для курса "IELTS 5.5" (Listening/Reading), по образцу
# структуры study.ru (тема -> уроки-статьи -> тест из вопросов "заполни пропуск"). Это авторский
# разбор стратегий сдачи, а не пересказ реальных вопросов Cambridge/IDP (копирайт).
# Остальные курсы/модули ниже остаются с одним lesson_count без реального контента —
# это следующий шаг, см. memory/echo_english_deployment для контекста.
IELTS_LISTENING_LESSONS = [
    {
        "title": "Формат IELTS Listening",
        "subtitle": "Что тебя ждёт на экзамене: структура, время, баллы",
        "read_minutes": 3,
        "content": [
            "IELTS Listening состоит из 4 разделов (sections) и содержит 40 вопросов. Первый раздел — "
            "бытовой диалог (например, бронирование), четвёртый — лекция на академическую тему.",
            "На прослушивание даётся 30 минут; в бумажной версии теста добавляется ещё 10 минут, чтобы "
            "перенести ответы в бланк — в компьютерной версии этого дополнительного времени нет, ответы "
            "вводятся сразу.",
            "Каждая запись звучит только один раз — переслушать нельзя, поэтому важно читать вопросы "
            "заранее, пока идёт вступление к разделу.",
            "Итоговый балл считается по таблице соответствия: из 40 правильных ответов высчитывается "
            "band score от 1 до 9.",
        ],
        "questions": [
            {"prompt": "В IELTS Listening всего {blank} вопросов.", "options": ["40", "50", "30"], "correct": "40"},
            {"prompt": "Сколько разделов (sections) в тесте?", "options": ["4", "3", "5"], "correct": "4"},
            {"prompt": "Каждая запись в Listening звучит {blank}.", "options": ["один раз", "дважды", "три раза"], "correct": "один раз"},
        ],
    },
    {
        "title": "Типы вопросов в Listening",
        "subtitle": "Form completion, multiple choice, matching, map labeling",
        "read_minutes": 3,
        "content": [
            "Самые частые типы заданий: заполнение пропусков (form/note/table completion), множественный "
            "выбор (multiple choice), подбор соответствий (matching), подписи на карте или плане "
            "(map/plan labeling).",
            "В заданиях на заполнение пропусков важно соблюдать лимит слов из инструкции — обычно "
            "'NO MORE THAN THREE WORDS AND/OR A NUMBER'. Превышение лимита засчитывается как ошибка, "
            "даже если по смыслу ответ верный.",
            "В multiple choice несколько вариантов часто кажутся похожими на правду — это специально, "
            "чтобы проверить внимательность к деталям: числам, датам, именам.",
        ],
        "questions": [
            {"prompt": "В заданиях на заполнение пропуска важно соблюдать {blank} из инструкции.", "options": ["лимит слов", "цвет ручки", "громкость записи"], "correct": "лимит слов"},
            {"prompt": "Задание, где нужно подписать объекты на плане — это {blank}.", "options": ["map labeling", "multiple choice", "matching"], "correct": "map labeling"},
            {"prompt": "Типичная формулировка лимита — 'NO MORE THAN {blank} WORDS'.", "options": ["THREE", "TEN", "ONE"], "correct": "THREE"},
        ],
    },
    {
        "title": "Стратегия: слушай наперёд",
        "subtitle": "Как использовать паузы и не терять баллы на парафразе",
        "read_minutes": 2,
        "content": [
            "Перед каждым разделом даётся 20–30 секунд, чтобы прочитать вопросы — используй это время, "
            "чтобы подчеркнуть ключевые слова и предположить тип ответа (имя, число, место).",
            "Ответы в записи почти всегда даются через парафраз — говорящий использует синонимы вместо "
            "слов из вопроса. Тренируйся слышать смысл, а не искать дословное совпадение.",
            "Если пропустил один ответ — не зацикливайся на нём, сразу переходи к следующему вопросу, "
            "иначе рискуешь пропустить сразу несколько подряд.",
        ],
        "questions": [
            {"prompt": "Ответы в записи почти всегда даются через {blank}, а не дословно.", "options": ["парафраз", "повтор", "перевод"], "correct": "парафраз"},
            {"prompt": "Если пропустил один ответ, нужно {blank}.", "options": ["сразу перейти к следующему", "остановить запись", "переслушать"], "correct": "сразу перейти к следующему"},
            {"prompt": "Пауза перед разделом нужна, чтобы {blank} вопросы.", "options": ["прочитать", "перевести", "выучить"], "correct": "прочитать"},
        ],
    },
]

IELTS_READING_LESSONS = [
    {
        "title": "Формат IELTS Reading",
        "subtitle": "3 текста, 40 вопросов, 60 минут без добавки",
        "read_minutes": 3,
        "content": [
            "IELTS Reading состоит из 3 текстов (passages) и 40 вопросов, на всё даётся 60 минут — в "
            "отличие от Listening, дополнительного времени на перенос ответов нет.",
            "Тексты постепенно усложняются: первый — самый простой, третий — самый сложный, часто "
            "научно-популярный.",
            "В Academic-версии тексты берутся из журналов, книг, научных статей; в General Training — "
            "из объявлений, писем, справочных материалов (актуально для миграции и работы).",
        ],
        "questions": [
            {"prompt": "Сколько текстов (passages) в IELTS Reading?", "options": ["3", "2", "4"], "correct": "3"},
            {"prompt": "Сколько минут даётся на весь Reading, включая перенос ответов?", "options": ["60", "70", "90"], "correct": "60"},
            {"prompt": "В какой версии теста тексты — это объявления и письма?", "options": ["General Training", "Academic", "Speaking"], "correct": "General Training"},
        ],
    },
    {
        "title": "Skimming и scanning",
        "subtitle": "Два разных навыка быстрого чтения",
        "read_minutes": 2,
        "content": [
            "Skimming — быстрое чтение текста целиком, чтобы понять общую идею и структуру абзацев, без "
            "вникания в детали.",
            "Scanning — поиск конкретной информации (даты, имена, цифры) без чтения всего текста: взгляд "
            "«скользит» по строчкам в поисках ключевого слова.",
            "Перед подробным чтением полезно сначала пробежаться skimming'ом — так проще понять, в каком "
            "абзаце искать ответ на конкретный вопрос.",
        ],
        "questions": [
            {"prompt": "Быстрое чтение текста целиком для общего понимания — это {blank}.", "options": ["skimming", "scanning", "matching"], "correct": "skimming"},
            {"prompt": "Поиск конкретной цифры или имени в тексте — это {blank}.", "options": ["scanning", "skimming", "paraphrasing"], "correct": "scanning"},
            {"prompt": "Перед подробным чтением полезно сначала сделать {blank}.", "options": ["skimming", "полный перевод", "конспект"], "correct": "skimming"},
        ],
    },
    {
        "title": "True / False / Not Given — частые ошибки",
        "subtitle": "Как не путать «текст молчит» с «текст опровергает»",
        "read_minutes": 3,
        "content": [
            "False ставится, когда утверждение прямо противоречит тексту. Not Given — когда в тексте "
            "просто нет информации, чтобы подтвердить или опровергнуть утверждение.",
            "Самая частая ошибка — путать False и Not Given: если кажется, что «текст молчит» об этом, но "
            "нет уверенности — скорее всего это Not Given, а не False.",
            "Отвечай строго по тексту, а не по своим знаниям темы — даже если утверждение верно в "
            "реальности, но текст об этом не говорит, правильный ответ — Not Given.",
        ],
        "questions": [
            {"prompt": "Если утверждение прямо противоречит тексту, ответ — {blank}.", "options": ["False", "Not Given", "True"], "correct": "False"},
            {"prompt": "Если в тексте просто нет информации по теме утверждения, ответ — {blank}.", "options": ["Not Given", "False", "True"], "correct": "Not Given"},
            {"prompt": "Отвечать нужно строго по {blank}, а не по общим знаниям.", "options": ["тексту", "интуиции", "заголовку"], "correct": "тексту"},
        ],
    },
]


def _build_module_lessons(lesson_specs: list[dict]) -> list[Lesson]:
    lessons = []
    for i, spec in enumerate(lesson_specs):
        lesson = Lesson(
            order=i,
            title=spec["title"],
            subtitle=spec["subtitle"],
            read_minutes=spec["read_minutes"],
            content="\n\n".join(spec["content"]),
        )
        lesson.questions = [
            LessonQuestion(
                order=j,
                prompt=q["prompt"],
                options="|".join(q["options"]),
                correct_option=q["correct"],
            )
            for j, q in enumerate(spec["questions"])
        ]
        lessons.append(lesson)
    return lessons


# Три курса подготовки к IELTS по целевому баллу (band score) — стандартная сегментация
# для прайм-подготовки, ближе клиенту, чем абстрактные уровни CEFR.
COURSES = [
    {
        "code": "B55",
        "title": "IELTS 5.5",
        "description": "С нуля до уверенного среднего: база по всем 4 модулям экзамена — Listening, Reading, Writing, Speaking.",
        "price_kzt": 5000,
        "order": 1,
        "modules": [
            ("listening", "Listening", IELTS_LISTENING_LESSONS),
            ("reading", "Reading", IELTS_READING_LESSONS),
            ("writing", "Writing", 6),  # контента пока нет
            ("speaking", "Speaking", 5),  # контента пока нет
        ],
    },
    {
        "code": "B65",
        "title": "IELTS 6.5",
        "description": "Для уверенного среднего уровня: техники под конкретные типы заданий, разбор типичных ошибок, практика по таймингу.",
        "price_kzt": 5000,
        "order": 2,
        "modules": [
            ("listening", "Listening", 8),
            ("reading", "Reading", 9),
            ("writing", "Writing", 8),
            ("speaking", "Speaking", 7),
        ],
    },
    {
        "code": "B75",
        "title": "IELTS 7.5+",
        "description": "Для высокого балла: сложные типы вопросов, эссе на Band 8+, беглость и точность в Speaking.",
        "price_kzt": 5000,
        "order": 3,
        "modules": [
            ("listening", "Listening", 6),
            ("reading", "Reading", 8),
            ("writing", "Writing", 10),
            ("speaking", "Speaking", 8),
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
            price_kzt=c["price_kzt"],
            order=c["order"],
        )
        session.add(course)
        await session.flush()
        for i, (kind, title, lessons_or_count) in enumerate(c["modules"]):
            if isinstance(lessons_or_count, list):
                lessons = _build_module_lessons(lessons_or_count)
                module = Module(course_id=course.id, kind=kind, title=title, lesson_count=len(lessons), order=i)
                module.lessons = lessons
            else:
                module = Module(course_id=course.id, kind=kind, title=title, lesson_count=lessons_or_count, order=i)
            session.add(module)
    await session.commit()
