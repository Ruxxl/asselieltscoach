from pydantic import BaseModel


class ModuleOut(BaseModel):
    id: int
    kind: str
    title: str
    lesson_count: int
    order: int

    class Config:
        from_attributes = True


class CourseOut(BaseModel):
    id: int
    code: str
    title: str
    description: str
    price_rub: int
    order: int
    modules: list[ModuleOut] = []

    class Config:
        from_attributes = True


class ReadingCheckResult(BaseModel):
    transcript: str
    is_correct: bool
    accuracy_score: float
    feedback: str
