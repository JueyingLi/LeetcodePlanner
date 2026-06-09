from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent
from backend.models.question import Question
from backend.models.quiz import QuizFocus, QuizType
from backend.models.solution import Solution


class QuizItem(BaseModel):
    quiz_type: str
    prompt: str
    options: list[str] | None = None
    correct_answer: str
    explanation: str = ""


class QuizListResponse(BaseModel):
    quizzes: list[QuizItem]


ALLOWED_TYPES = {
    QuizFocus.INPUT_OUTPUT: ["multiple_choice"],
    QuizFocus.PATTERN_RECOGNITION: ["multiple_choice"],
    QuizFocus.APPROACH_REASONING: ["multiple_choice"],
    QuizFocus.CODE_IMPLEMENTATION: ["code_choice"],
    QuizFocus.EDGE_CASES: ["multiple_choice"],
    QuizFocus.COMPLEXITY: ["multiple_choice"],
    QuizFocus.FULL_FLOW: ["multiple_choice", "code_choice"],
}


class QuizAgent(BaseLLMAgent):
    FOCUS_PROMPTS = {
        QuizFocus.INPUT_OUTPUT: """Generate ONLY multiple_choice questions (quiz_type: "multiple_choice") about understanding the problem deeply:
- "Given input X, what should the output be and why?"
- What does a specific edge-case input produce?
- What happens when the input is empty, has one element, has duplicates, or hits constraint boundaries?
- What exactly does "connected" or "adjacent" or "distinct" mean in this context?
- Trace through the algorithm with a specific small example

DO NOT generate code_choice questions for this focus. All questions must be multiple_choice with text answers.""",

        QuizFocus.PATTERN_RECOGNITION: """Generate ONLY multiple_choice questions (quiz_type: "multiple_choice") that test SPECIFIC pattern recognition at implementation depth.
DO NOT ask generic questions like "what category is this?" — the user already knows it's DP or Graph.
Instead test:
- "What SPECIFIC sub-type applies?" (e.g., not "DP" but "interval DP vs state machine DP vs bitmask DP — which one and why?")
- "What is the KEY observation that distinguishes this from similar problems?"
- "Problem X looks similar to this — what's the critical difference in approach?"
- "What data structure or state representation is needed and why?"
- "If you see [specific constraint/pattern], why does that signal [specific technique]?"
Questions should require understanding WHY a technique fits, not just naming it.

DO NOT generate code_choice questions for this focus.""",

        QuizFocus.APPROACH_REASONING: """Generate ONLY multiple_choice questions (quiz_type: "multiple_choice") about detailed design and thought process:
- "What should the DP state represent? What are the dimensions?"
- "Why does greedy fail here? Give a counterexample scenario."
- "What is the recurrence relation / transition?"
- "Why BFS instead of DFS (or vice versa)? What property makes the difference?"
- "In the Union Find approach, what optimization is critical and what happens without it?"
- "What is the correct initialization and base case?"
- "How do you handle the boundary between two subproblems?"

These are CONCEPTUAL questions about approach design — NOT code. DO NOT generate code_choice questions for this focus.""",

        QuizFocus.CODE_IMPLEMENTATION: """Generate ONLY code_choice questions (quiz_type: "code_choice") about actual code implementation.

CONTEXT IN THE PROMPT (mandatory):
The prompt MUST include 2-3 sentences explaining:
1. What this function/block does in plain English and WHY it's needed in the solution
2. What data structures it operates on (e.g., "freq_to_list is an OrderedDict mapping frequency → {key: node}")
3. What the KEY DECISION is (e.g., "The critical part is how min_freq is updated when a frequency bucket empties")

BAD prompt: "Which `_update()` implementation is correct?" — user has no idea what _update does
GOOD prompt: "In the LFU Cache, `_update()` moves a key to the next frequency bucket. It uses `freq_to_list` (frequency → OrderedDict of nodes) and must update `min_freq` when a bucket empties. Which implementation correctly updates min_freq?"

CODE OPTIONS:
- Focus on ONE SMALL critical function or section (3-8 lines) — NOT the entire solution
- Each option must ONLY contain the lines that DIFFER, plus 1-2 lines of surrounding context for readability
- Mark the differing line(s) with a comment like `# <-- key line` so the user can spot the difference
- BAD: 4 identical 10-line blocks with one subtle difference buried in line 7
- GOOD: 4 short 3-5 line blocks centered on the critical decision, each clearly different
- Wrong options should have ONE realistic bug: wrong operator, off-by-one, missing step, wrong direction

DO NOT generate multiple_choice questions for this focus. All questions must be code_choice.""",

        QuizFocus.EDGE_CASES: """Generate ONLY multiple_choice questions (quiz_type: "multiple_choice") about tricky edge cases:
- "What happens when [specific tricky input]? Which step of your algorithm breaks?"
- "This off-by-one scenario causes what bug in the sliding window?"
- "Why does the empty/single-element case need special handling?"
- "What integer overflow or boundary condition could crash the solution?"
- "Which of these test cases would distinguish a correct solution from a common wrong approach?"
Make these specific to the actual problem, not generic edge case types.

DO NOT generate code_choice questions for this focus.""",

        QuizFocus.COMPLEXITY: """Generate ONLY multiple_choice questions (quiz_type: "multiple_choice") that test DEEP understanding of complexity:
- "Why is it O(n log n) and not O(n²)? What specific operation causes the log factor?"
- "What is the space complexity and what dominates it — the recursion stack, the DP table, or the auxiliary data structure?"
- "If we changed constraint X, how would the complexity change?"
- "Can this be done in better than O(n²)? What technique enables it?"
- "What is the amortized complexity of this operation and why?"
Require the user to EXPLAIN the complexity, not just pick a Big-O notation.

DO NOT generate code_choice questions for this focus.""",

        QuizFocus.FULL_FLOW: """Generate a progression of increasingly difficult questions covering the full solving flow:

1. One multiple_choice on the key insight / pattern recognition (specific, not generic)
2. One multiple_choice on the state definition or approach setup
3. One code_choice focusing on ONE critical function (3-8 lines) — the `find()`, the transition, the merge step, etc.
4. One multiple_choice on an edge case that breaks naive approaches
5. One multiple_choice on complexity analysis

For code_choice:
- The prompt MUST explain what the function does and what data structures it uses (2-3 sentences of context)
- Focus on a SINGLE small function or code block (3-5 lines max per option), centered on the differing logic
- Mark the key line with `# <-- key line` so the user can spot the difference
- Good: "In Union-Find, `union(x, y)` attaches the smaller-rank tree under the larger to keep height low. Which correctly updates rank?"
- BAD: "Which `union()` is correct?" with no context and 10 identical lines
- Wrong options should have ONE subtle bug each (missing path compression, wrong comparison, etc.)

Each question should be HARD enough that someone who only vaguely remembers the solution would get it wrong.""",
    }

    async def generate(
        self,
        db: AsyncSession | None,
        question: Question,
        solutions: list[Solution],
        count: int = 5,
        focus: QuizFocus = QuizFocus.FULL_FLOW,
        provider: str | None = None,
        model: str | None = None,
        llm_config: dict | None = None,
        wrong_answers: list[dict] | None = None,
    ) -> list[dict]:
        solution_text = ""
        for sol in solutions:
            solution_text += f"""
--- Approach: {sol.approach_name} ---
Observation: {sol.initial_observation}
Reasoning: {sol.approach_reasoning}
Steps: {sol.step_by_step}
Edge cases: {sol.edge_cases}
Time: {sol.time_complexity}, Space: {sol.space_complexity}
Code:
{sol.code}
"""

        prior_steps_summary = None
        if focus in (QuizFocus.COMPLEXITY, QuizFocus.EDGE_CASES):
            prior_steps_summary = self._build_prior_summary(solutions, focus)

        focus_instruction = self.FOCUS_PROMPTS.get(focus, self.FOCUS_PROMPTS[QuizFocus.FULL_FLOW])

        # For pattern recognition, anchor the quiz on the solution's pattern_analysis
        # drill questions so the test mirrors what the learner studied.
        pattern_block = ""
        if focus == QuizFocus.PATTERN_RECOGNITION:
            pa = None
            for sol in solutions:
                if sol.pattern_analysis:
                    pa = sol.pattern_analysis
                    break
            if pa:
                lines = []
                if pa.get("data_characteristics"):
                    lines.append(f"Data: {pa['data_characteristics']}")
                if pa.get("goal"):
                    lines.append(f"Goal: {pa['goal']}")
                for sig in (pa.get("constraint_signals") or []):
                    lines.append(f"- Signal: {sig}")
                for app in (pa.get("approaches") or []):
                    lines.append(f"- [{app.get('category')}] {app.get('label')}: {app.get('why')}")
                drill_qs = pa.get("questions") or []
                if drill_qs:
                    lines.append("\nEXISTING DRILL QUESTIONS (use these as basis — create multiple_choice "
                                 "versions using the answer as correct and wrong_options as distractors):")
                    for dq in drill_qs[:4]:
                        lines.append(f"  Q: {dq.get('question')}")
                        lines.append(f"  A: {dq.get('answer')}")
                        wrongs = dq.get("wrong_options") or []
                        if wrongs:
                            lines.append(f"  Wrong: {' | '.join(wrongs)}")
                pattern_block = "\n\nPATTERN ANALYSIS:\n" + "\n".join(lines)

        # Re-test concepts the user previously got wrong on this question.
        wrong_block = ""
        if wrong_answers:
            wl = []
            for w in wrong_answers[:5]:
                wl.append(
                    f"- Prompt: {w.get('prompt')}\n  Their wrong answer: {w.get('user_answer')}\n"
                    f"  Correct: {w.get('correct_answer')}"
                )
            wrong_block = (
                "\n\nPREVIOUSLY MISSED (include at least one question that re-tests the SAME concept the "
                "learner got wrong, using their wrong answer as a tempting distractor):\n" + "\n".join(wl)
            )

        allowed = ALLOWED_TYPES.get(focus, ["multiple_choice"])
        quoted = [f'"{t}"' for t in allowed]
        type_rule = f"quiz_type must be one of: {', '.join(quoted)}"

        system_prompt = f"""You are creating CHALLENGING quiz questions for someone preparing for Google Hard interviews.
These are NOT beginner questions. The user already knows basic algorithm categories.
Your questions should test whether they can actually SOLVE and IMPLEMENT the problem, not just categorize it.

{focus_instruction}

Rules:
- Generate exactly {count} quiz questions
- {type_rule}
- All 4 options must be PLAUSIBLE — no obviously wrong throwaway options
- Wrong options should represent common misconceptions or mistakes
- correct_answer must exactly match one option
- explanation: explain WHY the correct answer is right AND why the most tempting wrong answer is wrong
- For code_choice:
  - The prompt MUST start with 2-3 sentences of context: what the function does, what data structures it uses, and what the key decision is. Never ask "Which X is correct?" without explaining what X does.
  - Options must be SHORT (3-5 lines). Only show the lines that differ plus 1-2 lines of context. Do NOT repeat 10 identical lines across all 4 options.
  - Mark the critical differing line with a trailing comment `# <--` so the reader can immediately see what changed.
  - Wrong options: ONE subtle, realistic bug each (wrong operator, off-by-one, missing step, wrong direction).
- Make distractors that someone who half-understands would pick"""

        user_msg = f"""Problem: {question.title} (#{question.number or 'N/A'})
Difficulty: {question.difficulty.value if hasattr(question.difficulty, 'value') else question.difficulty}
Topics: {', '.join(question.topics or [])}
Subtopics: {', '.join(question.subtopics) if question.subtopics else 'N/A'}

Solutions:
{solution_text}{pattern_block}{wrong_block}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        if llm_config:
            result = await self.call_llm_structured_direct(
                messages, QuizListResponse, llm_config
            )
        else:
            result = await self.call_llm_structured(
                messages, QuizListResponse, db, provider, model
            )

        quiz_data_list = []
        for quiz in result.quizzes:
            qt = QuizType.MULTIPLE_CHOICE
            if quiz.quiz_type == "code_choice" and "code_choice" in allowed:
                qt = QuizType.CODE_COMPLETION

            data = {
                "quiz_type": qt,
                "quiz_focus": focus,
                "question_id": question.id,
                "question_title": question.title,
                "prompt": quiz.prompt,
                "options": quiz.options,
                "correct_answer": quiz.correct_answer,
                "explanation": quiz.explanation,
                "prior_steps_summary": prior_steps_summary,
            }
            quiz_data_list.append(data)

        return quiz_data_list

    def _build_prior_summary(self, solutions: list[Solution], focus: QuizFocus) -> str:
        if not solutions:
            return ""
        best = solutions[-1]
        parts = [f"**Problem type:** {best.approach_name}"]
        if focus == QuizFocus.COMPLEXITY:
            parts.append(f"**Key observation:** {best.initial_observation}")
            parts.append(f"**Approach:** {best.approach_reasoning}")
            parts.append(f"**Edge cases:** {len(best.edge_cases)} identified")
        elif focus == QuizFocus.EDGE_CASES:
            parts.append(f"**Key observation:** {best.initial_observation}")
            parts.append(f"**Approach:** {best.approach_reasoning}")
        return "\n".join(parts)
