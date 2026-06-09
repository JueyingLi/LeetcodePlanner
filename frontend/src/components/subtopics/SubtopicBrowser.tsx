import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchSubtopics,
  fetchSubtopic,
  fetchSubtopicQuestions,
  generateSubtopicDescriptions,
  regenerateSubtopicDescription,
  rebuildTaxonomy,
  fetchTopicOrder,
  findAndAddQuestions,
} from "../../api/subtopics";
import { fetchPatternDeck, regenerateAllPatternAnalyses } from "../../api/patternDrill";
import { addTemplates, fetchAllCompleted, fetchTemplate, fetchTemplates, reviewTemplate, startTemplate } from "../../api/studyPlan";
import { Markdown } from "../ui/Markdown";
import { FillableCodeBlock, fillableLineIndexes } from "../ui/FillableCodeBlock";
import { VariantSection } from "./VariantSection";
import { PatternDrillDeck } from "../patterns/PatternDrillCard";
import { completedTemplateIds } from "../../lib/templateProgress";
import type { SubtopicInfo, Question, TemplateDetail, TemplateSummary } from "../../types";

// ---------------------------------------------------------------------------
// Parsing helpers
// ---------------------------------------------------------------------------

function parseSignalItems(text: string | null): string[] {
  if (!text) return [];
  const bullets = [...text.matchAll(/^[-*•]\s+(.+)$/gm)];
  if (bullets.length > 1) return bullets.map((m) => m[1].trim());
  if (text.includes(",")) {
    const parts = text.split(",").map((s) => s.trim()).filter((s) => s.length > 2);
    if (parts.length > 1) return parts;
  }
  const lines = text.split("\n").map((s) => s.trim()).filter((s) => s.length > 3);
  if (lines.length > 1) return lines;
  return text.trim() ? [text.trim()] : [];
}

function parseImplementationSteps(text: string | null): string[] {
  if (!text?.trim()) return [];
  const numbered = text.split(/\n(?=\d+\.\s)/);
  if (numbered.length > 1) return numbered.map((s) => s.trim()).filter(Boolean);
  const boldSections = text.split(/\n(?=\*\*)/);
  if (boldSections.length > 1) return boldSections.map((s) => s.trim()).filter(Boolean);
  const bullets = text.split(/\n(?=[-*]\s)/);
  if (bullets.length > 1) return bullets.map((s) => s.trim()).filter(Boolean);
  const paragraphs = text.split(/\n\n+/);
  if (paragraphs.length > 1) return paragraphs.map((s) => s.trim()).filter(Boolean);
  return [text.trim()];
}

type PatternCodeSection = {
  title: string;
  code: string;
  logic: string;
};

function normalizePatternName(value: string | null | undefined): string {
  return (value || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function templateMatchesSubtopic(template: TemplateSummary, subtopic: SubtopicInfo): boolean {
  const name = normalizePatternName(subtopic.name);
  const category = normalizePatternName(subtopic.category);
  const title = normalizePatternName(template.title);
  const sub = normalizePatternName(template.subtopic);
  const slug = normalizePatternName(template.slug);
  return (
    title === name ||
    sub === name ||
    slug === name ||
    name.includes(title) ||
    title.includes(name) ||
    (!!sub && name.includes(sub)) ||
    (!!category && title.includes(category))
  );
}

function codeSectionLogic(pattern: string, title: string): string {
  const key = `${normalizePatternName(pattern)}:${normalizePatternName(title)}`;
  const map: Record<string, string> = {
    "segment tree:segmenttree": "Owns the array length and tree storage. Leaves hold original values; internal nodes hold combined interval answers.",
    "segment tree:init": "Builds leaves first, then builds parents bottom-up so every parent satisfies the combine invariant.",
    "segment tree:update": "Changes one leaf and repairs only the ancestors whose intervals contain that index.",
    "segment tree:query": "Consumes complete stored intervals from the left and right boundaries, then moves both pointers upward.",
    "union find:dsu": "Stores parent pointers, component sizes, and the number of connected components.",
    "union find:init": "Starts with every node as its own root and component.",
    "union find:find": "Returns the representative root and compresses the path so future finds are faster.",
    "union find:union": "Merges two roots only if they differ, attaches smaller to larger, and updates component count.",
    "topological sort:topo sort": "Builds indegrees, repeatedly removes zero-prerequisite nodes, and uses output length to detect cycles.",
    "binary indexed tree:bit": "Stores prefix contributions in a 1-indexed array.",
    "binary indexed tree:add": "Walks upward through responsible BIT buckets and adds the delta.",
    "binary indexed tree:prefix sum": "Walks downward collecting buckets that exactly cover the prefix.",
    "difference array:apply range updates": "Marks only the boundary changes for each range update.",
    "difference array:build final array": "Runs one prefix scan to turn boundary changes into the actual values.",
    "bfs:bfs": "Uses a queue so states are processed by increasing distance.",
    "dijkstra:dijkstra": "Uses a heap to always expand the cheapest known state and skips stale heap entries.",
  };
  return map[key] || "Know the invariant this block preserves, what state it reads, and what state it updates.";
}

function titleFromCodeLine(line: string, fallback: string): string {
  const trimmed = line.trim();
  const match = trimmed.match(/^(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)/);
  if (!match) return fallback;
  return match[2].replace(/^__|__$/g, "").replace(/_/g, " ") || fallback;
}

function splitCodeIntoSections(code: string, pattern: string, fallbackLogic: string): PatternCodeSection[] {
  const lines = code.trim().split("\n");
  const sections: PatternCodeSection[] = [];
  let currentTitle = "Core code";
  let current: string[] = [];

  const flush = () => {
    if (current.length === 0) return;
    const block = current.join("\n").trimEnd();
    sections.push({
      title: currentTitle,
      code: block,
      logic: codeSectionLogic(pattern, currentTitle) || fallbackLogic,
    });
    current = [];
  };

  for (const line of lines) {
    const nextTitle = titleFromCodeLine(line, currentTitle);
    const startsBlock = /^(class|def)\s+/.test(line.trim());
    if (startsBlock && current.length > 0) {
      flush();
      currentTitle = nextTitle;
    } else if (startsBlock) {
      currentTitle = nextTitle;
    }
    current.push(line);
  }
  flush();
  return sections.length > 0 ? sections : [{ title: "Core code", code, logic: fallbackLogic }];
}

function extractCodeBlocksFromMarkdown(markdown: string | null, pattern: string): PatternCodeSection[] {
  if (!markdown) return [];
  const blocks = [...markdown.matchAll(/```(?:python|py)?\n([\s\S]*?)```/gi)];
  return blocks.flatMap((match, index) =>
    splitCodeIntoSections(match[1], pattern, `Code example ${index + 1} for this pattern.`),
  );
}

const SEGMENT_TREE_TEACHING_CODE = `# --- Segment Tree (Bottom-Up, Iterative) ---
# Goal: Answer range aggregate queries (sum, min, max) and support point updates, both in O(log n).
# When to use: Mutable array + repeated range queries. Naive is O(n) per query; this is O(log n).
# Key invariant: tree[i] = combine(tree[2*i], tree[2*i+1]) for every internal node.
class SegmentTree:
    # Goal: Build the segment tree from an initial array so all future queries are O(log n).
    # Input: nums (list[int]) — the initial array of values
    # Output: SegmentTree object with tree[] ready for update() and query()
    # Example: SegmentTree([1, 3, 5]) → internal tree supporting sum queries on [1, 3, 5]
    # Key idea: Leaves sit at tree[n..2n-1]; parents are built bottom-up so each stores its children's sum.
    def __init__(self, nums):
        self.n = len(nums)  # n is both the leaf count and the offset where leaves start in tree[]
        self.tree = [0] * (2 * self.n)  # tree[1] will hold the total sum; tree[n:2n] are the leaves
        # --- Phase 1: Copy input values into leaf positions ---
        for i, x in enumerate(nums):
            self.tree[self.n + i] = x  # leaf for nums[i] lives at tree[n + i]
        # --- Phase 2: Build parents bottom-up ---
        for i in range(self.n - 1, 0, -1):
            self.tree[i] = self.tree[2 * i] + self.tree[2 * i + 1]  # parent = sum of its two children

    # Goal: Change one element and repair all ancestor nodes so queries stay correct.
    # Input: index (int) — position in the original array; value (int) — new value to set
    # Output: None (mutates tree in place so future queries reflect the change)
    # Example: update(1, 10) on [1, 3, 5] → array becomes [1, 10, 5], all ancestor sums updated
    # Key idea: Only O(log n) ancestors contain this index — walk up and recompute each.
    def update(self, index, value):
        i = index + self.n  # convert array index to the corresponding leaf position in tree[]
        self.tree[i] = value  # overwrite the leaf with the new value
        # --- Walk upward, recomputing each ancestor ---
        i //= 2  # move to the parent of the changed leaf
        while i:
            self.tree[i] = self.tree[2 * i] + self.tree[2 * i + 1]  # recompute from children
            i //= 2  # move to the next ancestor

    # Goal: Compute the aggregate (sum) over a contiguous range [left, right] inclusive.
    # Input: left, right (int) — inclusive range bounds in the original array
    # Output: int — the sum of nums[left..right] under all updates applied so far
    # Example: query(0, 2) on [1, 10, 5] → 16
    # Key idea: Collect complete subtrees from both ends and move inward; each level contributes at most 2 nodes.
    def query(self, left, right):
        left += self.n  # convert array index to leaf position
        right += self.n  # convert array index to leaf position
        ans = 0  # identity element for sum (use float('inf') for min, -inf for max)
        # --- Shrink the range from both ends, collecting complete intervals ---
        while left <= right:
            if left % 2 == 1:  # left is a right child — its interval is fully inside the query
                ans += self.tree[left]  # consume this node's value
                left += 1  # move left boundary past this node
            if right % 2 == 0:  # right is a left child — its interval is fully inside the query
                ans += self.tree[right]  # consume this node's value
                right -= 1  # move right boundary past this node
            left //= 2  # move both boundaries up to the parent level
            right //= 2
        return ans  # accumulated sum over the query range`;

function teachingCodeForPattern(code: string, pattern: string): string {
  if (normalizePatternName(pattern).includes("segment tree")) return SEGMENT_TREE_TEACHING_CODE;
  return code;
}

const FALLBACK_PATTERN_CODE: Record<string, { code: string; logic: string }> = {
  "segment tree": {
    logic: "Range aggregate with point update. Change the identity and combine operation for min/max/gcd/custom values.",
    code: SEGMENT_TREE_TEACHING_CODE,
  },
  "union find": {
    logic: "Dynamic connectivity template. `find` returns the root; `union` merges roots and reports whether a merge happened.",
    code: `class DSU:
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
        return True`,
  },
  "topological sort": {
    logic: "Dependency ordering template. Zero indegree means all prerequisites have been satisfied.",
    code: `from collections import deque


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
    return order if len(order) == n else []`,
  },
  "difference array": {
    logic: "Range update template. Mark boundary deltas first, then recover actual values with one prefix scan.",
    code: `def apply_range_updates(n, updates):
    # diff[i] means "the value changes by this much starting at i".
    # Use n + 1 so right + 1 can be used as the undo boundary.
    diff = [0] * (n + 1)

    # Mark only the two boundaries of each inclusive range.
    for left, right, delta in updates:
        diff[left] += delta
        if right + 1 < n:
            diff[right + 1] -= delta

    # Convert boundary changes into actual values with one prefix scan.
    ans = [0] * n
    running = 0
    for i in range(n):
        running += diff[i]
        ans[i] = running
    return ans`,
  },
  "binary indexed tree": {
    logic: "Prefix aggregate with point update. BIT is compact and fast when the query can be expressed through prefixes.",
    code: `class BIT:
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
        return self.prefix_sum(right) - (self.prefix_sum(left - 1) if left else 0)`,
  },
  "bfs": {
    logic: "Unweighted shortest path template. Queue order guarantees first visit is shortest distance.",
    code: `from collections import deque


def bfs(start):
    q = deque([(start, 0)])
    seen = {start}
    while q:
        node, dist = q.popleft()
        for nei in neighbors(node):
            if nei in seen:
                continue
            seen.add(nei)
            q.append((nei, dist + 1))`,
  },
  "dijkstra": {
    logic: "Weighted shortest path template for non-negative edges.",
    code: `import heapq


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
    return dist`,
  },
  "binary search on answer": {
    logic: "Search the answer space, not the input. The checker must be monotonic.",
    code: `def binary_search_answer(lo, hi):
    while lo < hi:
        mid = (lo + hi) // 2
        if can(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo`,
  },
};

function fallbackCodeForSubtopic(subtopic: SubtopicInfo): { code: string; logic: string } | null {
  const name = normalizePatternName(subtopic.name);
  const category = normalizePatternName(subtopic.category);
  const key = Object.keys(FALLBACK_PATTERN_CODE).find((candidate) => {
    const normalized = normalizePatternName(candidate);
    return name.includes(normalized) || normalized.includes(name) || category.includes(normalized);
  });
  return key ? FALLBACK_PATTERN_CODE[key] : null;
}

function patternCodeSections(
  subtopic: SubtopicInfo,
  template: TemplateDetail | undefined,
): PatternCodeSection[] {
  const code = subtopic.core_code || template?.core_code;
  const breakdown = subtopic.breakdown || template?.breakdown || "";
  if (code?.trim()) {
    return splitCodeIntoSections(
      teachingCodeForPattern(code, subtopic.name),
      subtopic.name,
      breakdown,
    );
  }
  const fromMarkdown = extractCodeBlocksFromMarkdown(subtopic.implementation_keys, subtopic.name);
  if (fromMarkdown.length > 0) return fromMarkdown;
  const fallback = fallbackCodeForSubtopic(subtopic);
  return fallback ? splitCodeIntoSections(fallback.code, subtopic.name, fallback.logic) : [];
}


const difficultyColor: Record<string, string> = {
  Easy: "text-green-400",
  Medium: "text-yellow-400",
  Hard: "text-red-400",
};

// ---------------------------------------------------------------------------
// Detail view — tabs
// ---------------------------------------------------------------------------

const BASE_TABS = [
  { key: "concept" as const, label: "Understand", color: "#58CC02" },
  { key: "signals" as const, label: "Recognize", color: "#FFC800" },
  { key: "code" as const, label: "Implement", color: "#818CF8" },
  { key: "practice" as const, label: "Practice", color: "#38BDF8" },
];

const COMPARE_TAB = { key: "compare" as const, label: "vs Parent", color: "#F472B6" };

type DetailTab = "concept" | "signals" | "code" | "practice" | "compare";

function SubtopicDetailView({
  subtopic,
  onBack,
  onSelectQuestion,
  onOpenVariant,
  isStudied,
  studiedIds,
  knownSubtopics,
}: {
  subtopic: SubtopicInfo;
  onBack: () => void;
  onSelectQuestion: (id: number) => void;
  onOpenVariant: (id: number) => void;
  isStudied: boolean;
  studiedIds: Set<number>;
  knownSubtopics: SubtopicInfo[];
}) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<DetailTab>("concept");
  const [codeMode, setCodeMode] = useState<"fill" | "read">("fill");
  const [revealedCodeCount, setRevealedCodeCount] = useState(0);
  const [sectionDone, setSectionDone] = useState<Set<number>>(new Set());

  const { data: questions, isLoading: questionsLoading } = useQuery({
    queryKey: ["subtopicQuestions", subtopic.id],
    queryFn: () => fetchSubtopicQuestions(subtopic.id),
    enabled: activeTab === "practice",
  });
  const { data: templates } = useQuery({
    queryKey: ["templates"],
    queryFn: fetchTemplates,
    enabled: activeTab === "code",
  });
  const matchedTemplate = useMemo(
    () => (templates || []).find((template) => templateMatchesSubtopic(template, subtopic)),
    [templates, subtopic],
  );
  const { data: templateDetail } = useQuery({
    queryKey: ["template", matchedTemplate?.id],
    queryFn: () => fetchTemplate(matchedTemplate!.id),
    enabled: activeTab === "code" && !!matchedTemplate,
  });

  const findMut = useMutation({
    mutationFn: () => findAndAddQuestions(subtopic.id, 3),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subtopicQuestions", subtopic.id] });
      queryClient.invalidateQueries({ queryKey: ["subtopics"] });
      queryClient.invalidateQueries({ queryKey: ["questions"] });
    },
  });
  const regenMut = useMutation({
    mutationFn: () => regenerateSubtopicDescription(subtopic.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subtopics"] });
    },
  });
  const addStudyMut = useMutation({
    mutationFn: () => addTemplates(1, subtopic.id),
    onSuccess: (data) => {
      queryClient.setQueryData(["studyPlan"], data);
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });
  const markDoneMut = useMutation({
    mutationFn: () => reviewTemplate(subtopic.id, 5),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      queryClient.invalidateQueries({ queryKey: ["reviewAll"] });
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });
  const startMut = useMutation({
    mutationFn: () => startTemplate(subtopic.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });

  const signals = useMemo(() => parseSignalItems(subtopic.key_signals), [subtopic.key_signals]);
  const implSteps = useMemo(
    () => parseImplementationSteps(subtopic.implementation_keys),
    [subtopic.implementation_keys],
  );
  const codeSections = useMemo(
    () => patternCodeSections(subtopic, templateDetail),
    [subtopic, templateDetail],
  );
  const visibleCodeSections = codeSections.slice(0, revealedCodeCount);
  const revealNextCodeSection = () =>
    setRevealedCodeCount((count) => Math.min(count + 1, codeSections.length));

  const allCodeDone =
    codeSections.length > 0 &&
    revealedCodeCount >= codeSections.length &&
    codeSections.every((section, index) => fillableLineIndexes(section.code).length === 0 || sectionDone.has(index));

  useEffect(() => {
    if (allCodeDone && !isStudied) {
      markDoneMut.mutate();
    }
  }, [allCodeDone]);

  useEffect(() => {
    setCodeMode("fill");
    setRevealedCodeCount(0);
    setSectionDone(new Set());
  }, [subtopic.id]);

  if (!subtopic.description) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="w-9 h-9 rounded-lg bg-[#1C2B33] text-white flex items-center justify-center active:bg-[#243640]"
          >
            &larr;
          </button>
          <h2 className="text-white font-bold">{subtopic.name}</h2>
        </div>
        <div className="bg-[#1C2B33] rounded-xl p-6 text-center space-y-3">
          <p className="text-[#9CA3AF] text-sm">
            No description generated yet for this pattern.
          </p>
          <p className="text-[#9CA3AF] text-xs">
            Go back and tap "Generate Descriptions" to auto-fill all patterns with AI content.
          </p>
          <button
            onClick={() => regenMut.mutate()}
            disabled={regenMut.isPending}
            className="bg-[#58CC02] text-white rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            {regenMut.isPending ? "Generating..." : "Generate content"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Sticky header */}
      <div className="sticky top-0 z-20 -mx-4 px-4 py-3 bg-[#131F24]/95 backdrop-blur border-b border-[#2a3f4a]">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            aria-label="Back to patterns"
            className="w-9 h-9 rounded-lg bg-[#1C2B33] text-white flex items-center justify-center active:bg-[#243640]"
          >
            &larr;
          </button>
          <div className="min-w-0 flex-1">
            <p className="text-xs text-[#9CA3AF]">
              {subtopic.parent_name ? (
                <>{subtopic.category} &rsaquo; <button onClick={onBack} className="text-[#818CF8] hover:underline">{subtopic.parent_name}</button></>
              ) : subtopic.category}
            </p>
            <h2 className="text-white font-bold truncate">{subtopic.name}</h2>
          </div>
          {!isStudied && (
            <button
              onClick={() => addStudyMut.mutate()}
              disabled={addStudyMut.isPending}
              className="h-9 rounded-lg bg-[#58CC02] text-white px-3 text-xs font-semibold flex items-center justify-center active:bg-[#46A302] disabled:opacity-50"
            >
              {addStudyMut.isPending ? "Adding..." : "+ Study"}
            </button>
          )}
          {isStudied && (
            <span className="h-9 rounded-lg bg-[#58CC02]/20 text-[#58CC02] px-3 text-xs font-semibold flex items-center justify-center">
              Done
            </span>
          )}
          <button
            onClick={() => regenMut.mutate()}
            disabled={regenMut.isPending}
            aria-label={`Regenerate ${subtopic.name}`}
            title="Regenerate"
            className="w-9 h-9 rounded-lg bg-[#1C2B33] text-[#D1D5DB] flex items-center justify-center active:bg-[#243640] disabled:opacity-50"
          >
            <span className={regenMut.isPending ? "animate-spin" : ""}>↻</span>
          </button>
        </div>
        {addStudyMut.isError && (
          <p className="text-xs text-[#FF8A8A] mt-2">{(addStudyMut.error as Error).message}</p>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 overflow-x-auto">
        {[...BASE_TABS, ...(subtopic.parent_id ? [COMPARE_TAB] : [])].map((tab) => (
          <button
            key={tab.key}
            onClick={() => {
              setActiveTab(tab.key);
              if (tab.key === "code" && !isStudied && !startMut.isPending) {
                startMut.mutate();
              }
            }}
            className={`shrink-0 rounded px-2 py-1 text-[10px] font-semibold leading-none transition-colors ${
              activeTab === tab.key
                ? ""
                : "bg-[#1C2B33] text-[#9CA3AF]"
            }`}
            style={
              activeTab === tab.key
                ? {
                    backgroundColor: tab.color + "20",
                    color: tab.color,
                    border: `1px solid ${tab.color}40`,
                  }
                : undefined
            }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Concept tab ─────────────────────────────────────────── */}
      {activeTab === "concept" && (
        <div className="space-y-3">
          <div className="bg-[#1E3328] border border-[#2F6B46] rounded-lg p-3">
            <h3 className="text-[#58CC02] font-bold text-[11px] uppercase tracking-wide mb-2">
              Core Idea
            </h3>
            <div className="text-white text-sm leading-relaxed">
              <Markdown>{subtopic.description}</Markdown>
            </div>
          </div>

          {subtopic.when_to_use && (
            <div className="bg-[#302B1E] border border-[#6B5A2F] rounded-lg p-3">
              <h3 className="text-[#FFC800] font-bold text-[11px] uppercase tracking-wide mb-2">
                When to Reach for This
              </h3>
              <div className="text-[#D1D5DB] text-xs leading-relaxed">
                <Markdown>{subtopic.when_to_use}</Markdown>
              </div>
            </div>
          )}

          <button
            onClick={() => setActiveTab("signals")}
            className="w-full mt-2 py-2 rounded-lg text-xs font-bold bg-[#FFC800]/10 text-[#FFC800] border border-[#FFC800]/30 active:bg-[#FFC800]/20"
          >
            Next: Recognize →
          </button>
        </div>
      )}

      {/* ── Signals tab ─────────────────────────────────────────── */}
      {activeTab === "signals" && (
        <div className="space-y-3">
          <div className="bg-[#1C2B33] rounded-lg p-3 space-y-3">
            <div>
              <h3 className="text-[#FFC800] font-bold text-[11px] uppercase tracking-wide mb-1">
                Pattern Triggers
              </h3>
              <p className="text-xs text-[#9CA3AF]">
                When you spot these clues in a problem, think: <span className="text-white font-medium">{subtopic.name}</span>
              </p>
            </div>

            {signals.length > 1 ? (
              <div className="space-y-2">
                {signals.map((signal, i) => (
                  <div
                    key={i}
                    className="bg-[#FFC800]/5 border border-[#FFC800]/20 rounded-md p-2.5 flex items-start gap-2"
                  >
                    <span className="shrink-0 w-5 h-5 rounded-full bg-[#FFC800]/20 text-[#FFC800] text-[11px] font-bold flex items-center justify-center mt-0.5">
                      {i + 1}
                    </span>
                    <p className="text-xs text-[#FFE08A] leading-relaxed">{signal}</p>
                  </div>
                ))}
              </div>
            ) : subtopic.key_signals ? (
              <div className="text-xs text-[#D1D5DB]">
                <Markdown>{subtopic.key_signals}</Markdown>
              </div>
            ) : null}
          </div>

          <button
            onClick={() => setActiveTab("code")}
            className="w-full mt-2 py-2 rounded-lg text-xs font-bold bg-[#818CF8]/10 text-[#818CF8] border border-[#818CF8]/30 active:bg-[#818CF8]/20"
          >
            Next: Implement →
          </button>
        </div>
      )}

      {/* ── Code / Implement tab ────────────────────────────────── */}
      {activeTab === "code" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex rounded-lg overflow-hidden border border-[#2a3f4a]">
              <button
                onClick={() => setCodeMode("fill")}
                className={`px-2.5 py-1.5 text-[11px] ${codeMode === "fill" ? "bg-[#818CF8] text-white" : "bg-[#243640] text-[#D1D5DB]"}`}
              >
                Fill in
              </button>
              <button
                onClick={() => setCodeMode("read")}
                className={`px-2.5 py-1.5 text-[11px] ${codeMode === "read" ? "bg-[#818CF8] text-white" : "bg-[#243640] text-[#D1D5DB]"}`}
              >
                Read
              </button>
            </div>
            <span className="text-xs text-[#9CA3AF] shrink-0">
              {revealedCodeCount}/{codeSections.length} sections
            </span>
          </div>

          {codeSections.length > 0 ? (
            <>
              <div className="h-1.5 rounded-full bg-[#243640] overflow-hidden">
                <div
                  className="h-full bg-[#818CF8] transition-all"
                  style={{ width: `${(revealedCodeCount / codeSections.length) * 100}%` }}
                />
              </div>

              <div className="flex flex-wrap gap-1.5">
                {codeSections.map((section, index) => (
                  <button
                    key={`${section.title}-${index}`}
                    onClick={() => setRevealedCodeCount((count) => Math.max(count, index + 1))}
                    className={`text-[11px] rounded-full px-2 py-0.5 ${
                      index < revealedCodeCount
                        ? "bg-[#818CF8]/20 text-[#C8C4FF]"
                        : "bg-[#243640] text-[#9CA3AF]"
                    }`}
                  >
                    {index + 1}. {section.title}
                  </button>
                ))}
              </div>

              {revealedCodeCount === 0 && (
                <div className="bg-[#1C2B33] rounded-lg p-3 space-y-2 text-center">
                  <p className="text-white text-sm font-semibold">Start with the first code block</p>
                  <p className="text-xs text-[#9CA3AF]">
                    Reveal one section, fill the hidden lines from memory, then move to the next.
                  </p>
                  <button
                    onClick={revealNextCodeSection}
                    className="bg-[#818CF8] text-white rounded-lg px-3 py-1.5 text-xs font-semibold"
                  >
                    Reveal section 1
                  </button>
                </div>
              )}

              {visibleCodeSections.map((section, index) => (
                <div key={`${section.title}-${index}`} className="bg-[#1C2B33] rounded-lg overflow-hidden">
                  <div className="p-3 border-b border-[#2a3f4a]">
                    <p className="text-white text-sm font-semibold">
                      {index + 1}. {section.title}
                    </p>
                    <p className="text-xs text-[#D1D5DB] mt-1 leading-relaxed">{section.logic}</p>
                  </div>
                  {codeMode === "fill" ? (
                    <FillableCodeBlock
                      key={`${subtopic.id}-${index}`}
                      code={section.code}
                      subtopicId={subtopic.id}
                      subtopicName={subtopic.name}
                      onStatusChange={(status) => {
                        if (status === "done") {
                          setSectionDone((prev) => new Set(prev).add(index));
                        } else {
                          setSectionDone((prev) => {
                            const next = new Set(prev);
                            next.delete(index);
                            return next;
                          });
                        }
                      }}
                    />
                  ) : (
                    <pre className="bg-[#0E171B] p-3 overflow-x-auto text-xs text-green-300 whitespace-pre min-h-28">
                      {section.code}
                    </pre>
                  )}
                </div>
              ))}

              {revealedCodeCount > 0 && revealedCodeCount < codeSections.length && (
                <button
                  onClick={revealNextCodeSection}
                  className="w-full bg-[#818CF8] text-white rounded-lg py-2 text-xs font-semibold"
                >
                  Reveal next section ({revealedCodeCount + 1}/{codeSections.length})
                </button>
              )}

              {revealedCodeCount > 0 && (
                <button
                  onClick={() => {
                    setRevealedCodeCount(0);
                    setSectionDone(new Set());
                  }}
                  className="w-full bg-[#243640] text-[#D1D5DB] rounded-lg py-2 text-xs"
                >
                  Hide sections and restart recall
                </button>
              )}
            </>
          ) : (
            <div className="bg-[#1C2B33] rounded-lg p-3 space-y-2">
              <h3 className="text-[#818CF8] font-bold text-[11px] uppercase tracking-wide">
                Implementation Guide
              </h3>
              {implSteps.length > 0 ? (
                <div className="space-y-2">
                  {implSteps.map((step, i) => (
                    <div key={i} className="bg-[#131F24] border border-[#2a3f4a] rounded-md p-2.5">
                      <div className="flex items-start gap-2">
                        <span className="shrink-0 w-5 h-5 rounded-full bg-[#818CF8]/20 text-[#818CF8] text-[11px] font-bold flex items-center justify-center mt-0.5">
                          {i + 1}
                        </span>
                        <div className="flex-1 text-xs text-[#D1D5DB] min-w-0">
                          <Markdown>{step}</Markdown>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[#9CA3AF]">
                  No implementation content is available yet. Use the refresh icon to regenerate this pattern.
                </p>
              )}
            </div>
          )}

          {/* Variants */}
          {(subtopic.variants || (subtopic.variant_children && subtopic.variant_children.length > 0)) && (
            <VariantSection
              subtopic={subtopic}
              variantsText={subtopic.variants}
              onOpenVariant={onOpenVariant}
              studiedIds={studiedIds}
              knownSubtopics={knownSubtopics}
            />
          )}

          {/* Pitfalls */}
          {subtopic.common_pitfalls && (
            <div className="bg-[#372329] border border-[#7A3B4B] rounded-lg p-3 space-y-2">
              <h3 className="text-[#FF8A8A] font-bold text-[11px] uppercase tracking-wide">
                Common Pitfalls
              </h3>
              <div className="text-xs text-[#D1D5DB]">
                <Markdown>{subtopic.common_pitfalls}</Markdown>
              </div>
            </div>
          )}

          <button
            onClick={() => setActiveTab("practice")}
            className="w-full mt-2 py-2 rounded-lg text-xs font-bold bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30 active:bg-[#38BDF8]/20"
          >
            Next: Practice →
          </button>
        </div>
      )}

      {/* ── Practice tab ────────────────────────────────────────── */}
      {activeTab === "practice" && (
        <div className="space-y-3">
          <div className="bg-[#1C2B33] rounded-lg p-3 space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-[#38BDF8] font-bold text-[11px] uppercase tracking-wide">
                  Practice Problems
                </h3>
                <p className="text-xs text-[#9CA3AF] mt-1">
                  {subtopic.question_count} question{subtopic.question_count !== 1 ? "s" : ""} tagged
                </p>
              </div>
              <button
                onClick={() => findMut.mutate()}
                disabled={findMut.isPending}
                className="text-xs bg-[#58CC02] text-white px-2.5 py-1.5 rounded-md font-medium disabled:opacity-50"
              >
                {findMut.isPending ? "Adding..." : "Add Questions"}
              </button>
            </div>

            {findMut.isPending && (
              <p className="text-xs text-[#9CA3AF]">
                Searching for LeetCode problems and generating AI solutions...
              </p>
            )}
            {findMut.isSuccess && (
              <div className="text-xs space-y-1">
                {findMut.data.added.map((a) => (
                  <p key={a.question_id} className="text-[#58CC02]">
                    {a.existed ? "Tagged" : "Added"}: {a.title}
                  </p>
                ))}
                {findMut.data.errors.map((e) => (
                  <p key={e.number} className="text-[#FF4B4B]">
                    Failed #{e.number} {e.title}: {e.error}
                  </p>
                ))}
              </div>
            )}
            {findMut.isError && (
              <p className="text-xs text-[#FF4B4B]">{(findMut.error as Error).message}</p>
            )}

            {questionsLoading ? (
              <p className="text-xs text-[#9CA3AF] text-center py-3">Loading questions...</p>
            ) : questions && questions.length > 0 ? (
              <div className="space-y-2">
                {questions.map((q: Question) => (
                  <button
                    key={q.id}
                    onClick={() => onSelectQuestion(q.id)}
                    className="w-full text-left bg-[#131F24] rounded-md p-2.5 active:bg-[#243640] border border-[#2a3f4a]"
                  >
                    <div className="flex items-center gap-2">
                      {q.number && <span className="text-xs text-[#9CA3AF]">#{q.number}</span>}
                      <span className={`text-xs font-medium ${difficultyColor[q.difficulty] || "text-gray-400"}`}>
                        {q.difficulty}
                      </span>
                    </div>
                    <p className="text-white text-xs font-medium mt-1 truncate">{q.title}</p>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-[#9CA3AF] text-center py-3">
                No questions tagged yet. Tap "Add Questions" to find problems that use this pattern.
              </p>
            )}
          </div>

        </div>
      )}

      {/* ── Compare tab (variants only) ────────────────────────── */}
      {activeTab === "compare" && subtopic.parent_id && (
        <div className="space-y-3">
          {subtopic.comparison_same && (
            <div className="bg-[#1E3328] border border-[#2F6B46] rounded-lg p-3">
              <h3 className="text-[#58CC02] font-bold text-[11px] uppercase tracking-wide mb-2">
                What Stays the Same
              </h3>
              <div className="text-xs text-[#D1D5DB] leading-relaxed">
                <Markdown>{subtopic.comparison_same}</Markdown>
              </div>
            </div>
          )}

          {subtopic.comparison_different && (
            <div className="bg-[#302B1E] border border-[#6B5A2F] rounded-lg p-3">
              <h3 className="text-[#FFC800] font-bold text-[11px] uppercase tracking-wide mb-2">
                What Changes
              </h3>
              <div className="text-xs text-[#D1D5DB] leading-relaxed">
                <Markdown>{subtopic.comparison_different}</Markdown>
              </div>
            </div>
          )}

          {subtopic.comparison_when && (
            <div className="bg-[#1C2533] border border-[#2F466B] rounded-lg p-3">
              <h3 className="text-[#38BDF8] font-bold text-[11px] uppercase tracking-wide mb-2">
                When to Use This vs {subtopic.parent_name}
              </h3>
              <div className="text-xs text-[#D1D5DB] leading-relaxed">
                <Markdown>{subtopic.comparison_when}</Markdown>
              </div>
            </div>
          )}

          {subtopic.comparison_code && (
            <div className="bg-[#1C2B33] rounded-lg p-3">
              <h3 className="text-[#F472B6] font-bold text-[11px] uppercase tracking-wide mb-2">
                Code Comparison
              </h3>
              <div className="text-xs text-[#D1D5DB] leading-relaxed">
                <Markdown>{subtopic.comparison_code}</Markdown>
              </div>
            </div>
          )}

          {!subtopic.comparison_same && !subtopic.comparison_different && !subtopic.comparison_when && !subtopic.comparison_code && (
            <div className="bg-[#1C2B33] rounded-lg p-6 text-center">
              <p className="text-[#9CA3AF] text-sm">No comparison content generated yet.</p>
              <p className="text-[#9CA3AF] text-xs mt-1">Try regenerating this variant's content.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// List card — compact card shown in the pattern browser grid
// ---------------------------------------------------------------------------

function SubtopicListCard({
  subtopic,
  onOpen,
  onOpenVariant,
  onAddToStudy,
  isAdding,
  isStudied,
  studiedIds,
}: {
  subtopic: SubtopicInfo;
  onOpen: () => void;
  onOpenVariant: (id: number) => void;
  onAddToStudy: () => void;
  isAdding: boolean;
  isStudied: boolean;
  studiedIds: Set<number>;
}) {
  return (
    <div className="w-full bg-[#1C2B33] rounded-xl p-4 text-left transition-colors">
      <div className="flex items-center gap-3">
        <button onClick={onOpen} className="flex-1 min-w-0 text-left active:opacity-80">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white font-medium">{subtopic.name}</span>
            {isStudied && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-[#58CC02]/20 text-[#58CC02]">
                Done
              </span>
            )}
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                subtopic.question_count > 0
                  ? "bg-[#243640] text-[#9CA3AF]"
                  : "bg-[#4A4024] text-[#FFE08A]"
              }`}
            >
              {subtopic.question_count > 0
                ? `${subtopic.question_count} question${subtopic.question_count !== 1 ? "s" : ""}`
                : "Needs question"}
            </span>
            {subtopic.question_count === 0 && (
              <span className="text-xs text-[#9CA3AF]">
                Practice → Add Questions
              </span>
            )}
            {!subtopic.description && (
              <span className="text-xs bg-[#FFC800]/20 text-[#FFC800] px-2 py-0.5 rounded-full">
                No content
              </span>
            )}
          </div>
          {subtopic.description && (
            <p className="text-xs text-[#9CA3AF] mt-1 line-clamp-2">{subtopic.description}</p>
          )}
        </button>
        {isStudied ? (
          <span className="shrink-0 rounded-lg bg-[#58CC02]/20 text-[#58CC02] px-3 py-2 text-xs font-semibold">
            ✓ Done
          </span>
        ) : (
          <button
            onClick={onAddToStudy}
            disabled={isAdding}
            className="shrink-0 rounded-lg bg-[#58CC02] text-white px-3 py-2 text-xs font-semibold disabled:opacity-50 active:bg-[#46A302]"
          >
            {isAdding ? "Adding" : "+ Study"}
          </button>
        )}
        <button
          onClick={onOpen}
          aria-label={`Open ${subtopic.name}`}
          className="text-[#9CA3AF] text-lg shrink-0 px-1 active:text-white"
        >
          &rsaquo;
        </button>
      </div>
      {subtopic.variant_children && subtopic.variant_children.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2 ml-1">
          {subtopic.variant_children.map((v) => {
            const done = studiedIds.has(v.id);
            return (
              <button
                key={v.id}
                onClick={() => onOpenVariant(v.id)}
                className={`text-[11px] pl-2 pr-1.5 py-0.5 rounded-full border transition-colors inline-flex items-center gap-1.5 ${
                  done
                    ? "bg-[#58CC02]/15 text-[#58CC02] border-[#58CC02]/30"
                    : "bg-[#818CF8]/15 text-[#C8C4FF] border-[#818CF8]/30 hover:bg-[#818CF8]/25 active:bg-[#818CF8]/35"
                }`}
              >
                <span>{v.name}</span>
                {done && (
                  <span className="w-3.5 h-3.5 rounded-full bg-[#58CC02] text-[#131F24] flex items-center justify-center text-[9px] leading-none font-bold">
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main browser
// ---------------------------------------------------------------------------

export function SubtopicBrowser({
  onSelectQuestion,
}: {
  onSelectQuestion: (id: number) => void;
}) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const [mode, setMode] = useState<"learn" | "drill">("learn");
  const [selectedSubtopicId, setSelectedSubtopicId] = useState<number | null>(null);
  const [addingStudyId, setAddingStudyId] = useState<number | null>(null);

  const { data: subtopics, isLoading } = useQuery({
    queryKey: ["subtopics"],
    queryFn: () => fetchSubtopics(),
  });

  const { data: deck, isLoading: deckLoading } = useQuery({
    queryKey: ["patternDeck"],
    queryFn: () => fetchPatternDeck(),
    enabled: mode === "drill",
  });

  const { data: topicOrder } = useQuery({
    queryKey: ["topicOrder"],
    queryFn: fetchTopicOrder,
  });

  const { data: allTemplates } = useQuery({
    queryKey: ["templates"],
    queryFn: fetchTemplates,
  });
  const { data: allCompleted } = useQuery({
    queryKey: ["reviewAll"],
    queryFn: fetchAllCompleted,
  });

  const studiedIds = useMemo(() => {
    return completedTemplateIds(allTemplates, allCompleted?.items);
  }, [allTemplates, allCompleted]);

  const genMut = useMutation({
    mutationFn: generateSubtopicDescriptions,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subtopics"] });
    },
  });

  const rebuildMut = useMutation({
    mutationFn: rebuildTaxonomy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subtopics"] });
      queryClient.invalidateQueries({ queryKey: ["questions"] });
      queryClient.invalidateQueries({ queryKey: ["topics"] });
    },
  });

  const regenAllMut = useMutation({
    mutationFn: regenerateAllPatternAnalyses,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["patternDeck"] });
    },
  });
  const addStudyMut = useMutation({
    mutationFn: (subtopicId: number) => addTemplates(1, subtopicId),
    onMutate: (subtopicId) => {
      setAddingStudyId(subtopicId);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["studyPlan"], data);
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
    onSettled: () => {
      setAddingStudyId(null);
    },
  });

  const topLevelMatch =
    selectedSubtopicId != null
      ? (subtopics || []).find((st) => st.id === selectedSubtopicId) ?? null
      : null;

  const { data: fetchedVariant } = useQuery({
    queryKey: ["subtopic", selectedSubtopicId],
    queryFn: () => fetchSubtopic(selectedSubtopicId!),
    enabled: selectedSubtopicId != null && !topLevelMatch,
  });

  const selectedSubtopic = topLevelMatch ?? fetchedVariant ?? null;

  if (isLoading) {
    return <div className="text-center text-[#9CA3AF]">Loading patterns...</div>;
  }

  if (selectedSubtopic && mode === "learn") {
    return (
      <SubtopicDetailView
        subtopic={selectedSubtopic}
        onBack={() => {
          if (selectedSubtopic.parent_id) {
            setSelectedSubtopicId(selectedSubtopic.parent_id);
          } else {
            setSelectedSubtopicId(null);
          }
        }}
        onSelectQuestion={onSelectQuestion}
        onOpenVariant={(id: number) => setSelectedSubtopicId(id)}
        isStudied={studiedIds.has(selectedSubtopic.id)}
        studiedIds={studiedIds}
        knownSubtopics={subtopics || []}
      />
    );
  }

  const filtered = (subtopics || []).filter(
    (st) =>
      !filter ||
      st.name.toLowerCase().includes(filter.toLowerCase()) ||
      st.category.toLowerCase().includes(filter.toLowerCase()),
  );

  const grouped = filtered.reduce<Record<string, SubtopicInfo[]>>((acc, st) => {
    if (!acc[st.category]) acc[st.category] = [];
    acc[st.category].push(st);
    return acc;
  }, {});

  const hasAnyMissing = (subtopics || []).some((st) => !st.description);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-bold">Topics & Techniques</h3>
        <div className="flex gap-2">
          <button
            onClick={() => rebuildMut.mutate()}
            disabled={rebuildMut.isPending}
            className="text-xs bg-[#818CF8] text-white px-3 py-1.5 rounded-lg font-medium disabled:opacity-50"
          >
            {rebuildMut.isPending ? "Rebuilding..." : "Rebuild Taxonomy"}
          </button>
          {hasAnyMissing && (
            <button
              onClick={() => genMut.mutate()}
              disabled={genMut.isPending}
              className="text-xs bg-[#FFC800] text-[#131F24] px-3 py-1.5 rounded-lg font-medium disabled:opacity-50"
            >
              {genMut.isPending ? "Generating..." : "Generate Descriptions"}
            </button>
          )}
        </div>
      </div>

      {(genMut.isError || rebuildMut.isError || addStudyMut.isError) && (
        <p className="text-red-400 text-sm">
          {((genMut.error || rebuildMut.error || addStudyMut.error) as Error).message}
        </p>
      )}
      {rebuildMut.isSuccess && (
        <p className="text-[#58CC02] text-sm">Taxonomy rebuilt successfully.</p>
      )}

      <div className="flex gap-2">
        {(["learn", "drill"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`text-sm font-semibold rounded-lg px-3 py-1.5 ${
              mode === m
                ? "bg-[#58CC02]/20 text-[#7DEB35]"
                : "bg-[#1C2B33] text-[#9CA3AF]"
            }`}
          >
            {m === "learn" ? "Learn" : "Pattern drill"}
          </button>
        ))}
      </div>

      {mode === "drill" && (
        <p className="text-xs text-[#9CA3AF]">
          Recognize the data + operation, reveal each step, then grade yourself.
        </p>
      )}

      {mode === "learn" && (
        <input
          type="text"
          placeholder="Search patterns..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full bg-[#1C2B33] text-white rounded-lg px-3 py-2 text-sm placeholder-[#9CA3AF] focus:outline-none focus:ring-1 focus:ring-[#58CC02]"
        />
      )}

      {mode === "drill" ? (
        deckLoading ? (
          <p className="text-[#9CA3AF] text-sm text-center py-4">Loading drill deck...</p>
        ) : deck && deck.items.length > 0 ? (
          <PatternDrillDeck
            cards={deck.items.map((card) => ({
              questionId: card.id,
              preloaded: card,
              completed: card.completed,
            }))}
            onSelectQuestion={onSelectQuestion}
            onRegenerateAll={() => regenAllMut.mutate()}
            isRegeneratingAll={regenAllMut.isPending}
          />
        ) : (
          <p className="text-[#9CA3AF] text-sm text-center py-4">
            No drill cards yet. Generate AI solutions for a question (or open today's plan) to
            create pattern analyses.
          </p>
        )
      ) : Object.keys(grouped).length === 0 ? (
        <p className="text-[#9CA3AF] text-sm text-center py-4">
          No patterns yet. Import questions with subtopics to build your knowledge base.
        </p>
      ) : (
        Object.entries(grouped)
          .sort(([a], [b]) => {
            const order = topicOrder || [];
            const ai = order.indexOf(a);
            const bi = order.indexOf(b);
            return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
          })
          .map(([category, items]) => (
            <div key={category} className="space-y-2">
              <h4 className="text-sm font-medium text-[#58CC02]">{category}</h4>
              {items.map((st) => (
                <SubtopicListCard
                  key={st.id}
                  subtopic={st}
                  onOpen={() => setSelectedSubtopicId(st.id)}
                  onOpenVariant={(id) => setSelectedSubtopicId(id)}
                  onAddToStudy={() => addStudyMut.mutate(st.id)}
                  isAdding={addingStudyId === st.id}
                  isStudied={studiedIds.has(st.id)}
                  studiedIds={studiedIds}
                />
              ))}
            </div>
          ))
      )}
    </div>
  );
}
