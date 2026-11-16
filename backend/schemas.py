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
    """Тема Speaking в админке. questions — вопросы Part 1 по одному или вопросы Part 3 к карточке Part 2
    (карточка — в question_text)."""

    id: int
    title: str
    question_text: str
    questions: list[str] = []
    part: str = "part1"
    category: str = "other"
    order: int
    is_active: bool


class SpeakingTopicPublicOut(BaseModel):
    """Тема в списке выбора у ученика."""

    id: int
    title: str
    part: str
    category: str
    question_count: int


class AdminSpeakingTopicIn(BaseModel):
    title: str
    question_text: str
    questions: list[str] = []
    part: str = "part1"
    category: str = "other"
    order: int
    is_active: bool = True


class AdminSpeakingTopicPatch(BaseModel):
    title: str | None = None
    question_text: str | None = None
    questions: list[str] | None = None
    part: str | None = None
    category: str | None = None
    order: int | None = None
    is_active: bool | None = None


class SpeakingStartRequest(BaseModel):
    topic_id: int


class SpeakingStep(BaseModel):
    index: int
    kind: str  # part1 / part2 (карточка) / part3
    question: str


class SpeakingStartResult(BaseModel):
    session_id: int
    topic_title: str
    part: str  # part1 / part2 (карточка + вопросы Part 3)
    steps: list[SpeakingStep]


class SpeakingStepRequest(BaseModel):
    index: int


class SpeakingSpeakRequest(BaseModel):
    index: int
    mode: str = "ask"  # ask — преподаватель задаёт вопрос (с вводной фразой); repeat — только повторяет его


class SpeakingSpeakResult(BaseModel):
    text: str  # что произносит преподаватель (для запасного голоса и отображения)
    audio_b64: str | None = None  # mp3; None — фронтенд озвучит speechSynthesis


class SpeakingVocabItem(BaseModel):
    phrase: str
    translation: str


class SpeakingHelpResult(BaseModel):
    vocabulary: list[SpeakingVocabItem]
    sample: str


class SpeakingCorrectionItem(BaseModel):
    original: str
    better: str
    why: str = ""


class SpeakingReviewTopic(BaseModel):
    topic: str
    note: str = ""


class SpeakingAnswerResult(BaseModel):
    student_said: str
    on_topic: bool = True  # False — ответ не по вопросу: разбор не делаем, вопрос задаём заново
    topic_comment: str = ""
    teacher_say: str = ""  # реплика преподавателя вслух: реакция на ответ, подсказка или "ты отвлёкся, вопрос был…"
    audio_b64: str | None = None  # mp3 реплики преподавателя
    corrections: list[SpeakingCorrectionItem]
    review_topics: list[SpeakingReviewTopic]


class SpeakingEstimateResult(BaseModel):
    fluency_coherence: float
    lexical_resource: float
    grammar_accuracy: float
    pronunciation: float
    overall_band: float
    criteria_feedback: dict[str, str] = {}


class SpeakingImproveResult(BaseModel):
    current_band: float
    target_band: float
    improved_answer: str


class PaymentStartOut(BaseModel):
    """owned=True — курс уже доступен (куплен раньше или Halyk ещё не настроен, пилот).
    Иначе фронтенд подключает js_url и вызывает halyk.pay(payment)."""

    owned: bool = False
    payment_id: int | None = None
    js_url: str | None = None
    payment: dict | None = None


class PaymentStatusOut(BaseModel):
    status: str  # pending / paid / failed
    course_code: str
    failure_reason: str | None = None


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


class WritingIssueOut(BaseModel):
    start: int
    end: int
    original: str
    suggestion: str
    category: str
    explanation: str


class WritingCriterionOut(BaseModel):
    band: float
    comment: str
    reasoning: str = ""


class WritingResultOut(BaseModel):
    assessable: bool
    overall_band: float
    word_count: int
    criteria: dict[str, WritingCriterionOut]
    summary: str
    strengths: list[str]
    improvements: list[str]
    issues: list[WritingIssueOut]
    teacher_comment: str = ""
    sample_essay: str | None = None


class WritingChatTurn(BaseModel):
    role: str  # user / ai
    text: str


class WritingCheckOut(BaseModel):
    id: int
    task_type: str
    mode: str
    language: str
    target_band: str
    topic: str
    essay: str
    created_at: datetime
    result: WritingResultOut
    chat: list[WritingChatTurn] = []


class WritingHistoryItem(BaseModel):
    id: int
    task_type: str
    topic: str
    overall_band: float
    word_count: int
    created_at: datetime


class WritingSampleRequest(BaseModel):
    task_type: str
    topic: str
    target_band: str = "7.0-8.0"


class WritingIdeasRequest(BaseModel):
    task_type: str
    topic: str
    language: str = "ru"


class WritingTextOut(BaseModel):
    text: str


class WritingChatRequest(BaseModel):
    message: str


class GrammarCheckRequest(BaseModel):
    text: str
    text_language: str = "auto"
    ai_language: str = "ru"
    mode: str = "student"
    context: str = "general"
    target: str = "none"
    explanations: bool = True
    detailed: bool = True
    use_context: bool = True


class GrammarAssessmentOut(BaseModel):
    score: int
    level: str = ""
    summary: str = ""
    strengths: list[str] = []
    improvements: list[str] = []


class GrammarCheckOut(BaseModel):
    detected_language: str = ""
    issues: list[WritingIssueOut]
    assessment: GrammarAssessmentOut | None = None
    teacher_comment: str = ""


class GrammarTransformRequest(BaseModel):
    text: str
    action: str
    context: str = "general"
    target: str = "none"
    full_text: str | None = None  # весь документ, если переписываем только выделенный фрагмент


class GrammarChatRequest(BaseModel):
    text: str
    message: str
    ai_language: str = "ru"
    issues: list[WritingIssueOut] = []
    history: list[WritingChatTurn] = []


class GrammarDocxRequest(BaseModel):
    text: str
    result: GrammarCheckOut  # issues внутри — только не отклонённые учеником правки
    filename: str = "Grammar_Check"
    author: str = "Assel AI"
