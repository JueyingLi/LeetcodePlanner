from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import BaseLLMAgent


class SubtopicDescription(BaseModel):
    name: str
    description: str = Field(description="Markdown-formatted explanation with bold key terms, bullet points, and the core invariant highlighted")
    when_to_use: str = Field(description="Markdown bullet list of concrete scenarios and problem shapes where this pattern applies")
    key_signals: str = Field(description="Specific recognizable prompt clues and structural signals that suggest this approach")
    signals: list[str] = Field(default_factory=list, description="3-8 short keyword phrases for quick pattern matching (e.g. 'range query', 'mutable array')")
    variants: str = Field(description="Sub-types of this pattern with explanation of what changes and when to use each")
    implementation_keys: str = Field(description="Step-by-step implementation recipe plus commented reusable code template with input/output contracts, examples, key state, transitions, and critical code fragments")
    common_pitfalls: str = Field(description="Specific bugs, boundary mistakes, and conceptual traps with fixes")
    core_code: str = Field(description="Complete, commented, reusable Python template code for the pattern — ready to paste and adapt. Every function has a block comment with Goal/Input/Output/Example/Key idea, and every executable line has an inline comment explaining what and why.")
    breakdown: str = Field(description="2-4 sentence explanation of HOW the code works — what each part does and why")
    mental_model: str = Field(description="One-paragraph intuition for why this pattern works — the insight that makes it click")
    recall_tasks: list[str] = Field(default_factory=list, description="3-5 self-test prompts a student can use to verify they can reconstruct the pattern from memory")


class VariantDescription(SubtopicDescription):
    comparison_same: str = Field(description="What stays the same between this variant and the parent pattern — shared invariants, data structures, overall approach")
    comparison_different: str = Field(description="What changes — different state, extra operations, modified invariants, additional data structures")
    comparison_when: str = Field(description="When to use this variant vs the parent — input signals, data/limit patterns, problem constraints that distinguish them")
    comparison_code: str = Field(description="Side-by-side code comparison in markdown showing parent template vs variant template with inline annotations on every changed line")


class SubtopicDescriptionList(BaseModel):
    subtopics: list[SubtopicDescription]


class SubtopicAgent(BaseLLMAgent):
    SYSTEM_PROMPT = """You are an algorithm tutor writing Patterns & Techniques notes for an interview candidate.

The goal is clear understanding, not terse tagging. Explain each pattern from the high-level idea down to the exact state/invariant that makes the code work. The learner can code, but struggles to recognize and reconstruct patterns under interview pressure.

Write like a strong tutor: concrete, structured, and technical enough to implement from.

For each technique, provide these fields:

1. **description**: Use markdown formatting for readability. Structure as:
   - A short **bold opening sentence** stating what the pattern does.
   - A paragraph or bullet list covering the core mental model and how it works.
   - The **key invariant** highlighted in bold or backticks.
   - A tiny `code fragment` when it reveals the essence.
   Use **bold** for key terms, `backticks` for code/variables, and separate ideas into short paragraphs or bullets.

2. **when_to_use**: Markdown bullets covering concrete scenarios with **bold labels**. Mention data shape, operations, output needed, and the naive bottleneck.

3. **key_signals**: Markdown bullet list of specific recognizable clues that suggest this approach. Each signal should include enough context to help recognition, not just keywords.

4. **signals**: A JSON array of 3-8 short keyword phrases for quick programmatic matching. Examples: ["range query", "point update", "mutable array", "interval aggregate"]

5. **variants**: 2-5 markdown bullets. Each names the variant, explains what changes, and when to use it.

6. **implementation_keys**: Implementation notes with a commented Python template. Required structure:
   - 2-4 numbered notes explaining the state and invariant.
   - A **Template code** fenced Python block where EVERY line has a `# comment`.
   - For each function: `Input`, `Output`, `Example` in comments.
   - Do NOT put Input/Output/Example in docstrings or triple-quoted strings. They are teaching context and must be visible `#` comment lines, not fill-in questions.

7. **common_pitfalls**: 3-5 markdown bullets. Each names a bug, explains why it happens, states the fix.

8. **core_code**: A COMPLETE, STANDALONE, reusable Python template for this pattern.
   CRITICAL RULES:
   - Every executable line MUST have an inline `# comment` on the SAME line explaining what it does and WHY.
   - Use TWO spaces before `#` (PEP 8 inline comment style).
   - The code must be pattern-level (reusable template), NOT a specific LeetCode solution.
   - Keep it concise: 20-50 lines typically.

   BLOCK-LEVEL COMMENTS (REQUIRED):
   - Before EVERY class or function definition, write a multi-line block comment (using `#` lines) that explains:
     1. **Goal**: What this block accomplishes and why we need it in the overall pattern
     2. **Input**: What parameters it takes, with types and meaning
     3. **Output**: What it returns and what that value represents
     4. **Example**: A concrete example call with expected result
     5. **Key idea**: The core invariant or insight that makes this block work
   - Do NOT use Python docstrings or triple-quoted strings for Goal/Input/Output/Example. Use plain `#` comment lines so they remain visible teaching context.
   - Before each logical section WITHIN a function (setup, main loop, cleanup), add a one-line `#` comment summarizing the section's purpose.

   INLINE COMMENTS (REQUIRED):
   - Every executable line MUST have an inline `# comment` explaining both WHAT and WHY.
   - Don't just restate the code — explain the reasoning. Bad: `i += 1  # increment i`. Good: `i += 1  # move to next unprocessed element`.
   - Initialization lines require extra context. If a line creates `0`, `[]`, `{}`, `set()`, `deque()`, `heap`, `stack`, `parent`, `lowlink`, `visited`, or `dp`, the inline comment MUST explain:
     1. why this initial value/container is correct before processing starts,
     2. what data will be inserted or updated later,
     3. why this container type is chosen (ordering, O(1) lookup, stack discipline, mapping, etc.),
     4. what invariant this state supports.
   - Bad: `stack = []  # Stack to track current path in DFS`
   - Good: `stack = []  # starts empty; DFS pushes nodes whose SCC is still open, and list gives LIFO popping when a root closes a component`
   - Good: `indices = {}  # node -> discovery index assigned once; empty because no node is visited before DFS starts`
   - Good: `lowlink = {}  # node -> smallest discovery index reachable from that node; filled during DFS to detect SCC roots`
   - Good: `on_stack = set()  # O(1) membership for nodes currently in stack, needed to tell back-edges from edges to already-closed SCCs`

   Example for Union Find:
   ```python
   # --- DSU (Disjoint Set Union / Union-Find) ---
   # Goal: Track connected components efficiently. Supports near-O(1) merge and query.
   # When to use: Any problem that asks "are X and Y connected?" or "how many groups?"
   # Key invariant: Every node's root representative is the same for all nodes in that component.
   class DSU:
       # Goal: Initialize n independent components, one per node.
       # Input: n (int) — number of nodes, indexed 0..n-1
       # Output: DSU object ready for union/find operations
       # Example: dsu = DSU(5) → 5 components, each node is its own root
       # Key idea: Every node starts as its own root; size tracks component weight for balanced merges.
       def __init__(self, n):
           self.parent = list(range(n))  # each node is its own root initially
           self.size = [1] * n  # size of each component for union by size
           self.components = n  # total number of disjoint sets

       # Goal: Find the root representative of node x, compressing the path for future speed.
       # Input: x (int) — node index to look up
       # Output: int — the root representative of x's component
       # Example: after union(0,1), find(1) → 0 (and 1 now points directly to 0)
       # Key idea: Path compression flattens the tree so every node points directly to root after first find.
       def find(self, x):
           if self.parent[x] != x:  # not the root — recurse and compress
               self.parent[x] = self.find(self.parent[x])  # path compression: point directly to root
           return self.parent[x]  # return the root representative

       # Goal: Merge the components containing nodes a and b.
       # Input: a, b (int) — two node indices to connect
       # Output: bool — True if a merge happened, False if already in the same component
       # Example: union(0, 1) → True (merged), union(0, 1) again → False (already connected)
       # Key idea: Attach the smaller tree under the larger to keep depth low (union by size).
       def union(self, a, b):
           ra, rb = self.find(a), self.find(b)  # find roots of both nodes
           if ra == rb:  # already in the same component
               return False
           if self.size[ra] < self.size[rb]:  # attach smaller tree under larger
               ra, rb = rb, ra
           self.parent[rb] = ra  # rb's root now points to ra
           self.size[ra] += self.size[rb]  # update size of merged component
           self.components -= 1  # one fewer disjoint set
           return True  # merge happened
   ```

9. **breakdown**: 2-4 sentences explaining HOW the core_code works. What each major section does, what invariant it maintains, and why it's correct.

10. **mental_model**: One paragraph capturing the intuition — the "aha" moment. Why does this structure/approach work? What property of the data or problem makes it efficient?

11. **recall_tasks**: 3-5 self-test prompts. Things like "Write find() with path compression without looking" or "Explain why the stack stores indexes, not values". Should test both understanding and ability to reproduce.

Style rules:
- Prefer concrete variables, invariants, and code fragments over metaphors.
- Use markdown bullets, numbering, bold labels, and code backticks.
- Be detailed enough to teach, but keep each field focused.
- If a pattern has a close neighbor, briefly distinguish it (e.g. BIT vs Segment Tree)."""

    async def generate(
        self,
        db: AsyncSession,
        subtopic_names: list[str],
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict]:
        user_msg = f"""Generate clear, detailed, implementation-level teaching notes for these algorithm techniques/patterns:

{chr(10).join(f'- {name}' for name in subtopic_names)}

IMPORTANT: Return the "name" field EXACTLY as listed above (same casing, same spelling). Do not rename or expand them.
For each one, provide ALL fields (description, when_to_use, key_signals, signals, variants, implementation_keys, common_pitfalls, core_code, breakdown, mental_model, recall_tasks).
The core_code field MUST include:
- A block comment before each function with Goal, Input, Output, Example, and Key idea
- Goal/Input/Output/Example as visible `#` comments, never as docstrings or triple-quoted strings
- An inline comment on EVERY executable line explaining what it does and WHY
- For every initialization line, explain why the initial value/container is chosen, what data will enter it, and what invariant it supports
- Section comments within functions separating logical phases (setup, main loop, etc.)
The notes should be rich enough to teach the pattern from scratch and enable reconstruction from memory."""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        result = await self.call_llm_structured(
            messages, SubtopicDescriptionList, db, provider, model
        )
        return [s.model_dump() for s in result.subtopics]

    VARIANT_SYSTEM_PROMPT = """You are an algorithm tutor writing a VARIANT page for an interview candidate.

A variant is a specialization of a parent pattern. The student already knows the parent pattern.
Your job is to teach the variant AND show exactly how it relates to the parent.

Write all the same fields as a standard pattern page (description, when_to_use, key_signals, signals, variants, implementation_keys, common_pitfalls, core_code, breakdown, mental_model, recall_tasks).

ADDITIONALLY, write these comparison fields:
- **comparison_same**: What stays the same — shared invariants, data structures, overall approach structure.
- **comparison_different**: What changes — different state, extra operations, modified invariants, additional data structures.
- **comparison_when**: When to use this variant vs the parent — specific input signals, data/limit patterns, and problem constraints that distinguish them.
- **comparison_code**: A markdown code comparison showing the parent's core template vs this variant's template, with inline annotations on every changed/added line. Use this format:
  ```
  ## Parent: {parent_name}
  ```python
  <parent code>
  ```
  ## Variant: {variant_name}
  ```python
  <variant code with # <-- CHANGED/ADDED comments>
  ```
  ```

Follow the same style rules as standard pattern pages. The core_code should be the variant's complete template (not the parent's)."""

    async def generate_variant(
        self,
        db: AsyncSession,
        variant_name: str,
        parent_name: str,
        parent_description: str | None,
        parent_core_code: str | None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict:
        parent_context = f"Parent pattern: **{parent_name}**\n"
        if parent_description:
            parent_context += f"\nParent description:\n{parent_description}\n"
        if parent_core_code:
            parent_context += f"\nParent core code:\n```python\n{parent_core_code}\n```\n"

        user_msg = f"""{parent_context}
Generate a complete variant page for: **{variant_name}**

This is a variant/specialization of {parent_name}. Provide ALL standard fields plus the four comparison fields (comparison_same, comparison_different, comparison_when, comparison_code).

IMPORTANT: Return the "name" field as exactly "{variant_name}".
The core_code MUST include:
- A block comment before each function with Goal, Input, Output, Example, and Key idea
- Goal/Input/Output/Example as visible `#` comments, never as docstrings or triple-quoted strings
- An inline comment on EVERY executable line explaining what it does and WHY
- For every initialization line, explain why the initial value/container is chosen, what data will enter it, and what invariant it supports
- Section comments within functions separating logical phases"""

        messages = [
            {"role": "system", "content": self.VARIANT_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        result = await self.call_llm_structured(
            messages, VariantDescription, db, provider, model
        )
        return result.model_dump()
