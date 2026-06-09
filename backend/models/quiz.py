import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class QuizType(str, enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    ORDERING = "ordering"
    CODE_COMPLETION = "code_completion"
    OBSERVATION_MATCH = "observation_match"


class QuizFocus(str, enum.Enum):
    INPUT_OUTPUT = "input_output"
    PATTERN_RECOGNITION = "pattern_recognition"
    APPROACH_REASONING = "approach_reasoning"
    CODE_IMPLEMENTATION = "code_implementation"
    EDGE_CASES = "edge_cases"
    COMPLEXITY = "complexity"
    FULL_FLOW = "full_flow"


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    quiz_type: Mapped[QuizType] = mapped_column(Enum(QuizType), nullable=False)
    quiz_focus: Mapped[QuizFocus] = mapped_column(Enum(QuizFocus), default=QuizFocus.FULL_FLOW)
    quiz_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    user_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    question: Mapped["Question"] = relationship(back_populates="quiz_attempts")  # noqa: F821
