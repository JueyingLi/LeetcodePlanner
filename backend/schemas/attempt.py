from datetime import datetime

from pydantic import BaseModel


class AttemptCreate(BaseModel):
    question_id: int


class AttemptUpdate(BaseModel):
    observation: str | None = None
    approach: str | None = None
    code: str | None = None
    time_complexity: str | None = None
    space_complexity: str | None = None


class AttemptResponse(BaseModel):
    id: int
    question_id: int
    observation: str | None
    approach: str | None
    code: str | None
    time_complexity: str | None
    space_complexity: str | None
    ai_feedback: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeedbackRequest(BaseModel):
    step: str | None = None  # "observation", "approach", "code", "complexity", or None for full


class FeedbackResponse(BaseModel):
    step: str
    feedback: str
    score: int | None = None  # 1-5
    suggestions: list[str] = []
