import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models.question import Question
from backend.models.solution import Solution

logger = logging.getLogger(__name__)


async def _solutions_for(db: AsyncSession, question_id: int) -> list[Solution]:
    result = await db.execute(
        select(Solution).where(Solution.question_id == question_id).order_by(Solution.sort_order)
    )
    return list(result.scalars().all())


async def ensure_analysis(
    db: AsyncSession,
    question: Question,
    *,
    solutions: list[Solution] | None = None,
    force: bool = False,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Generate pattern_analysis on the optimal solution (LLM-powered).

    Pattern analysis lives on Solution now. We generate it for the optimal
    solution (or last solution if none marked optimal). Returns True if a
    pattern_analysis was written.
    """
    if solutions is None:
        solutions = await _solutions_for(db, question.id)
    if not solutions:
        logger.info("skip pattern analysis for question %s: no solutions yet", question.id)
        return False

    target = next((s for s in solutions if s.is_optimal), solutions[-1])
    if target.pattern_analysis and not force:
        return False

    from backend.agents.pattern_analysis_agent import PatternAnalysisAgent

    agent = PatternAnalysisAgent()
    try:
        result = await agent.generate(db, question, target, provider, model)
        target.pattern_analysis = result.model_dump()
        await db.commit()
        return True
    except Exception as e:
        logger.warning("pattern analysis generation failed for question %s: %s", question.id, e)
        return False


async def prepare_question(
    db: AsyncSession,
    question: Question,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Make a question drill-ready: generate solutions if missing, then pattern analysis.

    Returns True if the question ended up with a pattern analysis on its optimal solution.
    """
    from backend.services import solution_service

    solutions = await _solutions_for(db, question.id)

    if not solutions:
        try:
            solutions = await solution_service.generate_solutions(db, question, provider, model)
        except Exception as e:
            logger.warning("could not generate solutions for question %s: %s", question.id, e)
            return False

    target = next((s for s in solutions if s.is_optimal), solutions[-1])
    if target.pattern_analysis:
        return True

    return await ensure_analysis(db, question, solutions=solutions, force=True, provider=provider, model=model)


async def generate_for_questions(
    question_ids: list[int],
    provider: str | None = None,
    model: str | None = None,
) -> int:
    """Fill missing pattern analyses for the given questions (FastAPI BackgroundTask).

    For each question lacking an analysis on its optimal solution, generates solutions
    first if needed, then the pattern analysis. Runs sequentially; best-effort per question.
    """
    if not question_ids:
        return 0
    async with async_session() as db:
        rows = (await db.execute(
            select(Question).where(Question.id.in_(question_ids))
        )).scalars().all()
        questions = list(rows)
        if not questions:
            return 0

        count = 0
        for q in questions:
            solutions = await _solutions_for(db, q.id)
            target = next((s for s in solutions if s.is_optimal), solutions[-1] if solutions else None)
            if target and target.pattern_analysis:
                continue
            try:
                if await prepare_question(db, q, provider, model):
                    count += 1
            except Exception as e:
                logger.warning("drill prep failed for question %s: %s", q.id, e)
        return count
