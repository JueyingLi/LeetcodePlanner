from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.tutor_agent import TutorAgent
from backend.models.pattern_clarification import QuestionClarification
from backend.models.progress import UserProgress
from backend.models.question import Difficulty, Question, Status
from backend.models.question_links import QuestionSubtopic, QuestionTopic
from backend.models.solution import Solution
from backend.models.subtopic import SubtopicKnowledge
from backend.services import scheduler_service


async def _optimal_solution(db: AsyncSession, question_id: int) -> Solution | None:
    result = await db.execute(
        select(Solution)
        .where(Solution.question_id == question_id)
        .order_by(Solution.is_optimal.desc(), Solution.sort_order.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_browse_deck(
    db: AsyncSession,
    topic: str | None = None,
    difficulty: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Questions that have a solution with pattern_analysis, for the browsable deck."""
    has_analysis = (
        select(Solution.question_id)
        .where(Solution.pattern_analysis.is_not(None))
        .distinct()
        .scalar_subquery()
    )
    query = select(Question).where(Question.id.in_(has_analysis))
    if topic:
        topic_qids = (
            select(QuestionTopic.question_id).where(QuestionTopic.topic_name.ilike(topic))
            .union(
                select(QuestionSubtopic.question_id)
                .join(SubtopicKnowledge, SubtopicKnowledge.id == QuestionSubtopic.subtopic_id)
                .where(SubtopicKnowledge.name.ilike(topic))
            )
        ).scalar_subquery()
        query = query.where(Question.id.in_(topic_qids))
    if difficulty:
        try:
            query = query.where(Question.difficulty == Difficulty(difficulty))
        except ValueError:
            pass
    query = query.order_by(Question.frequency.desc(), Question.number).limit(limit)
    result = await db.execute(query)
    questions = list(result.scalars().all())

    if not questions:
        return []

    qids = [q.id for q in questions]
    sol_result = await db.execute(
        select(Solution)
        .where(Solution.question_id.in_(qids), Solution.pattern_analysis.is_not(None))
        .order_by(Solution.is_optimal.desc(), Solution.sort_order.desc())
    )
    pa_by_q: dict[int, dict] = {}
    for sol in sol_result.scalars().all():
        if sol.question_id not in pa_by_q:
            pa_by_q[sol.question_id] = sol.pattern_analysis

    deck = []
    for q in questions:
        pa = pa_by_q.get(q.id)
        if not pa:
            continue
        deck.append({
            "id": q.id,
            "number": q.number,
            "title": q.title,
            "difficulty": q.difficulty,
            "topics": q.topics or [],
            "subtopics": q.subtopics or [],
            "pattern_analysis": pa,
        })
    return deck


async def get_pattern_analysis(db: AsyncSession, question_id: int) -> dict | None:
    """Get the pattern_analysis for a question from its optimal solution."""
    sol = await _optimal_solution(db, question_id)
    if sol and sol.pattern_analysis:
        return sol.pattern_analysis
    return None


async def completed_question_ids(db: AsyncSession, user_id: str, qids: list[int]) -> set[int]:
    if not qids:
        return set()
    rows = (await db.execute(
        select(UserProgress.question_id).where(
            UserProgress.user_id == user_id,
            UserProgress.question_id.in_(qids),
            UserProgress.status == Status.DONE,
        )
    )).scalars().all()
    return set(rows)


async def record_review(
    db: AsyncSession,
    user_id: str,
    question_id: int,
    quality: int,
    notes: str | None = None,
):
    progress = await scheduler_service.record_review(db, user_id, question_id, quality)
    return progress


async def ask(
    db: AsyncSession,
    user_id: str,
    question: Question,
    user_question: str,
    step_kind: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> QuestionClarification:
    agent = TutorAgent()
    answer = await agent.answer(db, question, user_question, step_kind, provider, model)
    clarification = QuestionClarification(
        user_id=user_id,
        question_id=question.id,
        step_kind=step_kind,
        user_question=user_question,
        answer=answer,
    )
    db.add(clarification)
    await db.commit()
    await db.refresh(clarification)
    return clarification
