from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    pass


class SubtopicKnowledge(Base):
    __tablename__ = "subtopic_knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    slug: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subtopic_knowledge.id"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    when_to_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_signals: Mapped[str | None] = mapped_column(Text, nullable=True)
    signals: Mapped[list | None] = mapped_column(JSON, nullable=True)
    variants: Mapped[str | None] = mapped_column(Text, nullable=True)
    implementation_keys: Mapped[str | None] = mapped_column(Text, nullable=True)
    common_pitfalls: Mapped[str | None] = mapped_column(Text, nullable=True)
    core_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    mental_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    recall_tasks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    related_question_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    comparison_same: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparison_different: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparison_when: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparison_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    parent: Mapped["SubtopicKnowledge | None"] = relationship(
        "SubtopicKnowledge", remote_side=[id], back_populates="children",
    )
    children: Mapped[list["SubtopicKnowledge"]] = relationship(
        "SubtopicKnowledge", back_populates="parent", lazy="selectin",
    )
