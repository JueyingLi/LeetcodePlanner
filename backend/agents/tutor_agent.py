from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent
from backend.models.question import Question
from backend.models.solution import Solution


class TutorAnswer(BaseModel):
    answer: str = Field(description="A concise, teaching answer to the learner's question (markdown)")


class TutorAgent(BaseLLMAgent):
    """Answers a learner's clarifying question about a problem or its pattern analysis."""

    SYSTEM_PROMPT = """You are a patient algorithms tutor. The learner is drilling PATTERN RECOGNITION:
how to store the data, which algorithm to run, and how to optimize it. They will ask a clarifying
question about a specific problem (and possibly a specific recognition step).

- Answer directly and concisely in markdown. Get to the point.
- Teach the RECOGNITION cue, not just the fact: tie your answer back to "when you see X, think Y".
- When explaining a technique choice, connect concrete problem details to the needed state,
  operations, or invariant. Do not only name the technique.
- For DP, identify the repeated decision and exact subproblem state, such as
  `(day, holding, transactions_left)` for stock-with-k-transactions style problems.
- If they seem to have a misconception (e.g. they picked the wrong data structure), name it and correct it.
- Use a tiny concrete example if it removes confusion. Do NOT dump a full solution unless asked.
- If the question is ambiguous, answer the most useful interpretation."""

    async def answer(
        self,
        db: AsyncSession,
        question: Question,
        user_question: str,
        step_kind: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> str:
        sol = (await db.execute(
            select(Solution)
            .where(Solution.question_id == question.id, Solution.pattern_analysis.is_not(None))
            .order_by(Solution.is_optimal.desc())
            .limit(1)
        )).scalar_one_or_none()

        analysis = (sol.pattern_analysis if sol else None) or {}
        approaches_text = "\n".join(
            f"- [{a.get('category')}] {a.get('label')}: {a.get('why')}"
            for a in (analysis.get("approaches") or [])
        )

        user_msg = f"""Problem: {question.title} (#{question.number or 'N/A'})
{f"Description: {question.description}" if question.description else ""}
{f"Data characteristics: {analysis.get('data_characteristics')}" if analysis.get('data_characteristics') else ""}
{f"Goal: {analysis.get('goal')}" if analysis.get('goal') else ""}
{f"Approaches:\n{approaches_text}" if approaches_text else ""}
{f"The learner is asking about '{step_kind}'." if step_kind else ""}

Learner's question:
\"\"\"
{user_question}
\"\"\"
"""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        result = await self.call_llm_structured(messages, TutorAnswer, db, provider, model)
        return result.answer
