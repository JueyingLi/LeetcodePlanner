from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent
from backend.models.question_links import QuestionSubtopic
from backend.models.question import Question
from backend.models.solution import Solution
from backend.models.subtopic import SubtopicKnowledge
from backend.schemas.question import PatternAnalysis
from backend.taxonomy import ALL_SUBTOPIC_NAMES


class PatternAnalysisAgent(BaseLLMAgent):
    """Generates a structured pattern breakdown + specific drill questions for one solution.

    The output is stored on Solution.pattern_analysis and drives both the Pattern Drill
    (open Q&A) and Quiz (multiple choice using wrong_options).
    """

    SYSTEM_PROMPT = """You are a senior Google engineer coaching a candidate for L5 coding interviews.
Your job: given a problem and its SOLUTION, produce a pattern analysis that GUIDES the candidate
through the thinking process: concrete observations -> needed state/operations -> technique choice
-> implementation decisions -> optimization.

The candidate can code but struggles to RECOGNIZE which technique to apply. Your drill questions
must walk them through the MIND MAP of solving this problem step by step. Do not jump from
"this is a DP/graph/heap problem" straight to the answer. First explain what details in the
problem make that technique natural.

Before writing the final JSON, think through this internal model:
1. What data is changing, being queried, or being compared?
2. What exact operation would be too slow if done naively?
3. What information must be remembered so we do not recompute work?
4. What is the minimal state identity? For DP, name the state dimensions. For graphs, name the
   node/state and edge meaning. For data structures, name the supported operations.
5. What invariant makes the code correct after each update/loop/recursive return?
6. Which line in the provided solution maintains each state or invariant?

DP SPECIAL RULE:
If the solution uses Dynamic Programming, never say only "overlapping subproblems" or "optimal
substructure". Identify the repeated decision and the exact subproblem state. For example, in a
stock problem with at most k transactions, the observation is not just "use DP"; it is:
- each day repeats the same decisions: buy, sell, hold, or skip,
- the future only depends on day index, whether we are holding stock, and how many transactions
  have been used or remain,
- caching best profit for (day, holding, transactions_left/used) prevents recomputing all future
  possibilities after the same state is reached through different histories.
Use this level of specificity for the actual problem.

You must produce:

1. **scenario**: 1-2 sentence description of what the problem is about. Concrete and brief.
   Do NOT reveal the solution approach. Just describe the task.

2. **example**: One input/output example with brief explanation. Each on its own line:
   Format:
   "Input: nums = [2,7,11,15], target = 9
   Output: [0,1]
   Explanation: nums[0] + nums[1] = 9"

3. **data_characteristics**: The INPUT PROPERTIES that determine the technique. Not a restatement.
   Identify what's structurally special, what repeats, and what must be stored. Include concrete
   cues such as:
   - constraints that rule out brute force,
   - monotonicity, ordering, or sortedness,
   - repeated decisions or reusable subproblems,
   - update/query operations,
   - graph state, edge weights, or traversal constraints,
   - interval overlap, prefix/range structure, or frequency counts.
   Good: "At each day the same buy/sell/skip choice recurs, and the remaining value depends only
   on day, holding state, and transactions left; this is a small reusable state space."
   Bad: "This is a DP problem."

4. **goal**: What to compute/return in one sentence.

5. **constraint_signals**: 2-4 strings pairing a concrete observation with its implication.
   Format: "<observation> -> <what it implies>"
   Each implication should point to a state, operation, invariant, or complexity need.
   Bad: "k transactions -> DP"
   Good: "At most k transactions and choices repeat every day -> track best profit by
   (day, holding, transactions_left) instead of exploring every buy/sell history"

6. **approaches**: Ordered list of techniques (data structures first, algorithms, optimizations).
   For each: label (canonical name like "Min-Heap", "BFS", "Sliding Window" — NOT vague verbs
   like "Sort by start"), category, why, code_steps (actual lines from the solution).
   Code step explanations must teach WHY the line exists, not just paraphrase it. Tie each key
   line back to an observation, state variable, transition, invariant, or edge case.
   For initialization lines such as `index = 0`, `stack = []`, `seen = set()`, `memo = {}`,
   `dp = [...]`, `heap = []`, or `lowlink = {}`, explain:
   - why the state starts empty/zero/self-mapped,
   - what data flows into it later,
   - why this container type fits the operations,
   - what invariant this state maintains.
   Bad explanation: "initializes the stack."
   Good explanation: "The stack starts empty because no DFS node is currently open; nodes are pushed when first visited and popped together when lowlink proves an SCC root."

7. **questions**: 4-6 GUIDED drill questions that follow the solving mind map IN ORDER.

   THE MIND MAP FLOW (questions MUST follow this progression):

   **Q1 - Observation** (approach_label: "observation"):
   Guide the candidate to notice the key data characteristics, limits, repeated decisions, and goal.
   DO NOT ask vaguely "what do you observe?" Ask something specific that leads them to the
   critical insight without naming the technique. Examples:
   - "The input has n ≤ 10^5 elements and requires range sum queries that update frequently.
     What does this size + operation combination tell you about acceptable per-query complexity?"
   - "Each interval has a start and end time, and intervals can overlap. What relationship between
     intervals creates the core difficulty here?"
   - "The graph edges all have non-negative weights. What algorithmic guarantee does this enable?"

   For DP-style solutions, Q1 should ask what repeated choice/state exists. Example:
   - "On each day you can buy, sell, or skip, but the future result only depends on a few facts
     about the current situation. Which facts must define the state so two histories can be treated
     as the same subproblem?"

   **Q2 - Technique selection** (approach_label: "approach"):
   From the observations, guide toward the right technique. Frame as "to handle [characteristic],
   what structure/approach achieves [efficiency need]?" DO NOT name the answer in the question.
   Examples:
   - "You need to repeatedly extract the smallest element while inserting new ones, both in
     better than O(n). What data structure supports this?"
   - "The same (day, holding, transactions_left) situation can be reached through different
     histories. What approach lets you solve each such state once and reuse it?"
   - "Elements arrive left-to-right and you need to find the nearest greater element to the left.
     What structure naturally maintains candidates in the order you need?"

   **Q3-Q4 - Specific decisions** (approach_label: "approach"):
   Ask about critical code choices. These assume the candidate now knows the technique.
   - "In this solution, why are intervals processed sorted by start time rather than end time?"
   - "What would break if dp[0] were initialized to 0 instead of nums[0]?"
   - "Why must the visited check happen before enqueuing rather than after dequeuing?"

   **Q5-Q6 - Improvement / edge cases** (approach_label: "optimization"):
   - "The current solution is O(n log n). If the input were guaranteed sorted, how would you
     reduce this?"
   - "What happens when all intervals are identical? Does the algorithm handle this correctly?"

   QUALITY RULES:
   - Every question must be self-contained enough to appear later as a standalone quiz item.
     Include the concrete problem context, input/output goal, or key scenario in the question.
     Bad: "Why is a Trie used in this solution instead of a hash map?"
     Good: "In the autocomplete system, each typed prefix must return matching historical
     sentences quickly. Why does this prefix-query requirement make a Trie a better fit than
     a hash map over full sentences?"
   - Do NOT ask vague failure questions where many mistakes would cause the same answer.
     Bad: "What would happen if the segment tree nodes were not initialized correctly?"
     Bad: "What goes wrong if the DP array is wrong?"
     Good: "In Range Module, each segment tree node stores whether its interval is fully covered.
     Why must an untouched node start as uncovered/False, and how would starting it as covered
     create false positives in queryRange(left, right)?"
     Good: "In stock-with-k-transactions DP, why does the state need both `holding` and
     `transactions_left`, and what incorrect histories get merged if one dimension is omitted?"
   - Q1-Q2 must NOT name the technique in the question — the candidate discovers it.
   - approach_label MUST be one of: "observation", "data structure", "algorithm", "approach",
     or "optimization". NEVER use specific technique names (e.g. NOT "Segment Tree", "BFS").
   - Answers should be 2-3 sentences that TEACH the reasoning.
   - Wrong options must be PLAUSIBLE (things a half-understanding candidate would choose).
   - Each wrong option is 1-2 sentences.

CRITICAL RULES:
- Base EVERYTHING on the actual solution code provided.
- Labels must be REAL canonical names (Min-Heap, BFS, Segment Tree, Trie, etc.).
- Code steps must be ACTUAL lines from the solution.
- Questions follow the mind-map: observe → select technique → specific decisions → optimize.
- In Q1/Q2, do not reveal the final technique name in the question. The answer can name it after
  explaining the reasoning.
- If a technique is chosen because of recurring subproblems, explicitly name the subproblems.
- If a data structure is chosen because of operations, explicitly name the operations and their
  required complexity.
- If SUBTOPIC KNOWLEDGE is provided, use it as teaching context for recognition cues, variants,
  invariants, and implementation ideas. The provided solution code is still the source of truth:
  adapt the subtopic knowledge to this exact problem instead of copying generic notes blindly.
- Write for Google L5 standard — specific, technical, no hand-waving."""

    @staticmethod
    def _trim(text: str | None, limit: int = 900) -> str:
        if not text:
            return ""
        normalized = " ".join(str(text).split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    async def _subtopic_context(self, db: AsyncSession | None, question: Question) -> str:
        if db is None:
            return ""

        rows = (await db.execute(
            select(SubtopicKnowledge)
            .join(QuestionSubtopic, QuestionSubtopic.subtopic_id == SubtopicKnowledge.id)
            .where(QuestionSubtopic.question_id == question.id)
            .order_by(SubtopicKnowledge.parent_id.is_not(None), SubtopicKnowledge.name)
            .limit(5)
        )).scalars().all()

        if not rows and question.subtopics:
            rows = (await db.execute(
                select(SubtopicKnowledge)
                .where(SubtopicKnowledge.name.in_(question.subtopics))
                .order_by(SubtopicKnowledge.parent_id.is_not(None), SubtopicKnowledge.name)
                .limit(5)
            )).scalars().all()

        if not rows:
            return ""

        blocks = []
        for st in rows:
            signals = ", ".join(str(s) for s in (st.signals or [])[:8])
            parts = [f"### {st.name}"]
            if st.mental_model:
                parts.append(f"Mental model: {self._trim(st.mental_model, 600)}")
            if st.when_to_use:
                parts.append(f"When to use: {self._trim(st.when_to_use, 700)}")
            if st.key_signals:
                parts.append(f"Recognition signals: {self._trim(st.key_signals, 700)}")
            elif signals:
                parts.append(f"Recognition signals: {signals}")
            if st.implementation_keys:
                parts.append(f"Implementation shape: {self._trim(st.implementation_keys, 900)}")
            if st.variants:
                parts.append(f"Variants to distinguish: {self._trim(st.variants, 600)}")
            if st.common_pitfalls:
                parts.append(f"Common pitfalls: {self._trim(st.common_pitfalls, 500)}")
            blocks.append("\n".join(parts))

        return "\n\n".join(blocks)

    def _user_msg(self, question: Question, solution: Solution, subtopic_context: str = "") -> str:
        topic_info = f"Topics: {', '.join(question.topics or []) or 'N/A'}"
        if question.subtopics:
            topic_info += f"; Subtopics: {', '.join(question.subtopics)}"

        examples_str = ""
        if question.examples:
            for ex in question.examples[:2]:
                if isinstance(ex, dict):
                    examples_str += f"\n  Input: {ex.get('input', '')} → Output: {ex.get('output', '')}"
                    if ex.get("explanation"):
                        examples_str += f" ({ex['explanation']})"

        canonical = ", ".join(sorted(ALL_SUBTOPIC_NAMES))

        return f"""Generate pattern analysis for this solution.

Problem: {question.title}
Number: {question.number or 'N/A'}
Difficulty: {question.difficulty.value if hasattr(question.difficulty, 'value') else question.difficulty}
{topic_info}
{f'Description: {question.description}' if question.description else ''}
{f'Examples:{examples_str}' if examples_str else ''}
{f'''
SUBTOPIC KNOWLEDGE CONTEXT:
Use this as supporting context for recognition cues, state/invariant explanations, variants,
and common pitfalls. Do not copy it blindly if the provided solution uses a different variant.
{subtopic_context}
''' if subtopic_context else ''}

Solution — {solution.approach_name}{' (optimal)' if solution.is_optimal else ''}:
Observation: {solution.initial_observation}
Reasoning: {solution.approach_reasoning}
Steps: {solution.step_by_step}
Time: {solution.time_complexity} / Space: {solution.space_complexity}
Code:
{solution.code}

CANONICAL PATTERN NAMES (use these for approach labels when they fit):
{canonical}

Generate the full pattern_analysis. Include scenario, example, data_characteristics, goal,
constraint_signals, approaches (with real code_steps from the solution), and 4-6 guided
drill questions following the mind-map flow (observation -> technique -> decisions -> optimization).
Make the observation and technique-selection parts specific enough that the candidate can see WHY
the solution follows naturally from the problem details."""

    async def generate(
        self,
        db: AsyncSession | None,
        question: Question,
        solution: Solution,
        provider: str | None = None,
        model: str | None = None,
        llm_config: dict | None = None,
    ) -> PatternAnalysis:
        subtopic_context = await self._subtopic_context(db, question)
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": self._user_msg(question, solution, subtopic_context)},
        ]
        if llm_config is not None:
            return await self.call_llm_structured_direct(messages, PatternAnalysis, llm_config)
        return await self.call_llm_structured(messages, PatternAnalysis, db, provider, model)
