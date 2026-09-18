from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Course, Lesson, LessonQuestion, Module

# Реальный контент уроков — пока только для курса A1 (Vocabulary/Grammar), по образцу
# структуры study.ru (тема -> уроки-статьи -> тест из вопросов "заполни пропуск").
# Остальные курсы/модули ниже остаются с одним lesson_count без реального контента —
# это следующий шаг, см. memory/echo_english_deployment для контекста.
A1_VOCABULARY_LESSONS = [
    {
        "title": "Приветствия и знакомство",
        "subtitle": "Как поздороваться и представиться по-английски",
        "read_minutes": 3,
        "content": [
            "Самые частые приветствия в английском — Hello и Hi. Hello чуть более нейтральное и формальное, "
            "Hi — более разговорное, между друзьями и знакомыми.",
            "Чтобы представиться, используют фразу My name is... («Меня зовут...») или короче — I'm... "
            "Например: My name is Anna. / I'm Anna.",
            "На вопрос How are you? («Как дела?») обычно отвечают I'm fine, thank you. And you? — это "
            "вежливая формула, даже если дела не идеальные.",
            "Прощаются словами Bye, Goodbye или разговорным See you! («Увидимся!»).",
        ],
        "questions": [
            {
                "prompt": "— Hi! {blank} name is Tom. — Nice to meet you!",
                "options": ["My", "I", "Me"],
                "correct": "My",
            },
            {
                "prompt": "— How are you? — I'm fine, thank you. {blank} you?",
                "options": ["And", "For", "With"],
                "correct": "And",
            },
            {
                "prompt": "Формальное приветствие — это {blank}.",
                "options": ["Hello", "Hi", "Bye"],
                "correct": "Hello",
            },
        ],
    },
    {
        "title": "Числа 1–20",
        "subtitle": "Считаем по-английски от одного до двадцати",
        "read_minutes": 2,
        "content": [
            "Числа от 1 до 12 в английском не подчиняются никакому правилу и их нужно просто запомнить: "
            "one, two, three, four, five, six, seven, eight, nine, ten, eleven, twelve.",
            "Числа от 13 до 19 образуются добавлением суффикса -teen: thirteen, fourteen, fifteen, "
            "sixteen, seventeen, eighteen, nineteen.",
            "Двадцать — twenty, дальше (21, 22...) числа складываются: twenty-one, twenty-two.",
        ],
        "questions": [
            {"prompt": "Число 15 по-английски — {blank}.", "options": ["fifteen", "fifty", "five"], "correct": "fifteen"},
            {"prompt": "Число 20 по-английски — {blank}.", "options": ["twenty", "twelve", "ten"], "correct": "twenty"},
            {"prompt": "После nine идёт {blank}.", "options": ["ten", "nineteen", "nine"], "correct": "ten"},
        ],
    },
    {
        "title": "Цвета",
        "subtitle": "Основные названия цветов",
        "read_minutes": 2,
        "content": [
            "Основные цвета: red (красный), blue (синий), green (зелёный), yellow (жёлтый), black (чёрный), "
            "white (белый), orange (оранжевый), purple (фиолетовый).",
            "Чтобы описать цвет предмета, прилагательное ставится перед существительным: a red car "
            "(красная машина), a blue sky (синее небо). В английском прилагательные не меняются по родам "
            "и числам.",
        ],
        "questions": [
            {"prompt": "The sky is {blank}.", "options": ["blue", "loud", "fast"], "correct": "blue"},
            {"prompt": "Grass (трава) is usually {blank}.", "options": ["green", "green's", "greens"], "correct": "green"},
            {"prompt": "«Красная машина» — a {blank} car.", "options": ["red", "reds", "redly"], "correct": "red"},
        ],
    },
]

A1_GRAMMAR_LESSONS = [
    {
        "title": "Глагол to be",
        "subtitle": "Формы am / is / are в настоящем времени",
        "read_minutes": 4,
        "content": [
            "Глагол to be («быть») — один из самых важных в английском. В настоящем времени у него три формы: "
            "am, is, are.",
            "am используется только с I: I am a student.",
            "is используется с he, she, it и с существительными в единственном числе: He is happy. The book is "
            "interesting.",
            "are используется с you, we, they и с существительными во множественном числе: They are friends. "
            "We are here.",
            "В разговорной речи формы часто сокращают: I'm, he's, she's, it's, you're, we're, they're.",
        ],
        "questions": [
            {"prompt": "I {blank} a teacher.", "options": ["am", "is", "are"], "correct": "am"},
            {"prompt": "She {blank} from London.", "options": ["is", "am", "are"], "correct": "is"},
            {"prompt": "They {blank} happy today.", "options": ["are", "is", "am"], "correct": "are"},
        ],
    },
    {
        "title": "Личные местоимения",
        "subtitle": "I, you, he, she, it, we, they",
        "read_minutes": 3,
        "content": [
            "Личные местоимения заменяют существительные-подлежащее: I (я), you (ты/вы), he (он), she (она), "
            "it (оно, для предметов и животных), we (мы), they (они).",
            "В английском нет отдельного вежливого «вы» — you используется и для одного человека, и для "
            "нескольких, и в вежливом, и в неформальном обращении.",
            "Местоимение it также используется для погоды и времени: It is raining. It is five o'clock.",
        ],
        "questions": [
            {"prompt": "Look at the dog — {blank} is so cute!", "options": ["it", "he", "they"], "correct": "it"},
            {"prompt": "{blank} is raining outside.", "options": ["It", "He", "She"], "correct": "It"},
            {"prompt": "Anna and Tom are students. {blank} study English.", "options": ["They", "He", "It"], "correct": "They"},
        ],
    },
    {
        "title": "Артикли a / an / the",
        "subtitle": "Когда ставить неопределённый, а когда определённый артикль",
        "read_minutes": 3,
        "content": [
            "Артикль a/an ставится перед исчисляемым существительным в единственном числе, когда речь идёт о "
            "предмете впервые или в общем смысле: a cat, a table.",
            "an используется вместо a, если следующее слово начинается с гласного звука: an apple, an hour.",
            "Артикль the ставится, когда предмет уже известен собеседнику или упоминался раньше: I have a cat. "
            "The cat is black.",
        ],
        "questions": [
            {"prompt": "I have {blank} apple.", "options": ["an", "a", "the"], "correct": "an"},
            {"prompt": "She has a dog. {blank} dog is very friendly.", "options": ["The", "A", "An"], "correct": "The"},
            {"prompt": "He is {blank} good student.", "options": ["a", "an", "the"], "correct": "a"},
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


COURSES = [
    {
        "code": "A1",
        "title": "Beginner",
        "description": "Основы: алфавит, простые фразы, базовая грамматика.",
        "price_kzt": 5000,
        "order": 1,
        "modules": [
            ("vocabulary", "Vocabulary", A1_VOCABULARY_LESSONS),
            ("grammar", "Grammar", A1_GRAMMAR_LESSONS),
            ("listening", "Listening", 6),  # аудио-контента пока нет
        ],
    },
    {
        "code": "A2",
        "title": "Elementary",
        "description": "Бытовые диалоги, настоящее и прошедшее время.",
        "price_kzt": 5000,
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
        "price_kzt": 5000,
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
        "price_kzt": 5000,
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
        "price_kzt": 5000,
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
