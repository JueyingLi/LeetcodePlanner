from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.question import Status


class UserProgress(Base):
    __tablename__ = "user_progress"
    __table_args__ = (UniqueConstraint("user_id", "question_id", name="uq_progress_user_question"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    # Per-user study status for this question (no row implies TODO).
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.TODO, nullable=False, index=True)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    quality_history: Mapped[list] = mapped_column(JSON, default=list)
    quiz_correct_count: Mapped[int] = mapped_column(Integer, default=0)
    quiz_total_count: Mapped[int] = mapped_column(Integer, default=0)

    question: Mapped["Question"] = relationship(back_populates="progress")  # noqa: F821
