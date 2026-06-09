from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent
from backend.schemas.question import ExampleItem


class QuestionDescription(BaseModel):
    description: str = Field(description="Full problem description: what inputs are given, constraints, what to return")
    examples: list[ExampleItem] = Field(description="2-3 input/output examples with explanations")


class BatchDescriptionItem(BaseModel):
    number: int | None
    title: str
    description: str
    examples: list[ExampleItem]


class BatchDescriptionResult(BaseModel):
    questions: list[BatchDescriptionItem]


class DescriptionAgent(BaseLLMAgent):
    SYSTEM_PROMPT = """You are a LeetCode expert. Given problem titles/numbers, generate the full problem description and examples as they would appear on LeetCode.

For each problem provide:
- description: A clear problem statement in markdown format. Use paragraphs, **bold** for key terms, `code` for variable names, and bullet lists for constraints. Structure it as:
  1. Problem statement paragraph
  2. Input/output format
  3. **Constraints** section with bullet points (array sizes, value ranges, etc.)
- examples: 2-3 input/output examples. Each has "input" (function arguments), "output" (expected return), and "explanation" (why this output is correct).

Be accurate — these are well-known problems. If you know the exact problem, give the real description. If unsure, give a reasonable description based on the title."""

    async def generate_batch(
        self,
        db: AsyncSession,
        questions: list[dict],
        provider: str | None = None,
        model: str | None = None,
    ) -> list[BatchDescriptionItem]:
        lines = []
        for q in questions:
            num = q.get("number", "")
            title = q.get("title", "")
            lines.append(f"- #{num} {title}" if num else f"- {title}")

        user_msg = f"""Generate problem descriptions and examples for these LeetCode problems:

{chr(10).join(lines)}

Return accurate descriptions for each."""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        result = await self.call_llm_structured(
            messages, BatchDescriptionResult, db, provider, model
        )
        return result.questions
