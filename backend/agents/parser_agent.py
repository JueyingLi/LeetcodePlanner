from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent
from backend.schemas.question import QuestionCreate


class ParsedQuestionList(BaseModel):
    questions: list[QuestionCreate]


class ParserAgent(BaseLLMAgent):
    SYSTEM_PROMPT = """You are a parser that extracts LeetCode question information from free-text descriptions.
The user will paste text that may include question numbers, titles, difficulties, topics, and source information.

Extract each question into a structured format:
- number: LeetCode problem number (int or null if not mentioned)
- title: Problem title
- difficulty: "Easy", "Medium", or "Hard" (infer from context if not stated, default to "Medium")
- topics: List of topics this problem covers (e.g., ["Graph", "Dynamic Programming"]). A problem can belong to multiple topics. Use standard categories: "Array", "String", "Dynamic Programming", "Graph", "Tree", "Stack", "Heap", "Greedy", "Backtracking", "Math", "Binary Indexed Tree", "Sorting", "Design", "Geometry", "Linked List".
- subtopics: List of specific algorithm/data structure technique tags that would be used to solve this problem. Use standard competitive programming tags like: "two pointers", "sliding window", "binary search", "bfs", "dfs", "dp", "greedy", "backtracking", "trie", "union find", "monotonic stack", "heap", "topological sort", "segment tree", "bit manipulation", "prefix sum", "hash map", "linked list", "recursion", "divide and conquer", "math", "simulation". Pick 1-3 tags that best describe the solving techniques. If you know the problem, use accurate tags. If not, infer from the title and topic.
- frequency: 0.0-1.0 (default 0.5, increase for frequently mentioned problems)
- sources: List of source objects with "name" and "type" fields. Type is "company" for company-specific lists, "list" for curated lists
- url: LeetCode URL if determinable (format: https://leetcode.com/problems/slug-here/)
- status: Always "todo"

Be smart about inferring information:
- If the text says "Google past 3 months", create a source {"name": "Google 3 months", "type": "company"}
- If it mentions "Hot 100" or "Neetcode 150", create appropriate source tags
- Infer topics from problem titles when possible (e.g., "Two Sum" -> "Arrays", "Binary Tree Inorder" -> "Trees")
- Generate URL slugs from titles (lowercase, hyphens for spaces)"""

    async def parse(
        self,
        db: AsyncSession,
        text: str,
        default_source: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[QuestionCreate]:
        user_msg = f"Parse the following text and extract all LeetCode questions:\n\n{text}"
        if default_source:
            user_msg += f"\n\nDefault source for all questions: {default_source}"

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        result = await self.call_llm_structured(
            messages, ParsedQuestionList, db, provider, model
        )
        return result.questions
