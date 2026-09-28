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


class SpeakingTopicOut(BaseModel):
    id: int
    title: str
    question_text: str
    order: int
    is_active: bool

    class Config:
        from_attributes = True


class SpeakingTopicPublicOut(BaseModel):
    """То, что видит ученик в списке тем ДО старта звонка — без вопроса (его первым
    задаёт живой экзаменатор), в том же духе "сюрприза", что и карточки Part 1/2/3."""

    id: int
    title: str

    class Config:
        from_attributes = True


class AdminSpeakingTopicIn(BaseModel):
    title: str
    question_text: str
    order: int
    is_active: bool = True


class AdminSpeakingTopicPatch(BaseModel):
    title: str | None = None
    question_text: str | None = None
    order: int | None = None
    is_active: bool | None = None


class SpeakingStartRequest(BaseModel):
    part: str  # part1 / part2 / part3
    topic_id: int | None = None  # обязателен для part1 (см. backend/routers/speaking.py)


class SpeakingStartResult(BaseModel):
    session_id: int
    ai_message: str
    question: str = ""  # вопрос дословно из ai_message ("" — если реплика без вопроса)
    audio_b64: str | None = None  # mp3 реплики; None — фронтенд озвучит speechSynthesis


class SpeakingCorrection(BaseModel):
    better: str  # ответ ученика так, как сказал бы носитель
    tip: str  # короткое объяснение на русском


class SpeakingTurnResult(BaseModel):
    student_said: str
    ai_message: str
    question: str = ""
    correction: SpeakingCorrection | None = None  # как лучше сказать — None, если ответ был без ошибок
    finished: bool
    audio_b64: str | None = None


class SpeakingHelpRequest(BaseModel):
    question: str


class SpeakingHelpResult(BaseModel):
    hint: str
    sample: str


class SpeakingSessionOut(BaseModel):
    id: int
    status: str
    part: str
    corrected_answer: str | None = None
    improvement_comments: list[str] | None = None
    fluency_coherence: float | None = None
    lexical_resource: float | None = None
    grammar_accuracy: float | None = None
    pronunciation: float | None = None
    overall_band: float | None = None
    summary_feedback: str | None = None
    error_message: str | None = None

    class Config:
        from_attributes = True


class PurchaseResult(BaseModel):
    owned: bool


class NewsPostOut(BaseModel):
    id: int
    text: str
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
