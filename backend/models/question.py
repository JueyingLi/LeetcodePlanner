import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Difficulty(str, enum.Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class Status(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    REVIEW = "review"
    REWORK = "rework"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(Enum(Difficulty), nullable=False)
    topics: Mapped[list] = mapped_column(JSON, default=list)
    subtopics: Mapped[list] = mapped_column(JSON, default=list)
    frequency: Mapped[float] = mapped_column(Float, default=0.0)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    examples: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    solutions: Mapped[list["Solution"]] = relationship(back_populates="question", cascade="all, delete-orphan")  # noqa: F821
    # One progress row per user for this question (status lives here, per-user).
    progress: Mapped[list["UserProgress"]] = relationship(back_populates="question", cascade="all, delete-orphan")  # noqa: F821
    quiz_attempts: Mapped[list["QuizAttempt"]] = relationship(back_populates="question", cascade="all, delete-orphan")  # noqa: F821
