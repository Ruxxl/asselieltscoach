from datetime import datetime

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


class NewsPostOut(BaseModel):
    id: int
    text: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageOut(BaseModel):
    id: int
    sender: str  # student / teacher
    text: str | None = None
    voice_url: str | None = None  # проставляется в роутере, если voice_path есть
    created_at: datetime

    class Config:
        from_attributes = True


class AdminCourseStatOut(BaseModel):
    code: str
    title: str
    purchases_count: int
    revenue_kzt: int


class AdminStatsOut(BaseModel):
    total_users: int
    purchases_count: int
    total_sales_kzt: int
    by_course: list[AdminCourseStatOut]


class AdminUserOut(BaseModel):
    id: int
    username: str | None
    full_name: str | None
    owned_courses_count: int = 0  # не в ORM-модели — проставляется в роутере после model_validate
    created_at: datetime

    class Config:
        from_attributes = True


class AdminModuleIn(BaseModel):
    id: int | None = None  # None — новый модуль, добавляется при PATCH
    kind: str
    title: str
    lesson_count: int
    order: int


class AdminCourseIn(BaseModel):
    code: str
    title: str
    description: str
    price_kzt: int
    order: int
    modules: list[AdminModuleIn] = []


class AdminCoursePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    price_kzt: int | None = None
    order: int | None = None
    modules: list[AdminModuleIn] | None = None  # если задано — полностью заменяет список модулей
