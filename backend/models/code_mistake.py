from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class CodeMistake(Base):
    __tablename__ = "code_mistakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    subtopic_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subtopic_knowledge.id"), nullable=True, index=True)
    subtopic_name: Mapped[str] = mapped_column(String(200), nullable=False)
    correct_code: Mapped[str] = mapped_column(Text, nullable=False)
    user_code: Mapped[str] = mapped_column(Text, nullable=False)
    context_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    weakness_tag: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
