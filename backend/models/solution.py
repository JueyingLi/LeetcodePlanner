from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Solution(Base):
    __tablename__ = "solutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    approach_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description_reminder: Mapped[str] = mapped_column(Text, nullable=False, default="")
    initial_observation: Mapped[str] = mapped_column(Text, nullable=False)
    approach_reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    step_by_step: Mapped[str] = mapped_column(Text, nullable=False)
    edge_cases: Mapped[list] = mapped_column(JSON, default=list)
    # Free-text (AI often writes a full sentence here), so not length-limited.
    time_complexity: Mapped[str] = mapped_column(Text, nullable=False)
    space_complexity: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    fill_in_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pattern_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_optimal: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=1)
    llm_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    question: Mapped["Question"] = relationship(back_populates="solutions")  # noqa: F821
