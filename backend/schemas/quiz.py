from datetime import datetime

from pydantic import BaseModel, Field

from backend.models.quiz import QuizFocus, QuizType


class QuizGenerateRequest(BaseModel):
    count: int = 5
    topics: list[str] | None = None
    subtopics: list[str] | None = None
    focus: str | None = None
    quiz_focus: QuizFocus | None = None
    quiz_focuses: list[QuizFocus] | None = None
    question_ids: list[int] | None = None


class QuizQuestionData(BaseModel):
    quiz_type: QuizType
    quiz_focus: QuizFocus
    question_id: int
    question_title: str
    prompt: str
    options: list[str] | None = None
    correct_answer: str
    explanation: str = ""
    prior_steps_summary: str | None = None


class QuizSubmitItem(BaseModel):
    quiz_id: int
    answer: str
    time_spent_seconds: int | None = None


class QuizSubmitRequest(BaseModel):
    attempts: list[QuizSubmitItem]


class QuizAttemptResponse(BaseModel):
    id: int
    question_id: int
    quiz_type: QuizType
    quiz_focus: QuizFocus
    quiz_data: dict
    user_answer: str | None
    correct_answer: str
    is_correct: bool | None
    time_spent_seconds: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuizSessionResponse(BaseModel):
    quizzes: list[QuizAttemptResponse]
    total: int


class QuizStatsResponse(BaseModel):
    total_attempts: int
    correct_count: int
    accuracy: float
    by_topic: dict[str, dict] = Field(default_factory=dict)
    by_focus: dict[str, dict] = Field(default_factory=dict)
    weak_topics: list[str] = Field(default_factory=list)
