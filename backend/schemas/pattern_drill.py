from datetime import datetime

from pydantic import BaseModel

from backend.models.question import Difficulty
from backend.schemas.question import PatternAnalysis


class DrillCard(BaseModel):
    id: int
    number: int | None
    title: str
    difficulty: Difficulty
    topics: list[str]
    subtopics: list[str]
    pattern_analysis: PatternAnalysis | None = None
    completed: bool = False


class DrillDeckResponse(BaseModel):
    items: list[DrillCard]
    total: int


class DrillReviewRequest(BaseModel):
    quality: int
    notes: str | None = None


class DrillReviewResponse(BaseModel):
    question_id: int
    repetitions: int
    interval: int
    next_review: datetime | None = None
    last_reviewed: datetime | None = None


class DrillAskRequest(BaseModel):
    question: str
    step_kind: str | None = None


class DrillAskResponse(BaseModel):
    id: int
    question_id: int
    user_question: str
    answer: str
    created_at: datetime

    model_config = {"from_attributes": True}
