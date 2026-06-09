from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.subtopic import SubtopicKnowledge
from backend.models.study_plan import StudyPlan, StudyPlanItem, StudyPlanSession, SubtopicReview


SEED_TEMPLATES = [
    {
        "slug": "segment-tree",
        "name": "Segment Tree",
        "category": "Range Query",
        "when_to_use": "Use when values change and you still need fast range answers such as sum, min, max, count, or coverage over intervals.",
        "signals": ["range query", "point update", "mutable array", "interval aggregate", "many queries"],
        "core_code": """class SegmentTree:
    def __init__(self, nums):
        self.n = len(nums)
        self.tree = [0] * (2 * self.n)
        for i, x in enumerate(nums):
            self.tree[self.n + i] = x
        for i in range(self.n - 1, 0, -1):
            self.tree[i] = self.tree[2 * i] + self.tree[2 * i + 1]

    def update(self, index, value):
        i = index + self.n
        self.tree[i] = value
        i //= 2
        while i:
            self.tree[i] = self.tree[2 * i] + self.tree[2 * i + 1]
            i //= 2

    def query(self, left, right):
        # inclusive [left, right]
        left += self.n
        right += self.n
        ans = 0
        while left <= right:
            if left % 2 == 1:
                ans += self.tree[left]
                left += 1
            if right % 2 == 0:
                ans += self.tree[right]
                right -= 1
            left //= 2
            right //= 2
        return ans""",
        "breakdown": "Leaves live at indexes `n..2n-1`. Each parent is the combined answer of its two children. `update` changes one leaf and repairs ancestors. `query` consumes only complete stored intervals that fit inside the requested range.",
        "mental_model": "A segment tree stores precomputed answers for many intervals. Every node represents an interval, and its value is the answer for that interval. A query stitches together a few stored intervals instead of scanning the whole range.",
        "recall_tasks": [
            "Write the `query(left, right)` loop without looking.",
            "Explain why odd `left` and even `right` are consumed before moving upward.",
            "Change the template from range sum to range minimum.",
        ],
    },
    {
        "slug": "iterator-generator",
        "name": "Iterator / Generator",
        "category": "Advanced Data Structures",
        "when_to_use": "Use when the problem asks for lazy traversal, flattening, peeking, streaming, or next/hasNext style APIs.",
        "signals": ["iterator", "generator", "yield", "next", "hasNext", "stream", "flatten", "lazy"],
        "core_code": """def flatten(root):
    for item in root:
        if isinstance(item, list):
            yield from flatten(item)
        else:
            yield item


class PeekingIterator:
    def __init__(self, iterator):
        self.iterator = iterator
        self.cache = None
        self.has_cache = False

    def peek(self):
        if not self.has_cache:
            self.cache = self.iterator.next()
            self.has_cache = True
        return self.cache

    def next(self):
        if self.has_cache:
            self.has_cache = False
            return self.cache
        return self.iterator.next()

    def hasNext(self):
        return self.has_cache or self.iterator.hasNext()""",
        "breakdown": "`yield` pauses state and resumes later. `yield from` delegates nested traversal. Peeking iterators keep a one-element cache so `peek` does not consume the underlying stream.",
        "mental_model": "The iterator object is a state machine. Every call advances exactly one step unless the method is explicitly a peek/cache operation.",
        "recall_tasks": [
            "Explain why `peek()` needs `has_cache`.",
            "Convert recursive flattening to a stack-based iterator.",
            "List which methods consume the stream and which do not.",
        ],
    },
    {
        "slug": "union-find",
        "name": "Union Find",
        "category": "Graph",
        "when_to_use": "Use for dynamic connectivity, grouping, cycle detection in undirected graphs, and counting connected components.",
        "signals": ["connected", "component", "union", "find", "merge", "cycle", "groups", "islands"],
        "core_code": """class DSU:
    def __init__(self, n):
        self.parent = list(range(n))
        self.size = [1] * n
        self.components = n

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        self.components -= 1
        return True""",
        "breakdown": "`find` returns the representative root and compresses paths. `union` merges two roots, keeps the larger tree as parent, and returns whether a merge actually happened.",
        "mental_model": "Every set is represented by one root. Path compression turns future lookups into almost O(1). A failed union means both nodes were already connected.",
        "recall_tasks": [
            "Write `find` with path compression.",
            "Explain why `union` returns False on an existing connection.",
            "Convert a grid coordinate into a DSU id.",
        ],
    },
    {
        "slug": "binary-indexed-tree",
        "name": "Fenwick Tree",
        "category": "Range Query",
        "when_to_use": "Use for prefix sums with point updates, especially when implementation speed matters more than segment-tree flexibility.",
        "signals": ["prefix sum", "point update", "range sum", "inversion count", "frequency table"],
        "core_code": """class BIT:
    def __init__(self, n):
        self.n = n
        self.bit = [0] * (n + 1)

    def add(self, index, delta):
        i = index + 1
        while i <= self.n:
            self.bit[i] += delta
            i += i & -i

    def prefix_sum(self, index):
        i = index + 1
        ans = 0
        while i > 0:
            ans += self.bit[i]
            i -= i & -i
        return ans

    def range_sum(self, left, right):
        return self.prefix_sum(right) - (self.prefix_sum(left - 1) if left else 0)""",
        "breakdown": "`i & -i` isolates the range size represented by a BIT node. Updates walk upward; prefix queries walk downward.",
        "mental_model": "Each index stores a power-of-two suffix contribution. Prefix sums collect those contributions from right to left.",
        "recall_tasks": ["Write `add` and `prefix_sum`.", "Explain `i & -i`.", "Use BIT for inversion counting."],
    },
    {
        "slug": "trie",
        "name": "Trie",
        "category": "String",
        "when_to_use": "Use when many words share prefixes or the problem repeatedly asks prefix/dictionary lookup.",
        "signals": ["prefix", "dictionary", "word search", "autocomplete", "startsWith"],
        "core_code": """class TrieNode:
    def __init__(self):
        self.children = {}
        self.word = None


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        node = self.root
        for ch in word:
            node = node.children.setdefault(ch, TrieNode())
        node.word = word

    def search(self, word):
        node = self.root
        for ch in word:
            if ch not in node.children:
                return False
            node = node.children[ch]
        return node.word is not None""",
        "breakdown": "Each edge is one character. Terminal state must be stored separately because a word can be a prefix of another word.",
        "mental_model": "A trie prunes impossible prefixes early. It trades memory for fast prefix traversal.",
        "recall_tasks": ["Implement insert/search.", "Explain terminal marker.", "Use trie to prune DFS."],
    },
    {
        "slug": "monotonic-stack",
        "name": "Monotonic Stack",
        "category": "Stack",
        "when_to_use": "Use to find next/previous greater/smaller elements or maintain candidates that dominate earlier values.",
        "signals": ["next greater", "previous smaller", "daily temperatures", "histogram", "span"],
        "core_code": """def next_greater(nums):
    ans = [-1] * len(nums)
    stack = []  # indexes with decreasing values
    for i, x in enumerate(nums):
        while stack and nums[stack[-1]] < x:
            ans[stack.pop()] = x
        stack.append(i)
    return ans""",
        "breakdown": "The stack stores unresolved indexes. When the current value beats the top, it resolves that top's answer.",
        "mental_model": "Keep only candidates that have not yet found a better element. Pop exactly once, so total work is O(n).",
        "recall_tasks": ["Choose stack direction for next smaller.", "Explain O(n) despite while loop.", "Adapt for daily temperatures."],
    },
    {
        "slug": "bfs",
        "name": "BFS Queue",
        "category": "Graph",
        "when_to_use": "Use for shortest path in unweighted graphs/grids or level-order expansion.",
        "signals": ["shortest path", "minimum steps", "level order", "nearest", "grid"],
        "core_code": """from collections import deque


def bfs(start):
    q = deque([(start, 0)])
    seen = {start}
    while q:
        node, dist = q.popleft()
        for nei in neighbors(node):
            if nei in seen:
                continue
            seen.add(nei)
            q.append((nei, dist + 1))""",
        "breakdown": "Queue processes states by increasing distance. Mark visited before enqueueing to avoid duplicates.",
        "mental_model": "The first time BFS reaches a state in an unweighted graph, it has the shortest distance.",
        "recall_tasks": ["Write level-size loop.", "Explain multi-source BFS.", "Define grid neighbors safely."],
    },
    {
        "slug": "dijkstra",
        "name": "Dijkstra",
        "category": "Graph",
        "when_to_use": "Use for shortest path with non-negative weighted edges.",
        "signals": ["weighted graph", "minimum cost", "shortest distance", "network delay"],
        "core_code": """import heapq


def dijkstra(graph, source):
    dist = {source: 0}
    heap = [(0, source)]
    while heap:
        d, node = heapq.heappop(heap)
        if d != dist[node]:
            continue
        for nei, w in graph[node]:
            nd = d + w
            if nd < dist.get(nei, float("inf")):
                dist[nei] = nd
                heapq.heappush(heap, (nd, nei))
    return dist""",
        "breakdown": "The heap always expands the current cheapest known state. Stale heap entries are skipped.",
        "mental_model": "With non-negative weights, once a node is popped with its best distance, no later path can improve it.",
        "recall_tasks": ["Explain stale heap entries.", "Choose BFS vs Dijkstra.", "Add path reconstruction."],
    },
    {
        "slug": "topological-sort",
        "name": "Topological Sort",
        "category": "Graph",
        "when_to_use": "Use when dependencies form a directed graph and you need ordering or cycle detection.",
        "signals": ["prerequisite", "dependency", "course schedule", "build order", "DAG"],
        "core_code": """from collections import deque


def topo_sort(n, edges):
    graph = [[] for _ in range(n)]
    indeg = [0] * n
    for a, b in edges:
        graph[a].append(b)
        indeg[b] += 1
    q = deque(i for i in range(n) if indeg[i] == 0)
    order = []
    while q:
        node = q.popleft()
        order.append(node)
        for nei in graph[node]:
            indeg[nei] -= 1
            if indeg[nei] == 0:
                q.append(nei)
    return order if len(order) == n else []""",
        "breakdown": "Indegree counts unmet prerequisites. Removing zero-indegree nodes simulates satisfying dependencies.",
        "mental_model": "A DAG always has at least one zero-indegree node. If none remain before all nodes are processed, there is a cycle.",
        "recall_tasks": ["Define edge direction for Course Schedule.", "Detect cycle using output length.", "Implement DFS colors."],
    },
    {
        "slug": "binary-search-on-answer",
        "name": "Search on Answer",
        "category": "Binary Search",
        "when_to_use": "Use when the answer is numeric and feasibility is monotonic.",
        "signals": ["minimize maximum", "maximize minimum", "capacity", "speed", "minimum days", "feasible"],
        "core_code": """def binary_search_answer(lo, hi):
    # smallest x such that can(x) is True
    while lo < hi:
        mid = (lo + hi) // 2
        if can(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo""",
        "breakdown": "`can(mid)` must be monotonic. For minimize-maximum, feasible means try smaller. For maximize-minimum, flip the direction.",
        "mental_model": "You are not searching the input; you are searching possible answers and using a checker to discard half.",
        "recall_tasks": ["State the monotonic predicate.", "Choose lo/hi bounds.", "Flip template for maximum feasible."],
    },
]


def _normalize_name(name: str) -> str:
    return name.strip().lower()


async def ensure_seed_templates(db: AsyncSession) -> None:
    """Ensure all seed templates exist as subtopic_knowledge entries with core_code."""
    existing = list((await db.execute(select(SubtopicKnowledge).where(SubtopicKnowledge.slug.is_not(None)))).scalars().all())
    by_slug = {st.slug: st for st in existing if st.slug}

    all_subtopics = list((await db.execute(select(SubtopicKnowledge))).scalars().all())
    by_name = {_normalize_name(st.name): st for st in all_subtopics}

    changed = False
    for seed in SEED_TEMPLATES:
        slug = seed["slug"]
        name = seed["name"]

        if slug in by_slug:
            st = by_slug[slug]
        elif _normalize_name(name) in by_name:
            st = by_name[_normalize_name(name)]
        else:
            st = SubtopicKnowledge(name=name, category=seed["category"])
            db.add(st)
            changed = True

        st.slug = slug
        if not st.core_code or st.core_code != seed["core_code"]:
            st.core_code = seed["core_code"]
            changed = True
        if not st.breakdown:
            st.breakdown = seed.get("breakdown")
            changed = True
        if not st.mental_model:
            st.mental_model = seed.get("mental_model")
            changed = True
        if not st.signals:
            st.signals = seed.get("signals")
            changed = True
        if not st.when_to_use:
            st.when_to_use = seed.get("when_to_use")
            changed = True
        if not st.recall_tasks:
            st.recall_tasks = seed.get("recall_tasks")
            changed = True

    if changed:
        await db.flush()
        await db.commit()


async def list_templates(db: AsyncSession, user_id: str) -> list[tuple[SubtopicKnowledge, SubtopicReview | None]]:
    """List subtopics that have core_code (i.e. are usable as templates)."""
    await ensure_seed_templates(db)
    subtopics = list((await db.execute(
        select(SubtopicKnowledge)
        .where(SubtopicKnowledge.core_code.is_not(None))
        .order_by(SubtopicKnowledge.category, SubtopicKnowledge.name)
    )).scalars().all())
    reviews = list((await db.execute(
        select(SubtopicReview).where(SubtopicReview.user_id == user_id)
    )).scalars().all())
    review_by_subtopic = {r.subtopic_id: r for r in reviews}
    return [(st, review_by_subtopic.get(st.id)) for st in subtopics]


async def get_template(db: AsyncSession, user_id: str, subtopic_id: int) -> tuple[SubtopicKnowledge, SubtopicReview | None] | None:
    await ensure_seed_templates(db)
    st = (await db.execute(select(SubtopicKnowledge).where(SubtopicKnowledge.id == subtopic_id))).scalar_one_or_none()
    if not st:
        return None
    review = (await db.execute(
        select(SubtopicReview).where(
            SubtopicReview.user_id == user_id,
            SubtopicReview.subtopic_id == subtopic_id,
        )
    )).scalar_one_or_none()
    return st, review


async def record_template_review(
    db: AsyncSession, user_id: str, subtopic_id: int, quality: int, notes: str | None = None
) -> SubtopicReview | None:
    st = (await db.execute(select(SubtopicKnowledge).where(SubtopicKnowledge.id == subtopic_id))).scalar_one_or_none()
    if not st:
        return None
    review = (await db.execute(
        select(SubtopicReview).where(
            SubtopicReview.user_id == user_id,
            SubtopicReview.subtopic_id == subtopic_id,
        )
    )).scalar_one_or_none()
    if not review:
        review = SubtopicReview(user_id=user_id, subtopic_id=subtopic_id)
        db.add(review)
    quality = max(0, min(5, quality))
    history = list(review.quality_history or [])
    history.append(quality)
    review.quality_history = history[-20:]
    review.last_reviewed = datetime.now(timezone.utc)
    interval_days = 1 if quality < 3 else 2 if quality == 3 else 4 if quality == 4 else 7
    review.next_review = review.last_reviewed + timedelta(days=interval_days)
    if notes is not None:
        review.notes = notes
    await db.commit()
    await db.refresh(review)
    await _sync_study_plan_item_status(db, user_id, subtopic_id, quality)
    return review


async def start_template(db: AsyncSession, user_id: str, subtopic_id: int) -> bool:
    """Mark the matching StudyPlanItem as in_progress (if not already completed)."""
    st = (await db.execute(select(SubtopicKnowledge).where(SubtopicKnowledge.id == subtopic_id))).scalar_one_or_none()
    if not st:
        return False
    return await _sync_study_plan_item_status(db, user_id, subtopic_id, status_override="in_progress")


async def _sync_study_plan_item_status(
    db: AsyncSession,
    user_id: str,
    subtopic_id: int,
    quality: int | None = None,
    status_override: str | None = None,
) -> bool:
    """Find a matching StudyPlanItem for this subtopic and update its status."""
    item = (await db.execute(
        select(StudyPlanItem)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .join(StudyPlan, StudyPlanSession.plan_id == StudyPlan.id)
        .where(
            StudyPlan.user_id == user_id,
            StudyPlanItem.item_type == "template",
            StudyPlanItem.subtopic_id == subtopic_id,
        )
    )).scalar_one_or_none()
    if not item:
        return False
    if status_override:
        if item.status == "completed":
            return False
        item.status = status_override
    elif quality is not None:
        if quality >= 4:
            item.status = "completed"
        elif quality < 3:
            item.status = "rework"
        elif item.status == "not_started":
            item.status = "in_progress"
    await db.commit()
    return True
