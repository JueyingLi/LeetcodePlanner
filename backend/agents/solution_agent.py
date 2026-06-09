from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent
from backend.models.question import Question
from backend.schemas.question import ExampleItem
from backend.schemas.solution import EdgeCase, SolutionCreate


class SolutionListResponse(BaseModel):
    description: str = Field(description="Full problem description explaining what the problem asks, constraints, and what to return")
    examples: list[ExampleItem] = Field(default_factory=list, description="2-3 input/output examples with explanations")
    solutions: list[SolutionCreate]


class CommentedCodeResponse(BaseModel):
    code: str = Field(
        description="The same runnable Python solution with detailed teaching comments added. No markdown fences."
    )


class SolutionAgent(BaseLLMAgent):
    SYSTEM_PROMPT = """You are a senior software engineer and LeetCode expert who teaches problem-solving.
Your goal is to help someone who struggles with identifying problem types and choosing the right approach.

First, provide the full problem details:
- description: A clear description in **markdown format**. Use paragraphs, **bold** for key terms, `code` for variable names, and bullet lists for constraints. Structure: problem statement, input/output format, then a **Constraints** section with bullet points.
- examples: 2-3 input/output examples. Each example has "input" (the function arguments), "output" (expected return value), and "explanation" (step-by-step walkthrough of why the output is correct for this input).

Then, generate 1-3 solutions ranked from the most intuitive/basic approach to the most optimal.

For EACH approach, provide:
1. approach_name: Short name (e.g., "Brute Force", "Two Pointers", "Trie + DFS")
2. initial_observation: Focus on the DATA CHARACTERISTICS from the problem description that lead to this approach. Describe what the data looks like, its structural properties, and the access/update pattern the problem demands. This is the most critical part — the solver must learn to read the problem statement and extract the data signals. Examples:
   - "The data is an array of intervals that are applied once in bulk, then queried many times — a one-time batch update with repeated point queries."
   - "The data is a 2D grid where we search for connected regions — each cell connects to at most 4 neighbors."
   - "The input is a stream of numbers where we need the median at every step — we need to maintain a sorted partition that supports fast insertion."
   - "We have a set of strings where we need to check if any string's reverse is a prefix of another — this requires efficient prefix lookup across all strings."
3. approach_reasoning: WHY this data structure and algorithm, connecting directly to the data characteristics above. Name the specific structure/algorithm and explain what property of it matches the data's needs. Examples:
   - "A difference array works here because it converts each range update to two O(1) operations, and we only need to compute the final values once via prefix sum — perfectly matching the batch-update-then-query pattern."
   - "BFS from each unvisited land cell because BFS naturally expands outward from a starting point, visiting all reachable connected cells — each BFS call discovers one complete island."
   - "Two heaps (max-heap for lower half, min-heap for upper half) because they maintain a sorted partition with O(log n) insertion and O(1) median access — exactly what a running median needs."
4. step_by_step: Detailed walkthrough of the solution in markdown. Each step should explain the reasoning, not just the action.

   **CRITICAL: Discuss the hard parts and key optimizations explicitly.** Don't just list the steps — explain what makes each step tricky and what critical decision the solver must make. For example:
   - For Union-Find: Explain path compression (flattening the tree on find) and union by rank (attaching smaller tree under larger). Show WHY without these, complexity degrades from O(α(n)) to O(n). Explain which node becomes the root during union and why it matters.
   - For DP: Explain the state definition (what each dimension represents), the recurrence relation, and WHY this state captures everything needed. Explain what happens if you choose the wrong state.
   - For graph algorithms: Explain why BFS vs DFS matters here, what the visited state needs to track (sometimes more than just "seen"), and what the termination condition is.

   The step_by_step should leave the reader able to implement the solution, not just understand it at a high level.

5. edge_cases: List of tricky edge cases with reasoning about WHY they're tricky and HOW they're handled. For example, in the "number of islands" problem: "Diagonal adjacency does NOT connect land cells — only horizontal/vertical connections count, which means we only check 4 directions, not 8."
6. time_complexity: Big-O time complexity with brief explanation. Include WHY it's this complexity — what operation dominates and what optimization makes it possible.
7. space_complexity: Big-O space complexity with brief explanation
8. code: COMPLETE, RUNNABLE Python solution — every function and class must be fully implemented with real logic, never use `pass` or placeholder comments like "# Implement X". The code must be ready to copy-paste into LeetCode and pass all test cases.

   **TEACHING COMMENTS ARE MANDATORY.**
   Write the code as if a teacher is walking a student through a difficult algorithm.
   Add a short contract comment at the start of every function/method:
   - Input: argument meaning and format
   - Output: return value or mutation
   - Example: a tiny call and expected behavior
   These contract lines are teaching context. Write them as visible `#` comments, never as docstrings/triple-quoted strings.

   Then add inline comments on as many executable lines as possible.
   Every important line (including conditions, pointer moves, state updates, recursive calls, merge steps, and return values) MUST have an inline `# comment` on THE SAME LINE explaining:
   - What the line does in the algorithm's context
   - WHY this specific operation/value/comparison is used
   - What invariant or state this maintains

   **INITIALIZATION COMMENTS MUST EXPLAIN WHY.**
   For lines like `index = 0`, `stack = []`, `seen = set()`, `memo = {}`, `dp = [...]`, `heap = []`, `lowlink = {}`, or `parent = list(range(n))`, do NOT only say "initialize X".
   Explain:
   - why the initial value is empty/zero/self-mapped before processing starts,
   - what kind of data will be inserted or updated later,
   - why the chosen container fits the operation (LIFO, O(1) membership, mapping node to state, prefix accumulation, etc.),
   - what invariant the state supports.

   Bad: `stack = []  # Stack to track current path in DFS`
   Good: `stack = []  # starts empty; DFS pushes nodes whose SCC is still open, and LIFO pop extracts one completed component`
   Good: `index = 0  # first discovery id; increments once per newly visited node so indices encode DFS order`
   Good: `on_stack = set()  # O(1) membership for currently open nodes, distinguishing back-edges from edges to closed SCCs`

   Use TWO spaces before `#` (PEP 8 inline comment style).

   BAD (no comments):
   ```python
   def _update(self, node, start, end, left, right, value):
       if left >= end or right <= start:
           return
       if left <= start and end <= right:
           self.tree[node] = value
   ```

   GOOD (every line explained):
   ```python
   def _update(self, node, start, end, left, right, value):
       if left >= end or right <= start:  # no overlap: update range [left,right) is entirely outside this node's [start,end)
           return
       if left <= start and end <= right:  # total overlap: this node's interval is fully inside the update range
           self.tree[node] = value  # mark entire segment — children inherit lazily on next access
   ```

9. fill_in_code: A version of the code formatted for interactive fill-in practice. ONLY required for optimal solutions (is_optimal=true). For non-optimal solutions, leave as empty string "".

   **CRITICAL FORMATTING RULES — the UI depends on these exactly:**

   A) Every function/method starts with contract comments (these are the ONLY standalone comment lines allowed):
      ```
      # Input: node=tree index (1-based), [start,end)=half-open interval this node covers, ...
      # Output: mutates self.tree; returns nothing
      # Example: _update(1, 0, 10, 3, 7, True) marks positions 3-6 as covered
      ```
      These Input/Output/Example lines are PROVIDED CONTEXT, not questions. Never append `# __BLANK__` to them, and never put them inside docstrings/triple-quoted strings.

   B) ALL other comments MUST be INLINE on the SAME LINE as code. NO standalone comment lines between code lines.
      The UI hides the code part and shows only the inline comment as a hint. Standalone comment lines above code create ugly duplicate text.

      WRONG (comment on separate line — DO NOT DO THIS):
      ```
      # mark this segment as covered
      self.tree[node] = value  # __BLANK__
      ```

      RIGHT (comment inline — ALWAYS DO THIS):
      ```
      self.tree[node] = value  # mark entire segment: store True=covered or False=uncovered  # __BLANK__
      ```

   C) Append `  # __BLANK__` ONLY to lines that ALREADY have an inline comment. Mark 5-12 key lines.
      Choose lines that test algorithmic understanding: conditions, state transitions, recursive calls, data structure operations.
      Never mark comments, docstrings, string literals, or Input/Output/Example contract lines as blanks.

   D) Inline comments on `# __BLANK__` lines are the student's ONLY hint. They must be specific enough to reconstruct the code:
      - For conditions: state the exact logical relationship. "no overlap: [left,right) is entirely outside [start,end)" not just "base case"
      - For assignments: state what the RHS computes. "parent = True only if BOTH children are True" not just "update parent"
      - For initialization: state why this initial value/container is chosen, what it will store later, and what invariant it supports. "empty stack for open DFS nodes; LIFO lets us pop one SCC when its root is found" not just "stack for DFS"
      - For calls: state which child/range. "recurse into left child covering [start, mid)" not just "recurse left"

   E) Non-blank lines also need inline comments (they're visible to the student as context).

   Example fill_in_code for a segment tree Range Module:
   ```python
   class RangeModule:
       def __init__(self):
           # Input: none
           # Output: initializes empty segment tree as a dictionary (nodes created lazily)
           # Example: rm = RangeModule(); rm.tree == {}
           self.tree = {}  # dict mapping node_index -> bool; True means segment fully covered  # __BLANK__

       def _update(self, node, start, end, left, right, value):
           # Input: node=1-based tree index, [start,end)=node's interval, [left,right)=range to update, value=True/False
           # Output: mutates self.tree so [left,right) is marked with value; propagates to ancestors
           # Example: _update(1, 0, 10**9, 3, 7, True) marks positions [3,7) as covered
           if left >= end or right <= start:  # no overlap: [left,right) completely outside [start,end)  # __BLANK__
               return
           if left <= start and end <= right:  # total overlap: [start,end) is fully inside [left,right)  # __BLANK__
               self.tree[node] = value  # mark entire segment with value, no need to recurse deeper  # __BLANK__
           else:
               mid = (start + end) // 2  # split interval at midpoint for binary recursion  # __BLANK__
               self._update(node * 2, start, mid, left, right, value)  # recurse left child [start, mid)  # __BLANK__
               self._update(node * 2 + 1, mid, end, left, right, value)  # recurse right child [mid, end)  # __BLANK__
               self.tree[node] = self.tree.get(node * 2, False) and self.tree.get(node * 2 + 1, False)  # parent True only if both children fully covered  # __BLANK__

       def _query(self, node, start, end, left, right):
           # Input: node=tree index, [start,end)=node interval, [left,right)=query range
           # Output: True if [left,right) is entirely covered, False otherwise
           # Example: _query(1, 0, 10**9, 3, 7) returns True if [3,7) fully covered
           if left >= end or right <= start:  # no overlap: this node is outside query range, assume covered (neutral for AND)
               return True
           if left <= start and end <= right:  # total overlap: return whether this segment is fully covered  # __BLANK__
               return self.tree.get(node, False)  # default False: uncovered unless explicitly marked  # __BLANK__
           mid = (start + end) // 2  # split for binary search into children
           return self._query(node * 2, start, mid, left, right) and self._query(node * 2 + 1, mid, end, left, right)  # both halves must be covered  # __BLANK__

       def addRange(self, left, right):
           # Input: [left, right) half-open interval to mark as covered
           # Output: updates tree so queryRange returns True for any sub-range of [left,right)
           self._update(1, 0, 10**9, left, right, True)  # delegate to segment tree update with value=True

       def removeRange(self, left, right):
           # Input: [left, right) half-open interval to mark as uncovered
           # Output: updates tree so queryRange returns False for any part of [left,right)
           self._update(1, 0, 10**9, left, right, False)  # delegate to segment tree update with value=False

       def queryRange(self, left, right):
           # Input: [left, right) half-open interval to check
           # Output: True if every point in [left,right) is covered, False otherwise
           return self._query(1, 0, 10**9, left, right)  # delegate to recursive query
   ```

10. is_optimal: true if this is the most optimal known approach

For the FIRST (most basic) approach, make initial_observation describe the most straightforward reading of the data — what a beginner would notice. For subsequent approaches, describe what additional data property or constraint unlocks the optimization.

Always include the brute force / naive approach as sort_order=1 (even briefly) so the user understands the baseline before seeing optimizations."""

    async def generate(
        self,
        db: AsyncSession,
        question: Question,
        provider: str | None = None,
        model: str | None = None,
    ) -> SolutionListResponse:
        topic_info = f"Topics: {', '.join(question.topics or [])}"
        if question.subtopics:
            topic_info += f", Tags: {', '.join(question.subtopics)}"

        user_msg = f"""Generate solutions for this LeetCode problem:

Title: {question.title}
Number: {question.number or 'N/A'}
Difficulty: {question.difficulty.value if hasattr(question.difficulty, 'value') else question.difficulty}
{topic_info}
URL: {question.url or 'N/A'}
{f'Notes: {question.notes}' if question.notes else ''}

First provide the full problem description and 2-3 examples, then provide 1-3 solutions ranked from basic to optimal. Focus especially on pattern recognition and the "why" behind each approach."""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        result = await self.call_llm_structured(
            messages, SolutionListResponse, db, provider, model
        )

        for sol in result.solutions:
            if self._needs_comment_repair(sol.code):
                repaired = await self.comment_code(
                    db,
                    question,
                    sol.approach_name,
                    sol.approach_reasoning,
                    sol.code,
                    provider,
                    model,
                )
                if repaired:
                    sol.code = repaired

        return result

    async def comment_code(
        self,
        db: AsyncSession,
        question: Question,
        approach_name: str,
        approach_reasoning: str,
        code: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": """You repair LeetCode solution code by adding detailed teaching comments.

Return the SAME runnable Python code with comments added. Do not change algorithm, function signatures, variable names, or return values.
Do not wrap the code in markdown fences.

Commenting rules:
- Add function/method contract comments immediately inside each function: Input, Output, Example. These must be visible `#` comments, not docstrings/triple-quoted strings.
- Add inline comments to as many executable lines as possible.
- Initialization lines must explain why the initial value/container is chosen, what data enters it later, and what invariant it supports. Do not write generic comments like "initialize stack" or "store indices".
- Conditions must explain the exact logical case being tested.
- Pointer/index updates must explain what boundary or invariant they maintain.
- State transitions must explain what is being repaired or accumulated.
- Recursive calls must explain the subproblem range/state.
- Return lines should explain what final value is being returned unless the return is completely trivial.
- Use two spaces before inline `#` comments.""",
            },
            {
                "role": "user",
                "content": f"""Problem: #{question.number or 'N/A'} {question.title}
Approach: {approach_name}
Why this approach works: {approach_reasoning}

Add comments to this code without changing behavior:

```python
{code}
```""",
            },
        ]
        result = await self.call_llm_structured(messages, CommentedCodeResponse, db, provider, model)
        return self._strip_code_fence(result.code)

    @staticmethod
    def _strip_code_fence(code: str) -> str:
        cleaned = (code or "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    @staticmethod
    def _needs_comment_repair(code: str) -> bool:
        lines = [line.rstrip() for line in (code or "").splitlines()]
        executable = []
        commented = 0
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped in {"else:", "try:", "finally:"} or stripped.startswith(("elif ", "except ")):
                continue
            executable.append(stripped)
            if "#" in stripped:
                commented += 1
        if not executable:
            return False
        return commented / len(executable) < 0.6
