from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent

if TYPE_CHECKING:
    from backend.models.solution import Solution


class StepFeedback(BaseModel):
    step: str
    feedback: str
    score: int | None = Field(None, ge=1, le=5)
    suggestions: list[str] = Field(default_factory=list)


class FeedbackAgent(BaseLLMAgent):
    SYSTEM_PROMPT = """You are a coding interview coach helping someone prepare for tech company interviews. Your job is to TEACH, not just evaluate.

You will often be given a REFERENCE ANSWER — the known correct/optimal solution. Use it as the ground truth to judge the candidate's work. If the candidate's approach matches the reference (even if stated briefly or informally), treat it as CORRECT. Do NOT suggest alternative approaches unless the candidate's direction is genuinely wrong.

When reviewing the candidate's work:

1. **Judge against the reference first** — if a reference answer is provided, compare the candidate's work to it. A brief answer that matches the correct approach deserves a high score. "Use segment tree" is correct if the reference says segment tree.
2. **Acknowledge what's correct** — start with what they got right so they know what to keep.
3. **Give the next concrete step** — don't just say "think about layers." Instead say: "The matrix has `min(m, n) // 2` layers. Layer `k` starts at `(k, k)` and ends at `(m-1-k, n-1-k)`. Try extracting one layer's elements into a list first."
4. **Provide a specific hint or example** — if they're stuck, give a small concrete example.
5. **Connect to patterns they should recognize** — "This is similar to spiral matrix traversal — if you can traverse in spiral order, you can rotate by shifting elements along that path."

Score from 1-5:
1 = Wrong direction — redirect with the right starting point
2 = Right idea but incomplete — give the specific missing piece
3 = Decent — point out the gap and show how to close it
4 = Good — suggest optimization or edge case to consider
5 = Interview-ready — confirm and suggest how to explain it clearly

IMPORTANT scoring rule: if the candidate identifies the correct approach/pattern (matching the reference), score at least 3 even if their explanation is brief. A correct but terse answer is better than a wrong but detailed one.

For suggestions, be SPECIFIC and ACTIONABLE:
- BAD: "Consider edge cases"
- GOOD: "What happens when `k` is larger than the layer perimeter? You need `k % perimeter` to avoid redundant full rotations."
- BAD: "Think about the approach more"
- GOOD: "Try this: extract each layer as a 1D array, rotate it by `k` positions using slicing `arr[-k:] + arr[:-k]`, then write it back."

Always give suggestions that move the candidate one concrete step closer to a working solution."""

    def _format_reference_answer(self, optimal: Solution | None, step: str, basic: Solution | None = None) -> str:
        if not optimal:
            return ""

        step_to_fields: dict[str, list[tuple[str, str]]] = {
            "observation": [
                ("Correct Observation", optimal.initial_observation),
                ("Correct Approach", optimal.approach_name),
            ],
            "approach": [
                ("Correct Approach", optimal.approach_name),
                ("Approach Reasoning", optimal.approach_reasoning),
                ("Step-by-Step", optimal.step_by_step),
            ],
            "code": [
                ("Reference Code", f"```\n{optimal.code}\n```"),
                ("Edge Cases", "\n".join(f"- {e.get('case', e)}" for e in (optimal.edge_cases or []))),
            ],
            "complexity": [
                ("Correct Time Complexity", optimal.time_complexity),
                ("Correct Space Complexity", optimal.space_complexity),
            ],
        }

        fields = step_to_fields.get(step, [
            ("Correct Approach", optimal.approach_name),
            ("Observation", optimal.initial_observation),
            ("Reasoning", optimal.approach_reasoning),
        ])

        parts = []
        for label, value in fields:
            if value:
                parts.append(f"**{label}:** {value}")

        if not parts:
            return ""
        result = "\n\n--- OPTIMAL SOLUTION (primary reference) ---\n" + "\n".join(parts) + "\n--- END OPTIMAL ---"

        if basic and basic.id != optimal.id:
            basic_fields = step_to_fields.get(step, [
                ("Approach", basic.approach_name),
                ("Reasoning", basic.approach_reasoning),
            ])
            basic_parts = []
            for label, value in basic_fields:
                if value:
                    basic_parts.append(f"**{label}:** {value}")
            if basic_parts:
                result += "\n\n--- BASIC SOLUTION (also acceptable) ---\n" + "\n".join(basic_parts) + "\n--- END BASIC ---"

        return result

    async def review_step(
        self,
        db: AsyncSession,
        question_title: str,
        question_description: str | None,
        step: str,
        user_content: str,
        optimal: Solution | None = None,
        basic: Solution | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> StepFeedback:
        step_labels = {
            "observation": "Initial Observation / Pattern Recognition",
            "approach": "Approach & Method Selection",
            "code": "Code Implementation",
            "complexity": "Time & Space Complexity Analysis",
        }
        step_label = step_labels.get(step, step)

        step_guidance = {
            "observation": "Focus on: did they identify the right pattern? What's the key insight they're missing? Give them the specific observation that unlocks the problem.",
            "approach": "Focus on: is the algorithm choice correct? If not, explain WHY the right one works. If yes but vague, give the specific state definition, data structure, or technique they should use.",
            "code": "Focus on: correctness, bugs, missing edge cases in the implementation. Point to specific lines or logic errors. Suggest the fix, don't just say it's wrong.",
            "complexity": "Focus on: is the analysis correct? If wrong, walk through the actual complexity step by step. Explain what operation dominates and why.",
        }

        reference = self._format_reference_answer(optimal, step, basic)

        user_msg = f"""Problem: {question_title}
{f"Description: {question_description}" if question_description else ""}
{reference}

The candidate's {step_label}:
\"\"\"
{user_content}
\"\"\"

{step_guidance.get(step, "")}

{"IMPORTANT: Compare the candidate's answer against BOTH reference solutions above. The candidate's approach is correct if it matches EITHER the optimal or basic solution. If it matches the basic but not the optimal, acknowledge correctness but explain the optimal approach as an improvement." if reference else ""}

Review this step. Acknowledge what's right, then give specific guidance to move forward. Score 1-5 and give actionable suggestions with concrete examples or code snippets where helpful."""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        result = await self.call_llm_structured(
            messages, StepFeedback, db, provider, model
        )
        result.step = step
        return result

    async def review_full(
        self,
        db: AsyncSession,
        question_title: str,
        question_description: str | None,
        observation: str | None,
        approach: str | None,
        code: str | None,
        time_complexity: str | None,
        space_complexity: str | None,
        optimal: Solution | None = None,
        basic: Solution | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> StepFeedback:
        parts = []
        if observation:
            parts.append(f"**Observation:** {observation}")
        if approach:
            parts.append(f"**Approach:** {approach}")
        if code:
            parts.append(f"**Code:**\n```\n{code}\n```")
        if time_complexity or space_complexity:
            parts.append(f"**Complexity:** Time {time_complexity or '?'}, Space {space_complexity or '?'}")

        ref_parts = []
        if optimal:
            ref_parts.append(f"**Approach:** {optimal.approach_name}")
            ref_parts.append(f"**Observation:** {optimal.initial_observation}")
            ref_parts.append(f"**Reasoning:** {optimal.approach_reasoning}")
            ref_parts.append(f"**Code:**\n```\n{optimal.code}\n```")
            ref_parts.append(f"**Complexity:** Time {optimal.time_complexity}, Space {optimal.space_complexity}")

        basic_parts = []
        if basic and (not optimal or basic.id != optimal.id):
            basic_parts.append(f"**Approach:** {basic.approach_name}")
            basic_parts.append(f"**Code:**\n```\n{basic.code}\n```")
            basic_parts.append(f"**Complexity:** Time {basic.time_complexity}, Space {basic.space_complexity}")

        reference_block = ""
        if ref_parts:
            reference_block = "\n\n--- OPTIMAL SOLUTION (primary reference) ---\n" + "\n".join(ref_parts) + "\n--- END OPTIMAL ---"
        if basic_parts:
            reference_block += "\n\n--- BASIC SOLUTION (also acceptable) ---\n" + "\n".join(basic_parts) + "\n--- END BASIC ---"

        user_msg = f"""Problem: {question_title}
{f"Description: {question_description}" if question_description else ""}
{reference_block}

The candidate's full solution attempt:
{chr(10).join(parts)}

{"IMPORTANT: Compare the candidate's answer against BOTH solutions above. The candidate is correct if they match EITHER the optimal or basic solution. If they match the basic, acknowledge correctness but explain the optimal approach as an improvement." if reference_block else ""}

Review the overall solution end-to-end. For each step that needs work, give the specific fix or next step. If the solution is mostly correct, focus on how to present it clearly in an interview. Score 1-5 and give actionable suggestions."""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        result = await self.call_llm_structured(
            messages, StepFeedback, db, provider, model
        )
        result.step = "full"
        return result
