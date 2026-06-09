from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class GlossaryTerm(Base):
    """A cached, AI-generated explanation of an algorithm/technique keyword
    (e.g. "Sweep Line", "Merge Sort"). Shared/global and looked up by a
    normalized slug so the same term is generated once and reused everywhere."""

    __tablename__ = "glossary_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    how_it_works: Mapped[str] = mapped_column(Text, nullable=False, default="")
    example: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
