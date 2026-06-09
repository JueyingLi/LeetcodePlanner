from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class User(Base):
    """Local mirror of a Supabase auth user, keyed by the Supabase UUID.

    Rows are created just-in-time on the first authenticated request
    (see backend.auth.get_current_user).
    """

    __tablename__ = "users"

    # Matches Supabase auth.users.id (UUID), stored as text for portability.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Per-user interview date (replaces the old global JSON setting).
    interview_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
