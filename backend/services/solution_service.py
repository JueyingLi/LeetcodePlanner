from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.question import Question
from backend.models.solution import Solution
from backend.schemas.solution import SolutionResponse
from backend.taxonomy import SUBTOPIC_TO_TOPIC, TOPIC_ORDER


async def get_solutions(db: AsyncSession, question_id: int) -> list[Solution]:
    result = await db.execute(
        select(Solution)
        .where(Solution.question_id == question_id)
        .order_by(Solution.sort_order)
    )
    return list(result.scalars().all())


async def has_solutions(db: AsyncSession, question_id: int) -> bool:
    result = await db.execute(
        select(Solution.id).where(Solution.question_id == question_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def generate_solutions(
    db: AsyncSession,
    question: Question,
    provider: str | None = None,
    model: str | None = None,
) -> list[Solution]:
    from backend.agents.solution_agent import SolutionAgent

    agent = SolutionAgent()
    result = await agent.generate(db, question, provider, model)

    existing = await get_solutions(db, question.id)
    if existing:
        for sol in existing:
            await db.delete(sol)
        await db.flush()

    if result.description:
        question.description = result.description
    if result.examples:
        question.examples = [e.model_dump() for e in result.examples]
    await _reclassify_question_from_solutions(db, question, result.description, result.solutions, provider, model)

    solutions = []
    for i, sol_data in enumerate(result.solutions):
        solution = Solution(
            question_id=question.id,
            approach_name=sol_data.approach_name,
            initial_observation=sol_data.initial_observation,
            approach_reasoning=sol_data.approach_reasoning,
            step_by_step=sol_data.step_by_step,
            edge_cases=[e.model_dump() for e in sol_data.edge_cases],
            time_complexity=sol_data.time_complexity,
            space_complexity=sol_data.space_complexity,
            code=sol_data.code,
            fill_in_code=sol_data.fill_in_code or "",
            is_optimal=sol_data.is_optimal,
            sort_order=i + 1,
            llm_provider=provider or "openai",
            llm_model=model,
            generated_at=datetime.now(timezone.utc),
        )
        db.add(solution)
        solutions.append(solution)

    await db.commit()
    for s in solutions:
        await db.refresh(s)

    return solutions


async def _reclassify_question_from_solutions(
    db: AsyncSession,
    question: Question,
    description: str | None,
    generated_solutions: list,
    provider: str | None,
    model: str | None,
) -> None:
    from backend.agents.question_classifier_agent import QuestionClassifierAgent
    from backend.services.question_link_service import sync_question_links

    agent = QuestionClassifierAgent()
    try:
        classification = await agent.classify(db, question, description, generated_solutions, provider, model)
    except Exception:
        return

    valid_topics = set(TOPIC_ORDER)
    valid_subtopics = {name.lower(): name for name in SUBTOPIC_TO_TOPIC}

    subtopics: list[str] = []
    for raw in classification.subtopics:
        canonical = valid_subtopics.get(raw.lower().strip())
        if canonical and canonical not in subtopics:
            subtopics.append(canonical)

    topics: list[str] = []
    for raw in classification.topics:
        topic = raw.strip()
        if topic in valid_topics and topic not in topics:
            topics.append(topic)
    for subtopic in subtopics:
        topic = SUBTOPIC_TO_TOPIC.get(subtopic.lower())
        if topic and topic not in topics:
            topics.append(topic)

    if not topics and not subtopics:
        return

    question.topics = topics
    question.subtopics = subtopics
    await db.flush()
    await sync_question_links(db, question)


async def delete_solution(db: AsyncSession, solution_id: int) -> bool:
    result = await db.execute(select(Solution).where(Solution.id == solution_id))
    solution = result.scalar_one_or_none()
    if not solution:
        return False
    await db.delete(solution)
    await db.commit()
    return True
