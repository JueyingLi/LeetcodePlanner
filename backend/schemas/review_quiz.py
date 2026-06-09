from datetime import datetime

from pydantic import BaseModel, Field


class ReviewQuizItemResponse(BaseModel):
    id: int
    quiz_format: str
    source_type: str
    source_id: int
    replaces_quiz_id: int | None = None
    prompt: str
    options: list[str] | None = None
    correct_answer: str
    explanation: str | None = None
    user_answer: str | None = None
    is_correct: bool | None = None
    time_spent_seconds: int | None = None
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewQuizAnswerRequest(BaseModel):
    answer: str
    time_spent_seconds: int | None = None


class ReviewQuizBuildRequest(BaseModel):
    limit: int = 15


class ReviewQuizStatsResponse(BaseModel):
    total: int
    correct: int
    accuracy: float
    by_format: dict[str, dict] = Field(default_factory=dict)
