from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent
from backend.models.question import Question
from backend.schemas.solution import SolutionCreate
from backend.taxonomy import TAXONOMY


class QuestionClassification(BaseModel):
    topics: list[str] = Field(description="Canonical topic names from the provided taxonomy only")
    subtopics: list[str] = Field(description="Canonical subtopic names from the provided taxonomy only")
    reasoning: str = Field(description="Brief reason explaining the chosen labels")


def taxonomy_markdown() -> str:
    lines: list[str] = []
    for entry in TAXONOMY:
        lines.append(f"## {entry['topic']}")
        for st in entry["subtopics"]:
            desc = st.get("description") or st.get("key_signals") or ""
            lines.append(f"- **{st['name']}**: {desc}")
    return "\n".join(lines)


class QuestionClassifierAgent(BaseLLMAgent):
    SYSTEM_PROMPT = """You classify a LeetCode question into canonical topics and subtopics.

Use ONLY labels from the provided taxonomy. Do not invent new names.
Prefer precise algorithmic subtopics over broad categories.
Choose 1-3 topics and 2-6 subtopics.

Use the generated description, examples, observations, approaches, and code. The best labels should reflect the actual accepted/optimal approaches, not only words in the title.

Rules:
- Include a subtopic only if it is genuinely used or strongly needed by the solution.
- If an approach is a major alternative but not optimal, include it only when it is useful for study classification.
- Each selected subtopic must belong to one selected topic.
- If uncertain, choose fewer labels and explain why.
- Return canonical casing exactly as written in the taxonomy."""

    async def classify(
        self,
        db: AsyncSession,
        question: Question,
        description: str | None,
        solutions: list[SolutionCreate],
        provider: str | None = None,
        model: str | None = None,
    ) -> QuestionClassification:
        solution_text = []
        for sol in solutions:
            solution_text.append(
                "\n".join(
                    [
                        f"Approach: {sol.approach_name}",
                        f"Observation: {sol.initial_observation}",
                        f"Reasoning: {sol.approach_reasoning}",
                        f"Steps: {sol.step_by_step}",
                        f"Optimal: {sol.is_optimal}",
                        f"Code:\n{sol.code}",
                    ]
                )
            )

        user_msg = f"""Classify this question using the taxonomy below.

# Taxonomy
{taxonomy_markdown()}

# Question
Title: {question.title}
Number: {question.number or 'N/A'}
Difficulty: {question.difficulty.value if hasattr(question.difficulty, 'value') else question.difficulty}
Existing topics: {', '.join(question.topics or []) or 'None'}
Existing subtopics: {', '.join(question.subtopics or []) or 'None'}

# Generated description
{description or question.description or 'N/A'}

# Generated approaches and code
{chr(10).join(solution_text)}
"""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        return await self.call_llm_structured(messages, QuestionClassification, db, provider, model)
