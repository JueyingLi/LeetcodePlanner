"""Service for managing normalized question-subtopic/topic/source linkage.

Provides helpers to:
- Sync JSON arrays ↔ join tables on write
- Query questions by subtopic/topic using proper joins
- Migrate existing JSON data to join tables
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.question import Question
from backend.models.question_links import QuestionSourceLink, QuestionSubtopic, QuestionTopic
from backend.models.subtopic import SubtopicKnowledge


async def sync_question_links(db: AsyncSession, question: Question) -> None:
    """Sync join tables from the JSON arrays on a question. Call after any update to
    question.topics, question.subtopics, or question.sources."""
    qid = question.id

    # --- Topics ---
    await db.execute(delete(QuestionTopic).where(QuestionTopic.question_id == qid))
    for topic_name in (question.topics or []):
        db.add(QuestionTopic(question_id=qid, topic_name=topic_name))

    # --- Subtopics ---
    await db.execute(delete(QuestionSubtopic).where(QuestionSubtopic.question_id == qid))
    if question.subtopics:
        name_lower_map: dict[str, int] = {}
        rows = (await db.execute(select(SubtopicKnowledge.id, SubtopicKnowledge.name))).all()
        for sid, sname in rows:
            name_lower_map[sname.lower()] = sid
        for st_name in question.subtopics:
            st_id = name_lower_map.get(st_name.lower())
            if st_id:
                db.add(QuestionSubtopic(question_id=qid, subtopic_id=st_id))

    # --- Sources ---
    await db.execute(delete(QuestionSourceLink).where(QuestionSourceLink.question_id == qid))
    for src in (question.sources or []):
        if isinstance(src, dict):
            db.add(QuestionSourceLink(
                question_id=qid,
                source_name=src.get("name", ""),
                source_type=src.get("type", "list"),
            ))


async def questions_by_subtopic_name(db: AsyncSession, subtopic_name: str) -> list[Question]:
    """Find questions linked to a subtopic by name (via join table)."""
    result = await db.execute(
        select(Question)
        .join(QuestionSubtopic, QuestionSubtopic.question_id == Question.id)
        .join(SubtopicKnowledge, SubtopicKnowledge.id == QuestionSubtopic.subtopic_id)
        .where(SubtopicKnowledge.name.ilike(subtopic_name))
    )
    return list(result.scalars().all())


async def questions_by_subtopic_id(db: AsyncSession, subtopic_id: int) -> list[Question]:
    """Find questions linked to a subtopic by ID (via join table)."""
    result = await db.execute(
        select(Question)
        .join(QuestionSubtopic, QuestionSubtopic.question_id == Question.id)
        .where(QuestionSubtopic.subtopic_id == subtopic_id)
    )
    return list(result.scalars().all())


async def questions_by_topic(db: AsyncSession, topic_name: str) -> list[Question]:
    """Find questions linked to a topic (via join table)."""
    result = await db.execute(
        select(Question)
        .join(QuestionTopic, QuestionTopic.question_id == Question.id)
        .where(QuestionTopic.topic_name.ilike(topic_name))
    )
    return list(result.scalars().all())


async def question_ids_by_subtopic_names(db: AsyncSession, names: list[str]) -> set[int]:
    """Get question IDs matching any of the given subtopic names."""
    if not names:
        return set()
    result = await db.execute(
        select(QuestionSubtopic.question_id)
        .join(SubtopicKnowledge, SubtopicKnowledge.id == QuestionSubtopic.subtopic_id)
        .where(SubtopicKnowledge.name.in_(names))
    )
    return set(result.scalars().all())


async def question_ids_by_topics(db: AsyncSession, topics: list[str]) -> set[int]:
    """Get question IDs matching any of the given topics."""
    if not topics:
        return set()
    result = await db.execute(
        select(QuestionTopic.question_id)
        .where(QuestionTopic.topic_name.in_(topics))
    )
    return set(result.scalars().all())


async def question_ids_with_source(db: AsyncSession, source_name: str) -> set[int]:
    """Get question IDs that have a specific source (e.g. 'Google')."""
    result = await db.execute(
        select(QuestionSourceLink.question_id)
        .where(QuestionSourceLink.source_name.ilike(f"%{source_name}%"))
    )
    return set(result.scalars().all())


async def migrate_all_json_to_links(db: AsyncSession) -> int:
    """One-time migration: populate join tables from existing JSON arrays on all questions."""
    # Clear existing link data to avoid duplicates on re-run
    await db.execute(delete(QuestionTopic))
    await db.execute(delete(QuestionSubtopic))
    await db.execute(delete(QuestionSourceLink))

    questions = (await db.execute(select(Question))).scalars().all()

    # Pre-load subtopic name→id map
    st_rows = (await db.execute(select(SubtopicKnowledge.id, SubtopicKnowledge.name))).all()
    name_lower_map: dict[str, int] = {name.lower(): sid for sid, name in st_rows}

    count = 0
    for q in questions:
        # Topics
        for topic_name in (q.topics or []):
            db.add(QuestionTopic(question_id=q.id, topic_name=topic_name))

        # Subtopics
        for st_name in (q.subtopics or []):
            st_id = name_lower_map.get(st_name.lower())
            if st_id:
                db.add(QuestionSubtopic(question_id=q.id, subtopic_id=st_id))

        # Sources
        for src in (q.sources or []):
            if isinstance(src, dict):
                db.add(QuestionSourceLink(
                    question_id=q.id,
                    source_name=src.get("name", ""),
                    source_type=src.get("type", "list"),
                ))
        count += 1

    await db.flush()
    return count
