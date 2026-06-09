from pydantic import BaseModel, Field

from backend.agents.base import BaseLLMAgent


class FoundQuestion(BaseModel):
    number: int = Field(description="LeetCode problem number")
    title: str = Field(description="Exact LeetCode problem title")
    difficulty: str = Field(description="Easy, Medium, or Hard")
    url: str = Field(description="LeetCode URL like https://leetcode.com/problems/slug/")
    why: str = Field(description="1-2 sentences on why this problem is a good example of the pattern")


class QuestionFinderResponse(BaseModel):
    questions: list[FoundQuestion]


class QuestionFinderAgent(BaseLLMAgent):
    SYSTEM_PROMPT = """You are a LeetCode expert. Given a pattern/technique name and description,
return real LeetCode problems that are excellent examples of this pattern.

Rules:
- Return EXACTLY the number of problems requested
- Use REAL LeetCode problem numbers and titles (do not invent problems)
- Prioritize Medium and Hard difficulty — include at most 1 Easy
- Pick problems that are well-known, frequently asked at top companies, and clearly demonstrate the pattern
- Include the exact LeetCode URL slug
- For "why", explain what makes this problem a strong example of the pattern"""

    async def find_questions(
        self,
        db,
        pattern_name: str,
        pattern_description: str | None,
        count: int = 3,
        exclude_numbers: list[int] | None = None,
    ) -> list[dict]:
        exclude_text = ""
        if exclude_numbers:
            exclude_text = f"\n\nDo NOT include these problem numbers (already in the database): {exclude_numbers}"

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Pattern: {pattern_name}\n"
                f"Description: {pattern_description or 'N/A'}\n\n"
                f"Find {count} LeetCode problems that are excellent examples of this pattern. "
                f"Prioritize Medium and Hard problems."
                f"{exclude_text}"
            )},
        ]

        result = await self.call_llm_structured(
            messages, QuestionFinderResponse, db
        )

        return [q.model_dump() for q in result.questions]
