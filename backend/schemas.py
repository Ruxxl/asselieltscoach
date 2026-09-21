from pydantic import BaseModel


class LessonBrief(BaseModel):
    id: int
    order: int
    title: str
    subtitle: str
    read_minutes: int

    class Config:
        from_attributes = True


class ModuleOut(BaseModel):
    id: int
    kind: str
    title: str
    lesson_count: int
    order: int
    lessons: list[LessonBrief] = []
    completed_lessons: int = 0  # сколько уроков модуля пользователь уже сдал

    class Config:
        from_attributes = True


class CourseOut(BaseModel):
    id: int
    code: str
    title: str
    description: str
    price_kzt: int
    order: int
    modules: list[ModuleOut] = []
    owned: bool = False  # куплен ли курс текущим пользователем (по X-Telegram-Init-Data)
    progress_percent: int | None = None  # None — в курсе ещё нет реальных уроков, а не 0%

    class Config:
        from_attributes = True


class QuestionOut(BaseModel):
    order: int
    prompt: str
    options: list[str]

    class Config:
        from_attributes = True


class LessonDetail(BaseModel):
    id: int
    title: str
    subtitle: str
    content: list[str]
    course_code: str
    module_title: str
    position: int  # порядковый номер урока в модуле, начиная с 1
    total_in_module: int
    prev_lesson_id: int | None
    next_lesson_id: int | None
    questions: list[QuestionOut]


class AnswerCheckRequest(BaseModel):
    answers: list[str]  # выбранный вариант на каждый вопрос по порядку


class AnswerCheckResult(BaseModel):
    correct_count: int
    total: int
    results: list[bool]  # правильность каждого ответа по порядку


class ReadingCheckResult(BaseModel):
    transcript: str
    is_correct: bool
    accuracy_score: float
    feedback: str


class PurchaseResult(BaseModel):
    owned: bool
