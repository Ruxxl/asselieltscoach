from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Telegram user id
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    level: Mapped[str | None] = mapped_column(String(4), nullable=True)  # A1..C2
    xp: Mapped[int] = mapped_column(Integer, default=0)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(4), unique=True)  # A1..C2
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    price_kzt: Mapped[int] = mapped_column(Integer)
    order: Mapped[int] = mapped_column(Integer)

    modules: Mapped[list["Module"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    kind: Mapped[str] = mapped_column(String(32))  # grammar/vocabulary/listening/speaking/reading/writing/pronunciation
    title: Mapped[str] = mapped_column(String(128))
    lesson_count: Mapped[int] = mapped_column(Integer, default=0)
    order: Mapped[int] = mapped_column(Integer)

    course: Mapped["Course"] = relationship(back_populates="modules")
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="module", cascade="all, delete-orphan", order_by="Lesson.order"
    )


class Lesson(Base):
    """Реальный урок-статья внутри модуля курса (по образцу study.ru: тема -> список уроков).

    Заполнено пока только для курса A1 (Vocabulary/Grammar) как демонстрация подхода —
    остальные курсы/модули остаются с одним lesson_count без реального контента.
    """

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"))
    order: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(128))
    subtitle: Mapped[str] = mapped_column(String(255))
    read_minutes: Mapped[int] = mapped_column(Integer, default=2)
    content: Mapped[str] = mapped_column(Text)  # параграфы, разделённые "\n\n"

    module: Mapped["Module"] = relationship(back_populates="lessons")
    questions: Mapped[list["LessonQuestion"]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", order_by="LessonQuestion.order"
    )


class LessonQuestion(Base):
    """Один вопрос теста урока: предложение с пропуском + варианты слова на выбор."""

    __tablename__ = "lesson_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    order: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)  # предложение с "{blank}" на месте пропуска
    options: Mapped[str] = mapped_column(String(255))  # варианты через "|"
    correct_option: Mapped[str] = mapped_column(String(64))

    lesson: Mapped["Lesson"] = relationship(back_populates="questions")


class CoursePurchase(Base):
    """Факт покупки курса — реальная запись владения, не клиентская заглушка.

    Оплата сейчас — мгновенная заглушка без реального эквайринга (см. Payment ниже
    и бэкенд-задачу подключить провайдера, напр. ioka.kz); эта таблица уже даёт
    настоящую серверную проверку доступа к урокам независимо от способа оплаты.
    """

    __tablename__ = "course_purchases"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_course_purchase_user_course"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    price_paid: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LessonProgress(Base):
    """Факт прохождения теста урока пользователем — основа реального % прогресса курса."""

    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress_user_lesson"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    completed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # placement / final
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    answers: Mapped[list["TestAnswer"]] = relationship(back_populates="attempt", cascade="all, delete-orphan")


class TestAnswer(Base):
    __tablename__ = "test_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("test_attempts.id"))
    skill: Mapped[str] = mapped_column(String(16), default="reading")
    question_text: Mapped[str] = mapped_column(Text)
    reference_text: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(nullable=True)
    accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    attempt: Mapped["TestAttempt"] = relationship(back_populates="answers")


class NewsPost(Base):
    """Новость от преподавателя — публикуется командой /news в боте (см. bot/main.py)."""

    __tablename__ = "news_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatMessage(Base):
    """Сообщение в переписке ученика с преподавателем ("Обратиться к преподавателю").

    telegram_message_id — id сообщения-уведомления, отправленного преподавателю в Telegram
    (для sender='student'), по которому бот находит нужного ученика, когда преподаватель
    отвечает Reply-ом в Telegram (см. bot/main.py).
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sender: Mapped[str] = mapped_column(String(16))  # student / teacher
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    amount_rub: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/paid/failed — TODO: реальный провайдер
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
