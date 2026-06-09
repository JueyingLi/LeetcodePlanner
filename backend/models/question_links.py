"""Normalized join tables for question-subtopic and question-topic linkage.

These replace the brittle JSON array columns (questions.topics, questions.subtopics)
as the source of truth for querying. The JSON columns are kept as a read cache
(populated on write) for API responses that need the flat list.
"""

from sqlalchemy import ForeignKey, Integer, String, Float
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class QuestionSubtopic(Base):
    __tablename__ = "question_subtopics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    subtopic_id: Mapped[int] = mapped_column(Integer, ForeignKey("subtopic_knowledge.id", ondelete="CASCADE"), nullable=False, index=True)


class QuestionTopic(Base):
    __tablename__ = "question_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)


class QuestionSourceLink(Base):
    __tablename__ = "question_source_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_post_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("question_source_posts.id", ondelete="SET NULL"), nullable=True, index=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="list")
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
