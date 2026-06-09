from datetime import datetime

from pydantic import BaseModel


class ProgressResponse(BaseModel):
    id: int
    question_id: int
    ease_factor: float
    interval: int
    repetitions: int
    last_reviewed: datetime | None
    next_review: datetime | None
    quality_history: list[int]
    quiz_correct_count: int
    quiz_total_count: int

    model_config = {"from_attributes": True}


class ReviewRequest(BaseModel):
    quality: int


class DailyPlanItem(BaseModel):
    question_id: int
    question_title: str
    question_number: int | None
    difficulty: str
    topics: list[str]
    status: str
    reason: str
    next_review: datetime | None
    has_solutions: bool = False


class DailyPlanResponse(BaseModel):
    date: str
    items: list[DailyPlanItem]
    review_count: int
    new_count: int
    days_until_interview: int
    hours_until_interview: int = 0
    minutes_until_interview: int = 0
    missing_solutions_count: int = 0


class WeaknessResponse(BaseModel):
    topic: str
    subtopic: str | None
    attempts: int
    correct: int
    accuracy: float
