from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.progress import UserProgress
from backend.models.question import Question, Status
from backend.models.question_links import QuestionSubtopic, QuestionTopic
from backend.schemas.question import QuestionCreate, QuestionUpdate
from backend.services.question_link_service import sync_question_links


async def list_questions(
    db: AsyncSession,
    user_id: str,
    topic: str | None = None,
    difficulty: str | None = None,
    status: str | None = None,
    source: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Question], int]:
    query = select(Question).options(selectinload(Question.solutions))
    count_query = select(func.count(Question.id))

    if status:
        # Status is per-user (UserProgress). A question with no progress row for
        # this user is implicitly TODO.
        join_on = and_(
            UserProgress.question_id == Question.id,
            UserProgress.user_id == user_id,
        )
        query = query.outerjoin(UserProgress, join_on)
        count_query = count_query.outerjoin(UserProgress, join_on)
        if status == Status.TODO.value:
            status_filter = or_(UserProgress.id.is_(None), UserProgress.status == Status.TODO)
        else:
            status_filter = UserProgress.status == status
        query = query.where(status_filter)
        count_query = count_query.where(status_filter)

    if topic:
        topic_qids = select(QuestionTopic.question_id).where(QuestionTopic.topic_name.ilike(topic)).scalar_subquery()
        query = query.where(Question.id.in_(topic_qids))
        count_query = count_query.where(Question.id.in_(topic_qids))
    if difficulty:
        query = query.where(Question.difficulty == difficulty)
        count_query = count_query.where(Question.difficulty == difficulty)
    if search:
        query = query.where(Question.title.ilike(f"%{search}%"))
        count_query = count_query.where(Question.title.ilike(f"%{search}%"))
    if source:
        query = query.where(Question.sources.contains(source))
        count_query = count_query.where(Question.sources.contains(source))

    query = query.order_by(Question.updated_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    count_result = await db.execute(count_query)

    return list(result.scalars().all()), count_result.scalar() or 0


async def get_status_map(
    db: AsyncSession, user_id: str, question_ids: list[int]
) -> dict[int, str]:
    """Map question_id -> per-user status string for questions that have a
    progress row. Missing entries imply TODO."""
    if not question_ids:
        return {}
    result = await db.execute(
        select(UserProgress.question_id, UserProgress.status).where(
            UserProgress.user_id == user_id,
            UserProgress.question_id.in_(question_ids),
        )
    )
    out: dict[int, str] = {}
    for qid, st in result.all():
        out[qid] = st.value if hasattr(st, "value") else st
    return out


async def set_status(
    db: AsyncSession, user_id: str, question_id: int, status: Status
) -> UserProgress:
    """Upsert the per-user study status for a question."""
    from backend.services.scheduler_service import sm2_update

    result = await db.execute(
        select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.question_id == question_id,
        )
    )
    progress = result.scalar_one_or_none()
    if not progress:
        progress = UserProgress(user_id=user_id, question_id=question_id)
        db.add(progress)
    progress.status = status
    if status == Status.DONE:
        sm2_update(progress, 4)
    elif status == Status.REWORK:
        sm2_update(progress, 2)
    await db.commit()
    await db.refresh(progress)
    return progress


async def get_question(db: AsyncSession, question_id: int) -> Question | None:
    result = await db.execute(
        select(Question)
        .options(selectinload(Question.solutions))
        .where(Question.id == question_id)
    )
    return result.scalar_one_or_none()


async def get_question_by_number(db: AsyncSession, number: int) -> Question | None:
    result = await db.execute(select(Question).where(Question.number == number))
    return result.scalar_one_or_none()


async def create_question(db: AsyncSession, data: QuestionCreate) -> Question:
    question = Question(**data.model_dump())
    db.add(question)
    await db.commit()
    await db.refresh(question)
    await sync_question_links(db, question)
    await db.commit()
    return question


async def update_question(db: AsyncSession, question_id: int, data: QuestionUpdate) -> Question | None:
    question = await get_question(db, question_id)
    if not question:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(question, key, value)
    await db.commit()
    await db.refresh(question)
    if any(k in update_data for k in ("topics", "subtopics", "sources")):
        await sync_question_links(db, question)
        await db.commit()
    return question


async def delete_question(db: AsyncSession, question_id: int) -> bool:
    question = await get_question(db, question_id)
    if not question:
        return False
    await db.delete(question)
    await db.commit()
    return True


async def get_topics(db: AsyncSession) -> list[str]:
    result = await db.execute(select(Question.topics))
    topics_set = set()
    for row in result.all():
        if row[0]:
            for t in row[0]:
                topics_set.add(t)
    return sorted(topics_set)


async def get_stats(db: AsyncSession, user_id: str) -> dict:
    total = (await db.execute(select(func.count(Question.id)))).scalar() or 0

    # Per-user status counts. Questions without a progress row are TODO.
    by_status = {s.value: 0 for s in Status}
    rows = (await db.execute(
        select(UserProgress.status, func.count(UserProgress.id))
        .where(UserProgress.user_id == user_id)
        .group_by(UserProgress.status)
    )).all()
    rows_with_progress = 0
    for st, count in rows:
        key = st.value if hasattr(st, "value") else st
        by_status[key] = count
        rows_with_progress += count
    by_status[Status.TODO.value] += max(0, total - rows_with_progress)

    by_difficulty = {}
    for row in (await db.execute(
        select(Question.difficulty, func.count(Question.id)).group_by(Question.difficulty)
    )).all():
        by_difficulty[row[0].value if hasattr(row[0], "value") else row[0]] = row[1]
    return {"total": total, "by_status": by_status, "by_difficulty": by_difficulty}
