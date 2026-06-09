from datetime import datetime, timedelta, timezone

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.progress import UserProgress
from backend.models.question import Question, Status
from backend.models.question_links import QuestionSubtopic, QuestionTopic
from backend.models.quiz import QuizAttempt
from backend.models.solution import Solution
from backend.models.subtopic import SubtopicKnowledge


def sm2_update(progress: UserProgress, quality: int) -> UserProgress:
    """Doubling-interval spaced repetition: 1, 2, 4, 8, 16… days."""
    quality = max(0, min(5, quality))

    if quality >= 3:
        if progress.repetitions == 0:
            progress.interval = 1
        else:
            progress.interval = progress.interval * 2
        progress.repetitions += 1
    else:
        progress.repetitions = 0
        progress.interval = 1

    now = datetime.now(timezone.utc)
    progress.last_reviewed = now
    progress.next_review = now + timedelta(days=progress.interval)

    history = list(progress.quality_history or [])
    history.append(quality)
    progress.quality_history = history[-20:]

    return progress


async def record_review(
    db: AsyncSession, user_id: str, question_id: int, quality: int
) -> UserProgress:
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

    sm2_update(progress, quality)
    await db.commit()
    await db.refresh(progress)
    return progress


async def get_daily_plan(
    db: AsyncSession, user_id: str, interview_date_str: str | None = None
) -> dict:
    now = datetime.now(timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59)

    date_str = interview_date_str or settings.interview_date
    try:
        interview_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        interview_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    delta = interview_date - now
    total_seconds = max(0, int(delta.total_seconds()))
    days_until = total_seconds // 86400
    hours_until = (total_seconds % 86400) // 3600
    minutes_until = (total_seconds % 3600) // 60

    due_result = await db.execute(
        select(Question)
        .join(UserProgress, UserProgress.question_id == Question.id)
        .where(UserProgress.user_id == user_id)
        .where(UserProgress.next_review <= today_end)
        .order_by(UserProgress.next_review)
        .limit(settings.daily_question_limit)
    )
    due_questions = list(due_result.scalars().all())

    rework_result = await db.execute(
        select(Question)
        .join(UserProgress, and_(
            UserProgress.question_id == Question.id,
            UserProgress.user_id == user_id,
        ))
        .where(UserProgress.status == Status.REWORK)
        .where(Question.id.not_in([q.id for q in due_questions]))
        .limit(5)
    )
    rework_questions = list(rework_result.scalars().all())

    remaining_slots = settings.daily_question_limit - len(due_questions) - len(rework_questions)
    new_questions = []
    if remaining_slots > 0:
        existing_ids = [q.id for q in due_questions + rework_questions]
        # "New" = TODO for this user: either no progress row, or status TODO.
        new_result = await db.execute(
            select(Question)
            .outerjoin(UserProgress, and_(
                UserProgress.question_id == Question.id,
                UserProgress.user_id == user_id,
            ))
            .where(or_(UserProgress.id.is_(None), UserProgress.status == Status.TODO))
            .where(Question.id.not_in(existing_ids) if existing_ids else True)
            .order_by(Question.frequency.desc())
            .limit(remaining_slots)
        )
        new_questions = list(new_result.scalars().all())

    items = []
    for q in rework_questions:
        items.append(_plan_item(q, "rework", "rework"))
    for q in due_questions:
        items.append(_plan_item(q, "review_due", "review"))
    for q in new_questions:
        items.append(_plan_item(q, "new", "todo"))

    question_ids = [item["question_id"] for item in items]
    missing_solutions_count = 0
    if question_ids:
        has_sol_result = await db.execute(
            select(Solution.question_id).distinct().where(
                Solution.question_id.in_(question_ids)
            )
        )
        has_sol_ids = {row[0] for row in has_sol_result.all()}
        for item in items:
            item["has_solutions"] = item["question_id"] in has_sol_ids
        missing_solutions_count = len(question_ids) - len(has_sol_ids)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "items": items,
        "review_count": len(due_questions) + len(rework_questions),
        "new_count": len(new_questions),
        "days_until_interview": days_until,
        "hours_until_interview": hours_until,
        "minutes_until_interview": minutes_until,
        "missing_solutions_count": missing_solutions_count,
    }


def _plan_item(q: Question, reason: str, status: str = "todo") -> dict:
    return {
        "question_id": q.id,
        "question_title": q.title,
        "question_number": q.number,
        "difficulty": q.difficulty.value if hasattr(q.difficulty, "value") else q.difficulty,
        "topics": q.topics or [],
        "status": status,
        "reason": reason,
        "next_review": None,
        "has_solutions": False,
    }


async def generate_today_solutions(db: AsyncSession, user_id: str) -> dict:
    from backend.services import solution_service

    plan = await get_daily_plan(db, user_id)
    question_ids = [item["question_id"] for item in plan["items"]]
    if not question_ids:
        return {"generated": 0, "total_missing": 0, "errors": []}

    has_sol = await db.execute(
        select(Solution.question_id).distinct().where(
            Solution.question_id.in_(question_ids)
        )
    )
    has_sol_ids = {row[0] for row in has_sol.all()}
    missing_ids = [qid for qid in question_ids if qid not in has_sol_ids]

    if not missing_ids:
        return {"generated": 0, "total_missing": 0, "errors": []}

    result = await db.execute(
        select(Question).where(Question.id.in_(missing_ids))
    )
    missing = list(result.scalars().all())

    generated = 0
    errors = []
    for q in missing:
        try:
            await solution_service.generate_solutions(db, q)
            generated += 1
        except Exception as e:
            errors.append({"question_id": q.id, "title": q.title, "error": str(e)})

    return {"generated": generated, "total_missing": len(missing), "errors": errors[:10]}


async def get_random_question(db: AsyncSession, exclude_ids: list[int] | None = None) -> dict | None:
    query = select(Question)
    if exclude_ids:
        query = query.where(Question.id.not_in(exclude_ids))
    query = query.order_by(func.random()).limit(1)
    result = await db.execute(query)
    q = result.scalar_one_or_none()
    if not q:
        return None
    return _plan_item(q, "random")


async def search_pick_questions(db: AsyncSession, query: str, limit: int = 10) -> list[dict]:
    topic_qids = (
        select(QuestionTopic.question_id)
        .where(QuestionTopic.topic_name.ilike(f"%{query}%"))
        .scalar_subquery()
    )
    subtopic_qids = (
        select(QuestionSubtopic.question_id)
        .join(SubtopicKnowledge, SubtopicKnowledge.id == QuestionSubtopic.subtopic_id)
        .where(SubtopicKnowledge.name.ilike(f"%{query}%"))
        .scalar_subquery()
    )
    stmt = select(Question).where(
        (Question.title.ilike(f"%{query}%"))
        | (Question.id.in_(topic_qids))
        | (Question.id.in_(subtopic_qids))
    ).order_by(Question.frequency.desc()).limit(limit)
    result = await db.execute(stmt)
    return [_plan_item(q, "picked") for q in result.scalars().all()]


async def get_refill_questions(
    db: AsyncSession, user_id: str, exclude_ids: list[int] | None = None, count: int = 5
) -> list[dict]:
    # TODO for this user: no progress row, or status TODO.
    query = (
        select(Question)
        .outerjoin(UserProgress, and_(
            UserProgress.question_id == Question.id,
            UserProgress.user_id == user_id,
        ))
        .where(or_(UserProgress.id.is_(None), UserProgress.status == Status.TODO))
    )
    if exclude_ids:
        query = query.where(Question.id.not_in(exclude_ids))
    query = query.order_by(Question.frequency.desc()).limit(count)
    result = await db.execute(query)
    return [_plan_item(q, "new", "todo") for q in result.scalars().all()]


async def get_weakness_stats(db: AsyncSession, user_id: str) -> list[dict]:
    result = await db.execute(
        select(
            Question.topics,
            QuizAttempt.is_correct,
        )
        .join(QuizAttempt, QuizAttempt.question_id == Question.id)
        .where(QuizAttempt.user_id == user_id)
        .where(QuizAttempt.is_correct.is_not(None))
    )
    topic_stats: dict[str, dict] = {}
    for topics, is_correct in result.all():
        topics_list = topics or ["Unknown"]
        for topic in topics_list:
            if topic not in topic_stats:
                topic_stats[topic] = {"attempts": 0, "correct": 0}
            topic_stats[topic]["attempts"] += 1
            topic_stats[topic]["correct"] += 1 if is_correct else 0

    stats = []
    for topic, data in topic_stats.items():
        if data["attempts"] < 3:
            continue
        accuracy = data["correct"] / data["attempts"]
        stats.append({
            "topic": topic,
            "subtopic": None,
            "attempts": data["attempts"],
            "correct": data["correct"],
            "accuracy": round(accuracy, 3),
        })
    return sorted(stats, key=lambda x: x["accuracy"])
