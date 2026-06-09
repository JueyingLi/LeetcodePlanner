from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.question import Question
from backend.models.question_links import QuestionSubtopic
from backend.models.subtopic import SubtopicKnowledge
from backend.schemas.subtopic import SubtopicCreate, SubtopicUpdate


EXTRA_SUBTOPIC_ALIASES: dict[str, list[str]] = {
    # Older imported questions used broad tags while the newer taxonomy splits
    # them into more teachable patterns.
    "bfs queue": ["DFS / BFS"],
    "bfs": ["DFS / BFS"],
    "dfs": ["DFS / BFS"],
    "fast slow pointers": ["Reverse / Merge"],
    "merge intervals": ["Sweep Line"],
    "heap greedy": ["Sorting + Greedy", "Priority Queue / Heap"],
}


def _subtopic_match_names(name: str) -> list[str]:
    from backend.taxonomy import OLD_TO_NEW

    values: list[str] = [name]
    name_lower = name.lower()

    for old, new in OLD_TO_NEW.items():
        if new.lower() == name_lower:
            values.append(old)

    values.extend(EXTRA_SUBTOPIC_ALIASES.get(name_lower, []))

    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(value.strip())
    return deduped


def _subtopic_filter(name: str):
    filters = [
        cast(Question.subtopics, String).ilike(f'%"{match_name}"%')
        for match_name in _subtopic_match_names(name)
    ]
    return or_(*filters)


async def list_subtopics(
    db: AsyncSession,
    category: str | None = None,
    include_variants: bool = False,
) -> list[dict]:
    query = (
        select(SubtopicKnowledge)
        .options(selectinload(SubtopicKnowledge.children), selectinload(SubtopicKnowledge.parent))
    )
    if not include_variants:
        query = query.where(SubtopicKnowledge.parent_id.is_(None))
    if category:
        query = query.where(SubtopicKnowledge.category == category)
    query = query.order_by(SubtopicKnowledge.category, SubtopicKnowledge.name)
    result = await db.execute(query)
    subtopics = list(result.scalars().all())

    enriched = []
    for st in subtopics:
        count_result = await db.execute(
            select(func.count(QuestionSubtopic.id))
            .where(QuestionSubtopic.subtopic_id == st.id)
        )
        count = count_result.scalar() or 0
        d = {**_to_dict(st), "question_count": count}
        enriched.append(d)
    return enriched


async def get_subtopic(db: AsyncSession, subtopic_id: int) -> SubtopicKnowledge | None:
    result = await db.execute(
        select(SubtopicKnowledge)
        .options(selectinload(SubtopicKnowledge.children), selectinload(SubtopicKnowledge.parent))
        .where(SubtopicKnowledge.id == subtopic_id)
    )
    return result.scalar_one_or_none()


async def get_subtopic_by_name(db: AsyncSession, name: str) -> SubtopicKnowledge | None:
    result = await db.execute(
        select(SubtopicKnowledge).where(
            func.lower(SubtopicKnowledge.name) == name.lower()
        )
    )
    return result.scalar_one_or_none()


async def create_subtopic(db: AsyncSession, data: SubtopicCreate) -> SubtopicKnowledge:
    subtopic = SubtopicKnowledge(**data.model_dump())
    db.add(subtopic)
    await db.commit()
    await db.refresh(subtopic)
    return subtopic


async def update_subtopic(
    db: AsyncSession, subtopic_id: int, data: SubtopicUpdate
) -> SubtopicKnowledge | None:
    subtopic = await get_subtopic(db, subtopic_id)
    if not subtopic:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(subtopic, key, value)
    await db.commit()
    await db.refresh(subtopic)
    return subtopic


async def delete_subtopic(db: AsyncSession, subtopic_id: int) -> bool:
    subtopic = await get_subtopic(db, subtopic_id)
    if not subtopic:
        return False
    await db.delete(subtopic)
    await db.commit()
    return True


async def ensure_subtopics_exist(
    db: AsyncSession, subtopics: list[str], category: str
) -> None:
    for name in subtopics:
        name_clean = name.strip().lower()
        if not name_clean:
            continue
        existing = await get_subtopic_by_name(db, name_clean)
        if not existing:
            st = SubtopicKnowledge(name=name_clean, category=category)
            db.add(st)
    await db.commit()


async def get_categories(db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(SubtopicKnowledge.category)
        .distinct()
        .order_by(SubtopicKnowledge.category)
    )
    return [row[0] for row in result.all()]


async def get_questions_by_subtopic(
    db: AsyncSession, subtopic_name: str
) -> list[Question]:
    # Primary: join table lookup
    st = (await db.execute(
        select(SubtopicKnowledge).where(SubtopicKnowledge.name.ilike(subtopic_name))
    )).scalar_one_or_none()
    if st:
        result = await db.execute(
            select(Question)
            .join(QuestionSubtopic, QuestionSubtopic.question_id == Question.id)
            .where(QuestionSubtopic.subtopic_id == st.id)
            .order_by(Question.difficulty, Question.title)
        )
        questions = list(result.scalars().all())
        if questions:
            return questions
    # Fallback: JSON cast (for questions not yet migrated to join tables)
    result = await db.execute(
        select(Question)
        .where(_subtopic_filter(subtopic_name))
        .order_by(Question.difficulty, Question.title)
    )
    return list(result.scalars().all())


async def get_all_subtopic_names(db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(SubtopicKnowledge.name).order_by(SubtopicKnowledge.name)
    )
    return [row[0] for row in result.all()]


def _to_dict(st: SubtopicKnowledge) -> dict:
    variant_children = [
        {"id": c.id, "name": c.name, "slug": c.slug}
        for c in (st.children or [])
    ]
    return {
        "id": st.id,
        "name": st.name,
        "slug": st.slug,
        "category": st.category,
        "parent_id": st.parent_id,
        "parent_name": st.parent.name if st.parent else None,
        "description": st.description,
        "when_to_use": st.when_to_use,
        "key_signals": st.key_signals,
        "signals": st.signals,
        "variants": st.variants,
        "implementation_keys": st.implementation_keys,
        "common_pitfalls": st.common_pitfalls,
        "core_code": st.core_code,
        "breakdown": st.breakdown,
        "mental_model": st.mental_model,
        "recall_tasks": st.recall_tasks,
        "related_question_ids": st.related_question_ids,
        "comparison_same": st.comparison_same,
        "comparison_different": st.comparison_different,
        "comparison_when": st.comparison_when,
        "comparison_code": st.comparison_code,
        "variant_children": variant_children if variant_children else None,
        "created_at": st.created_at,
        "updated_at": st.updated_at,
    }
