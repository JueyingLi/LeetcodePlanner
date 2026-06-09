from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class SubtopicReview(Base):
    __tablename__ = "subtopic_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "subtopic_id", name="uq_subtopic_review_user_subtopic"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    subtopic_id: Mapped[int] = mapped_column(Integer, ForeignKey("subtopic_knowledge.id"), nullable=False)
    quality_history: Mapped[list] = mapped_column(JSON, default=list)
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    subtopic: Mapped["SubtopicKnowledge"] = relationship()  # noqa: F821


class QuestionSourcePost(Base):
    __tablename__ = "question_source_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="paste", nullable=False, index=True)
    uuid: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    topic_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    slug: Mapped[str | None] = mapped_column(String(240), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_from_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at_from_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    extracted_questions: Mapped[list] = mapped_column(JSON, default=list)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class UserStudyPreference(Base):
    __tablename__ = "user_study_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_study_preferences_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    review_count: Mapped[int] = mapped_column(Integer, default=5)
    template_count: Mapped[int] = mapped_column(Integer, default=3)
    google_count: Mapped[int] = mapped_column(Integer, default=5)
    hard_count: Mapped[int] = mapped_column(Integer, default=2)
    pattern_count: Mapped[int] = mapped_column(Integer, default=3)
    daily_refresh_hour: Mapped[int] = mapped_column(Integer, default=5)
    timezone_offset: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StudyPlan(Base):
    __tablename__ = "study_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "plan_date", name="uq_study_plan_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    interview_target: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    regenerated_count: Mapped[int] = mapped_column(Integer, default=0)
    markdown_snapshot: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)

    sessions: Mapped[list["StudyPlanSession"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="StudyPlanSession.sort_order"
    )


class StudyPlanSession(Base):
    __tablename__ = "study_plan_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("study_plans.id"), nullable=False, index=True)
    session_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=0)

    plan: Mapped[StudyPlan] = relationship(back_populates="sessions")
    items: Mapped[list["StudyPlanItem"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="StudyPlanItem.sort_order"
    )


class StudyPlanItem(Base):
    __tablename__ = "study_plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("study_plan_sessions.id"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    question_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("questions.id"), nullable=True)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subtopic_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subtopic_knowledge.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="not_started", nullable=False, index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    session: Mapped[StudyPlanSession] = relationship(back_populates="items")
    subtopic: Mapped["SubtopicKnowledge | None"] = relationship()  # noqa: F821
