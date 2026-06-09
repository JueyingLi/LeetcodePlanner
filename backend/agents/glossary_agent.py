from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent


class GlossaryEntry(BaseModel):
    definition: str = Field(description="1-3 sentence plain-English definition of the technique")
    how_it_works: str = Field(description="Detailed markdown explanation of how it works, step by step")
    example: str = Field(description="A concrete worked example in markdown: a small input and a walkthrough, with a short code sketch if helpful")


class GlossaryAgent(BaseLLMAgent):
    """Explains an algorithm/technique keyword (e.g. 'Sweep Line', 'Merge Sort')."""

    SYSTEM_PROMPT = """You are an algorithms teacher writing a glossary entry for a single technique.
The learner is preparing for Google interviews and wants to truly understand the keyword, not just a
one-liner. Produce three parts:

- definition: 1-3 sentences. What the technique IS and what problem shape it solves.
- how_it_works: a DETAILED markdown explanation of the mechanism. Use a numbered list of the core steps,
  state the key invariant, the data structure(s) involved, and the time/space complexity with a one-line
  reason. Mention the recognition signal ("reach for this when you see ...").
- example: ONE concrete worked example in markdown. Give a small concrete input, walk through what the
  technique does step by step on that input, and include a short Python code sketch (a few lines) if it
  clarifies. Keep it focused and correct.

Be accurate and concrete. If the term is ambiguous, explain the standard algorithmic meaning used in
competitive programming / LeetCode."""

    async def generate(
        self,
        db: AsyncSession,
        term: str,
        context: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> GlossaryEntry:
        user_msg = f"Explain the technique/keyword: \"{term}\"."
        if context:
            user_msg += f"\n\nReference notes (use if accurate):\n{context}"
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        return await self.call_llm_structured(messages, GlossaryEntry, db, provider, model)
