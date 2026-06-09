import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class ReviewQuizFormat(str, enum.Enum):
    SCENARIO_MATCH = "scenario_match"
    SIGNAL_RECOGNITION = "signal_recognition"
    CODE_REPAIR = "code_repair"
    DRILL_RECALL = "drill_recall"
    WHEN_TO_USE = "when_to_use"
    APPROACH_SELECT = "approach_select"
    MISTAKE_RETRY = "mistake_retry"


class ReviewQuizSourceType(str, enum.Enum):
    QUESTION = "question"
    TEMPLATE = "template"
    PATTERN_DRILL = "pattern_drill"
    CODE_MISTAKE = "code_mistake"
    QUIZ = "quiz"


class ReviewQuizItem(Base):
    __tablename__ = "review_quiz_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    quiz_format: Mapped[ReviewQuizFormat] = mapped_column(Enum(ReviewQuizFormat), nullable=False)
    source_type: Mapped[ReviewQuizSourceType] = mapped_column(Enum(ReviewQuizSourceType), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    replaces_quiz_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
