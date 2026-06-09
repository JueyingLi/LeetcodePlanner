import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addTemplates,
  addPatternDrills,
  fetchAllCompleted,
  fetchStudyPlan,
  fetchTemplates,
  regenerateStudyPlan,
  reviewTemplate,
  skipAndReplaceTemplate,
  updateStudyPlanItem,
} from "../../api/studyPlan";
import type { ReviewItem } from "../../api/studyPlan";
import { fetchSubtopics } from "../../api/subtopics";
import { Markdown } from "../ui/Markdown";
import { FillableCodeBlock, fillableLineIndexes } from "../ui/FillableCodeBlock";
import { VariantSection } from "../subtopics/VariantSection";
import { PatternDrillDeck } from "../patterns/PatternDrillCard";
import type { StudyPlanItem, StudyPlanSession, SubtopicInfo } from "../../types";
import { ReviewQuizSession } from "./ReviewQuizSession";

const difficultyColor: Record<string, string> = {
  Easy: "text-green-400",
  Medium: "text-yellow-400",
  Hard: "text-red-400",
};



function StatusControls({
  item,
  compact = false,
}: {
  item: StudyPlanItem;
  compact?: boolean;
}) {
  const queryClient = useQueryClient();
  const updateMut = useMutation({
    mutationFn: (data: Partial<Pick<StudyPlanItem, "status" | "pinned" | "notes">>) =>
      updateStudyPlanItem(item.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });

  const setStatus = (status: string) => {
    updateMut.mutate({ status: item.status === status ? "not_started" : status });
  };

  const base = compact
    ? "text-xs px-2 py-1 rounded"
    : "text-xs font-semibold px-3 py-2 rounded-lg";
  const inactive = "bg-[#243640] text-white";

  return (
    <div className={`flex ${compact ? "flex-col" : "flex-wrap"} gap-1.5`}>
      <button
        onClick={() => setStatus("in_progress")}
        disabled={updateMut.isPending}
        className={`${base} ${
          item.status === "in_progress" ? "bg-[#FFC800]/20 text-[#FFC800]" : inactive
        } disabled:opacity-50`}
      >
        {item.status === "in_progress" ? "Undo" : "Start"}
      </button>
      <button
        onClick={() => setStatus("completed")}
        disabled={updateMut.isPending}
        className={`${base} ${
          item.status === "completed" ? "bg-[#58CC02]/20 text-[#58CC02]" : inactive
        } disabled:opacity-50`}
      >
        {item.status === "completed" ? "Undo" : "Complete"}
      </button>
      <button
        onClick={() => setStatus("rework")}
        disabled={updateMut.isPending}
        className={`${base} ${
          item.status === "rework" ? "bg-[#FF4B4B]/20 text-[#FF8A8A]" : inactive
        } disabled:opacity-50`}
      >
        {item.status === "rework" ? "Undo" : "Rework"}
      </button>
    </div>
  );
}

function templateStatusForQuality(quality: number): StudyPlanItem["status"] {
  if (quality >= 4) return "completed";
  if (quality <= 2) return "rework";
  return "in_progress";
}


function sessionStats(session: StudyPlanSession) {
  const visibleItems = session.items.filter((item) => item.status !== "skipped");
  const total = visibleItems.length;
  const completed = visibleItems.filter((item) => item.status === "completed").length;
  const minutes = visibleItems.reduce((sum, item) => sum + item.estimated_minutes, 0);
  return { total, completed, minutes };
}

function sessionDisplayTitle(session: StudyPlanSession): string {
  if (session.session_type === "template_review") return "Popular Templates";
  return session.title;
}




function sessionCardClasses(sessionType: string): { card: string; chip: string; accent: string } {
  const styles: Record<string, { card: string; chip: string; accent: string }> = {
    review: {
      card: "bg-[#20303A] border border-[#3B5361]",
      chip: "bg-[#334B59] text-[#BFE8FF]",
      accent: "bg-[#38BDF8]",
    },
    template_review: {
      card: "bg-[#1E3328] border border-[#2F6B46]",
      chip: "bg-[#58CC02]/15 text-[#7DEB35]",
      accent: "bg-[#58CC02]",
    },
    new: {
      card: "bg-[#302B1E] border border-[#6B5A2F]",
      chip: "bg-[#4A4024] text-[#FFE08A]",
      accent: "bg-[#FFC800]",
    },
    hard_block: {
      card: "bg-[#372329] border border-[#7A3B4B]",
      chip: "bg-[#552D38] text-[#FFB4C4]",
      accent: "bg-[#FF4B4B]",
    },
    pattern_drill: {
      card: "bg-[#282642] border border-[#514C8A]",
      chip: "bg-[#3A3764] text-[#C8C4FF]",
      accent: "bg-[#8B7CFF]",
    },
    reflection: {
      card: "bg-[#243238] border border-[#47636D]",
      chip: "bg-[#344850] text-[#C7E2EA]",
      accent: "bg-[#7DD3FC]",
    },
  };
  return styles[sessionType] || {
    card: "bg-[#1C2B33] border border-[#2a3f4a]",
    chip: "bg-[#243640] text-[#D1D5DB]",
    accent: "bg-[#58CC02]",
  };
}

function TemplatePanel({ item }: { item: StudyPlanItem }) {
  const queryClient = useQueryClient();
  const [quality, setQuality] = useState(4);
  const [notes, setNotes] = useState(item.notes || "");
  const template = item.template;
  const { data: subtopics } = useQuery({
    queryKey: ["subtopics"],
    queryFn: () => fetchSubtopics(),
    enabled: !!template,
  });
  const subtopic = matchingSubtopic(item, subtopics);

  const reviewMut = useMutation({
    mutationFn: async () => {
      await reviewTemplate(item.template_id!, quality, notes);
      await updateStudyPlanItem(item.id, { status: templateStatusForQuality(quality), notes });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      queryClient.invalidateQueries({ queryKey: ["reviewAll"] });
    },
  });

  if (!template) return null;

  return (
    <div className="mt-3 bg-[#131F24] rounded-lg p-3 space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 bg-[#0E171B] rounded-lg p-3">
        <div>
          <p className="text-xs text-[#58CC02] font-medium">Plan status</p>
          <p className="text-xs text-[#9CA3AF] mt-0.5">
            Mark this scheduled template separately from the review score.
          </p>
        </div>
        <StatusControls item={item} />
      </div>
      <div>
        <p className="text-xs text-[#58CC02] font-medium">When to use</p>
        <p className="text-sm text-[#D1D5DB] mt-1">{template.when_to_use}</p>
      </div>
      <div>
        <p className="text-xs text-[#58CC02] font-medium">Signals</p>
        <p className="text-sm text-[#D1D5DB] mt-1">{template.signals.join(", ")}</p>
      </div>
      <div>
        <p className="text-xs text-[#58CC02] font-medium">Core code</p>
        <pre className="mt-2 bg-[#0E171B] rounded-lg p-3 overflow-x-auto text-xs text-green-300 whitespace-pre">
          {template.core_code}
        </pre>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-[#FFC800] font-medium">Breakdown</p>
          <Markdown>{template.breakdown}</Markdown>
        </div>
        <div>
          <p className="text-xs text-[#FFC800] font-medium">Mental model</p>
          <Markdown>{template.mental_model}</Markdown>
        </div>
        {subtopic ? (
          <VariantSection subtopic={subtopic} variantsText={subtopic.variants} knownSubtopics={subtopics} />
        ) : (
          <div>
            <p className="text-xs text-[#FFC800] font-medium">Variants</p>
            <Markdown>{template.variants}</Markdown>
          </div>
        )}
        <div>
          <p className="text-xs text-[#FFC800] font-medium">Pitfalls</p>
          <Markdown>{template.pitfalls}</Markdown>
        </div>
      </div>
      {template.recall_tasks.length > 0 && (
        <div>
          <p className="text-xs text-[#58CC02] font-medium">Mini recall tasks</p>
          <ul className="mt-1 space-y-1">
            {template.recall_tasks.map((task, index) => (
              <li key={index} className="text-sm text-[#D1D5DB]">
                {index + 1}. {task}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-col sm:flex-row gap-2">
        <select
          value={quality}
          onChange={(e) => setQuality(Number(e.target.value))}
          className="bg-[#243640] text-white rounded-lg px-3 py-2 text-sm outline-none"
        >
          {[5, 4, 3, 2, 1, 0].map((v) => (
            <option key={v} value={v}>Quality {v}</option>
          ))}
        </select>
        <input
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Review note"
          className="flex-1 bg-[#243640] text-white rounded-lg px-3 py-2 text-sm placeholder-[#9CA3AF] outline-none"
        />
        <button
          onClick={() => reviewMut.mutate()}
          disabled={reviewMut.isPending}
          className="bg-[#58CC02] text-white rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {reviewMut.isPending ? "Saving..." : "Record review"}
        </button>
      </div>
    </div>
  );
}

type TemplateCodeSection = {
  title: string;
  code: string;
  logic: string;
};

function templateCodeSections(item: StudyPlanItem): TemplateCodeSection[] {
  const template = item.template;
  if (!template) return [];
  const lines = template.core_code.split("\n");
  const sections: TemplateCodeSection[] = [];
  let currentTitle = "Setup";
  let current: string[] = [];

  const flush = () => {
    if (current.length === 0) return;
    sections.push({
      title: currentTitle,
      code: current.join("\n").trimEnd(),
      logic: sectionLogic(template.slug, currentTitle),
    });
    current = [];
  };

  for (const line of lines) {
    const trimmed = line.trim();
    const match = trimmed.match(/^(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)/);
    if (match && current.length > 0) {
      flush();
      currentTitle = match[2].replace(/_/g, " ");
    } else if (match) {
      currentTitle = match[2].replace(/_/g, " ");
    }
    current.push(line);
  }
  flush();
  return sections.length > 0 ? sections : [{ title: "Core code", code: template.core_code, logic: template.breakdown }];
}

function sectionLogic(slug: string, title: string): string {
  const key = `${slug}:${title.toLowerCase()}`;
  const map: Record<string, string> = {
    "segment-tree:segmenttree": "Defines the reusable structure. The tree array stores interval summaries so query/update do not scan the original array.",
    "segment-tree:__init__": "Builds leaves from the input and then builds parents bottom-up. Parent nodes combine two child intervals.",
    "segment-tree:update": "Changes one leaf, then walks upward repairing exactly the ancestors whose intervals changed.",
    "segment-tree:query": "Moves two pointers inward and only consumes nodes whose intervals are fully inside the requested range.",
    "union-find:dsu": "Stores one parent pointer per node and a size array so connected components can be merged efficiently.",
    "union-find:__init__": "Starts with every node as its own component. The component count decreases only on successful union.",
    "union-find:find": "Returns the representative root. Path compression rewires nodes directly to the root for future calls.",
    "union-find:union": "Merges two roots, attaches smaller to larger, and returns whether a real merge happened.",
    "iterator-generator:flatten": "A recursive generator. `yield from` delegates nested lists while preserving lazy traversal.",
    "iterator-generator:peekingiterator": "Wraps an iterator with one-value lookahead so `peek` can inspect without consuming.",
    "iterator-generator:peek": "Loads the cache only when empty. Repeated peeks return the same value.",
    "iterator-generator:next": "Consumes the cached value if present; otherwise delegates to the underlying iterator.",
    "iterator-generator:hasnext": "Must not consume a value unless it has been cached.",
    "topological-sort:topo sort": "Builds indegrees, repeatedly removes zero-prerequisite nodes, and detects cycles by incomplete output.",
    "dijkstra:dijkstra": "Uses a heap to always expand the cheapest known state and skips stale entries.",
    "bfs:bfs": "Processes states in distance order. Marking visited before enqueue prevents duplicate work.",
  };
  return map[key] || "This block is a reusable part of the template. Know its invariant, inputs, outputs, and when it should be modified for a specific problem.";
}

function matchingSubtopic(item: StudyPlanItem, subtopics: SubtopicInfo[] | undefined): SubtopicInfo | null {
  if (!item.template || !subtopics) return null;
  const needle = (item.template.subtopic || item.template.title || "").toLowerCase();
  const title = item.template.title.toLowerCase();
  return subtopics.find((st) => {
    const name = st.name.toLowerCase();
    return name === needle || name === title || name.includes(needle) || title.includes(name);
  }) || null;
}

function templateComplexity(item: StudyPlanItem): string {
  const slug = item.template?.slug || "";
  const map: Record<string, string> = {
    "segment-tree": "**Build:** `O(n)`.\n\n**Point update:** `O(log n)` because only one root-to-leaf path changes.\n\n**Range query:** `O(log n)` because the query range is decomposed into a logarithmic number of complete stored intervals.\n\n**Space:** `O(n)` for the iterative tree, usually `2*n` slots. Recursive array implementations often allocate `4*n`.",
    "union-find": "**Find / union:** effectively `O(1)` amortized, more precisely inverse Ackermann with path compression and union by size/rank.\n\n**Space:** `O(n)` for parent and size/rank arrays.",
    "iterator-generator": "**Next:** usually `O(1)` amortized per returned value, plus traversal work needed to reach it.\n\n**Space:** depends on saved traversal state. Recursive generators use call stack depth; explicit iterators often store a stack/cache.",
    "binary-indexed-tree": "**Update / prefix query:** `O(log n)`.\n\n**Range query:** `O(log n)` by subtracting two prefix sums.\n\n**Space:** `O(n)`.",
    "trie": "**Insert/search:** `O(L)` where `L` is word length.\n\n**Space:** proportional to the total number of stored characters.",
    "monotonic-stack": "**Time:** `O(n)` because each item is pushed and popped at most once.\n\n**Space:** `O(n)` in the worst case.",
    "bfs": "**Time:** `O(V + E)` for graph traversal.\n\n**Space:** `O(V)` for queue and visited state.",
    "dijkstra": "**Time:** commonly `O((V + E) log V)` with a heap.\n\n**Space:** `O(V + E)` for graph plus distances/heap.",
    "topological-sort": "**Time:** `O(V + E)`.\n\n**Space:** `O(V + E)` for adjacency, indegrees, and queue.",
    "binary-search-answer": "**Time:** `O(log(range) * check_cost)`.\n\n**Space:** usually whatever the feasibility checker needs.",
  };
  return map[slug] || "**Time:** explain the cost of each operation the template exposes.\n\n**Space:** explain the persistent state the template stores.";
}

function RelatedQuestions({
  item,
  onSelectQuestion,
}: {
  item: StudyPlanItem;
  onSelectQuestion: (id: number) => void;
}) {
  const related = Array.isArray(item.metadata.related_questions)
    ? item.metadata.related_questions as Array<{
        id: number;
        number: number | null;
        title: string;
        difficulty: string;
        topics: string[];
        subtopics: string[];
      }>
    : [];

  if (related.length === 0) {
    return (
      <div className="bg-[#1C2B33] rounded-xl p-4">
        <p className="text-white font-medium">Apply this template</p>
        <p className="text-sm text-[#9CA3AF] mt-1">
          No matching questions are tagged yet. Add or import questions with this subtopic to tie practice back to the template.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
      <div>
        <p className="text-white font-medium">Apply this template</p>
        <p className="text-xs text-[#9CA3AF] mt-0.5">
          Same pattern, different outputs. Identify what stays fixed and what changes.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {related.map((q) => (
          <button
            key={q.id}
            onClick={() => onSelectQuestion(q.id)}
            className="text-left bg-[#243640] rounded-lg p-3 active:bg-[#2a4a56]"
          >
            <div className="flex items-center gap-2">
              {q.number && <span className="text-xs text-[#9CA3AF]">#{q.number}</span>}
              <span className={`text-xs ${difficultyColor[q.difficulty] || "text-gray-400"}`}>
                {q.difficulty}
              </span>
            </div>
            <p className="text-sm text-white font-medium truncate mt-1">{q.title}</p>
            <p className="text-xs text-[#9CA3AF] mt-1 line-clamp-2">
              Replace the result logic while keeping the recognition pattern and core invariant.
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

const TEMPLATE_TABS = [
  { key: "concept" as const, label: "Understand", color: "#58CC02" },
  { key: "signals" as const, label: "Recognize", color: "#FFC800" },
  { key: "code" as const, label: "Implement", color: "#818CF8" },
  { key: "practice" as const, label: "Practice", color: "#38BDF8" },
];

type TemplateTab = (typeof TEMPLATE_TABS)[number]["key"];

function TemplateStudyDeck({
  items,
  onSelectQuestion,
}: {
  items: StudyPlanItem[];
  onSelectQuestion: (id: number) => void;
}) {
  const queryClient = useQueryClient();
  const templateItems = items.filter((item) => item.item_type === "template" && item.template && item.status !== "skipped");
  const [activeIndex, setActiveIndex] = useState(0);
  const [activeTab, setActiveTab] = useState<TemplateTab>("concept");
  const [mode, setMode] = useState<"explain" | "fill">("fill");
  const [revealedByItem, setRevealedByItem] = useState<Record<number, number>>({});
  const [doneSectionsByItem, setDoneSectionsByItem] = useState<Record<number, Record<number, boolean>>>({});
  const { data: subtopics } = useQuery({
    queryKey: ["subtopics"],
    queryFn: () => fetchSubtopics(),
  });
  const addTemplatesMut = useMutation({
    mutationFn: () => addTemplates(3),
    onSuccess: (data) => {
      const updatedSession = data.sessions.find((session) => session.session_type === "template_review");
      const updatedTemplates = updatedSession?.items.filter((item) => item.item_type === "template" && item.template && item.status !== "skipped") || [];
      queryClient.setQueryData(["studyPlan"], data);
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
      if (updatedTemplates.length > templateItems.length) {
        setActiveIndex(templateItems.length);
        setActiveTab("concept");
      }
    },
  });
  const active = templateItems[Math.min(activeIndex, Math.max(templateItems.length - 1, 0))];
  const template = active?.template;
  const sections = active ? templateCodeSections(active) : [];
  const subtopic = active ? matchingSubtopic(active, subtopics) : null;
  const revealedCount = active ? revealedByItem[active.id] || 0 : 0;
  const visibleSections = sections.slice(0, revealedCount);
  const doneSections = active ? doneSectionsByItem[active.id] || {} : {};
  const allRevealed = sections.length > 0 && revealedCount >= sections.length;
  const allFillableTouched =
    allRevealed &&
    sections.every((section, index) => fillableLineIndexes(section.code).length === 0 || doneSections[index]);
  const statusMut = useMutation({
    mutationFn: ({ itemId, status }: { itemId: number; status: StudyPlanItem["status"] }) =>
      updateStudyPlanItem(itemId, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      queryClient.invalidateQueries({ queryKey: ["reviewAll"] });
    },
  });
  const skipMut = useMutation({
    mutationFn: () => skipAndReplaceTemplate(active!.id),
    onSuccess: (data) => {
      const updatedSession = data.sessions.find((session) => session.session_type === "template_review");
      const updatedTemplates = updatedSession?.items.filter((item) => item.item_type === "template" && item.template && item.status !== "skipped") || [];
      queryClient.setQueryData(["studyPlan"], data);
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
      setActiveIndex(Math.max(0, updatedTemplates.length - 1));
      setActiveTab("concept");
    },
  });

  const setTemplateTab = (tab: TemplateTab) => {
    setActiveTab(tab);
    if (active && tab !== "concept" && active.status !== "completed") {
      statusMut.mutate({ itemId: active.id, status: "in_progress" });
    }
  };

  useEffect(() => {
    if (!active || !sections.length || !allFillableTouched || active.status === "completed") return;
    statusMut.mutate({ itemId: active.id, status: "completed" });
  }, [active?.id, active?.status, allFillableTouched, sections.length]);

  if (!active || !template) {
    return (
      <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
        <p className="text-sm text-[#9CA3AF]">No templates scheduled for this block.</p>
        <button
          onClick={() => addTemplatesMut.mutate()}
          disabled={addTemplatesMut.isPending}
          className="w-full bg-[#58CC02] text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-50"
        >
          {addTemplatesMut.isPending ? "Adding..." : "Add templates"}
        </button>
        {addTemplatesMut.isError && (
          <p className="text-xs text-[#FF8A8A]">{(addTemplatesMut.error as Error).message}</p>
        )}
      </div>
    );
  }

  const revealNextSection = () => {
    setRevealedByItem((prev) => ({
      ...prev,
      [active.id]: Math.min(sections.length, (prev[active.id] || 0) + 1),
    }));
  };

  const hideCurrentTemplate = () => {
    setRevealedByItem((prev) => ({ ...prev, [active.id]: 0 }));
    setDoneSectionsByItem((prev) => ({ ...prev, [active.id]: {} }));
  };

  const markRework = () => {
    setRevealedByItem((prev) => ({ ...prev, [active.id]: 0 }));
    setDoneSectionsByItem((prev) => ({ ...prev, [active.id]: {} }));
    setActiveTab("concept");
    statusMut.mutate({ itemId: active.id, status: "rework" });
  };

  const handleSectionStatus = (index: number, status: "in_progress" | "done") => {
    if (!active) return;
    setDoneSectionsByItem((prev) => {
      const current = prev[active.id] || {};
      return {
        ...prev,
        [active.id]: {
          ...current,
          [index]: status === "done",
        },
      };
    });
    if (status === "in_progress" && active.status === "not_started") {
      statusMut.mutate({ itemId: active.id, status: "in_progress" });
    }
  };

  return (
    <div className="space-y-4">
      {/* Template picker */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {templateItems.map((item, index) => (
          <button
            key={item.id}
            onClick={() => { setActiveIndex(index); setActiveTab("concept"); }}
            className={`shrink-0 rounded-full px-3 py-2 text-xs font-medium ${
              index === activeIndex
                ? "bg-[#58CC02] text-white"
                : "bg-[#1C2B33] text-[#D1D5DB] border border-[#2a3f4a]"
            }`}
          >
            {item.title}
          </button>
        ))}
      </div>

      {/* Header */}
      <div className="bg-[#1C2B33] rounded-xl p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-[#58CC02] font-medium">
              Template {activeIndex + 1} of {templateItems.length}
            </p>
            <h3 className="text-white text-xl font-bold mt-1">{template.title}</h3>
          </div>
          <div className="flex flex-col items-end gap-2">
            <span className={`text-xs rounded-full px-2 py-1 ${
              active.status === "completed"
                ? "bg-[#58CC02]/20 text-[#7DEB35]"
                : active.status === "in_progress"
                  ? "bg-[#FFC800]/20 text-[#FFE08A]"
                  : active.status === "rework"
                    ? "bg-[#FF4B4B]/20 text-[#FF8A8A]"
                    : "bg-[#243640] text-[#9CA3AF]"
            }`}>
              {active.status.replace("_", " ")}
            </span>
            {active.status !== "completed" && (
              <button
                onClick={() => skipMut.mutate()}
                disabled={skipMut.isPending}
                className="text-xs text-[#D1D5DB] bg-[#243640] rounded-lg px-3 py-1.5 disabled:opacity-50"
              >
                {skipMut.isPending ? "Skipping..." : "Skip"}
              </button>
            )}
            {active.status === "completed" && (
              <button
                onClick={markRework}
                disabled={statusMut.isPending}
                className="text-xs text-[#FF8A8A] bg-[#332026] rounded-lg px-3 py-1.5 disabled:opacity-50"
              >
                Rework
              </button>
            )}
          </div>
        </div>
        {skipMut.isError && (
          <p className="text-xs text-[#FF8A8A] mt-3">{(skipMut.error as Error).message}</p>
        )}
      </div>

      {/* Tab bar — consistent with SubtopicBrowser */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {TEMPLATE_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setTemplateTab(tab.key)}
            className={`shrink-0 rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${
              activeTab === tab.key ? "" : "bg-[#1C2B33] text-[#9CA3AF]"
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

      {/* ── Understand tab ──────────────────────────────────── */}
      {activeTab === "concept" && (
        <div className="space-y-4">
          <div className="bg-[#1E3328] border border-[#2F6B46] rounded-xl p-5">
            <h3 className="text-[#58CC02] font-bold text-xs uppercase tracking-wide mb-3">
              Core Idea
            </h3>
            <div className="text-white text-base leading-relaxed">
              <Markdown>{subtopic?.description || template.when_to_use}</Markdown>
            </div>
          </div>

          {(subtopic?.when_to_use || template.mental_model) && (
            <div className="bg-[#302B1E] border border-[#6B5A2F] rounded-xl p-5">
              <h3 className="text-[#FFC800] font-bold text-xs uppercase tracking-wide mb-3">
                When to Reach for This
              </h3>
              <div className="text-[#D1D5DB] text-sm leading-relaxed">
                <Markdown>{subtopic?.when_to_use || template.mental_model}</Markdown>
              </div>
            </div>
          )}

          <button
            onClick={() => setTemplateTab("signals")}
            className="w-full bg-[#58CC02] text-white rounded-xl py-3 text-sm font-semibold"
          >
            Next: Learn to recognize this pattern
          </button>
        </div>
      )}

      {/* ── Recognize tab ───────────────────────────────────── */}
      {activeTab === "signals" && (
        <div className="space-y-4">
          <div className="bg-[#1C2B33] rounded-xl p-5 space-y-4">
            <div>
              <h3 className="text-[#FFC800] font-bold text-xs uppercase tracking-wide mb-1">
                Pattern Triggers
              </h3>
              <p className="text-sm text-[#9CA3AF]">
                When you spot these clues, think: <span className="text-white font-medium">{template.title}</span>
              </p>
            </div>
            <div className="space-y-2">
              {template.signals.map((signal, i) => (
                <div
                  key={i}
                  className="bg-[#FFC800]/5 border border-[#FFC800]/20 rounded-lg p-3 flex items-start gap-3"
                >
                  <span className="shrink-0 w-6 h-6 rounded-full bg-[#FFC800]/20 text-[#FFC800] text-xs font-bold flex items-center justify-center mt-0.5">
                    {i + 1}
                  </span>
                  <p className="text-sm text-[#FFE08A]">{signal}</p>
                </div>
              ))}
            </div>
          </div>

          {template.mental_model && (
            <div className="bg-[#302B1E] border border-[#6B5A2F] rounded-xl p-5">
              <h3 className="text-[#FFC800] font-bold text-xs uppercase tracking-wide mb-3">
                Mental Model
              </h3>
              <div className="text-[#D1D5DB] text-sm leading-relaxed">
                <Markdown>{template.mental_model}</Markdown>
              </div>
            </div>
          )}

          {/* Complexity */}
          <div className="bg-[#131F24] border border-[#2a3f4a] rounded-xl p-4">
            <h3 className="text-[#D1D5DB] font-bold text-xs uppercase tracking-wide mb-2">
              Time &amp; Space
            </h3>
            <div className="text-sm text-[#9CA3AF]">
              <Markdown>{templateComplexity(active)}</Markdown>
            </div>
          </div>

          <button
            onClick={() => setTemplateTab("code")}
            className="w-full bg-[#FFC800] text-[#131F24] rounded-xl py-3 text-sm font-semibold"
          >
            Next: Study the code
          </button>
        </div>
      )}

      {/* ── Implement tab ───────────────────────────────────── */}
      {activeTab === "code" && (
        <div className="space-y-3">
          {active.status === "completed" && (
            <div className="bg-[#1E3328] border border-[#2F6B46] rounded-xl p-4 flex items-center gap-3">
              <span className="text-[#58CC02] text-lg">✓</span>
              <div>
                <p className="text-[#7DEB35] font-semibold text-sm">Completed</p>
                <p className="text-xs text-[#9CA3AF]">You can review in read mode or rework from the header.</p>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between">
            <div className="flex rounded-lg overflow-hidden border border-[#2a3f4a]">
              {active.status !== "completed" && (
                <button
                  onClick={() => setMode("fill")}
                  className={`px-3 py-2 text-xs ${mode === "fill" ? "bg-[#818CF8] text-white" : "bg-[#243640] text-[#D1D5DB]"}`}
                >
                  Fill in
                </button>
              )}
              <button
                onClick={() => setMode("explain")}
                className={`px-3 py-2 text-xs ${mode === "explain" || active.status === "completed" ? "bg-[#818CF8] text-white" : "bg-[#243640] text-[#D1D5DB]"}`}
              >
                Read
              </button>
            </div>
            <span className="text-xs text-[#9CA3AF]">
              {active.status === "completed" ? sections.length : revealedCount}/{sections.length} sections
            </span>
          </div>

          <div className="h-1.5 rounded-full bg-[#243640] overflow-hidden">
            <div
              className={`h-full transition-all ${active.status === "completed" ? "bg-[#58CC02]" : "bg-[#818CF8]"}`}
              style={{ width: `${sections.length > 0 ? ((active.status === "completed" ? sections.length : revealedCount) / sections.length) * 100 : 0}%` }}
            />
          </div>

          {active.status === "completed" ? (
            <>
              {sections.map((section, index) => (
                <div key={`${section.title}-${index}`} className="bg-[#1C2B33] rounded-xl overflow-hidden">
                  <div className="p-4 border-b border-[#2a3f4a]">
                    <p className="text-white font-semibold">{index + 1}. {section.title}</p>
                    <p className="text-sm text-[#D1D5DB] mt-1">{section.logic}</p>
                  </div>
                  <pre className="bg-[#0E171B] p-4 overflow-x-auto text-xs text-green-300 whitespace-pre min-h-28">
                    {section.code}
                  </pre>
                </div>
              ))}
            </>
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                {sections.map((section, index) => (
                  <button
                    key={`${section.title}-${index}`}
                    onClick={() =>
                      setRevealedByItem((prev) => ({
                        ...prev,
                        [active.id]: Math.max(prev[active.id] || 0, index + 1),
                      }))
                    }
                    className={`text-xs rounded-full px-2 py-1 ${
                      index < revealedCount
                        ? "bg-[#818CF8]/20 text-[#C8C4FF]"
                        : "bg-[#243640] text-[#9CA3AF]"
                    }`}
                  >
                    {index + 1}. {section.title}
                  </button>
                ))}
              </div>

              {revealedCount === 0 && (
                <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3 text-center">
                  <p className="text-white font-semibold">Start with the first code block</p>
                  <p className="text-sm text-[#9CA3AF]">
                    Reveal one section, try to recall the hidden lines, then move to the next.
                  </p>
                  <button
                    onClick={revealNextSection}
                    className="bg-[#818CF8] text-white rounded-lg px-4 py-2 text-sm font-semibold"
                  >
                    Reveal section 1
                  </button>
                </div>
              )}

              {visibleSections.map((section, index) => (
                <div key={`${section.title}-${index}`} className="bg-[#1C2B33] rounded-xl overflow-hidden">
                  <div className="p-4 border-b border-[#2a3f4a]">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-white font-semibold">{index + 1}. {section.title}</p>
                        <p className="text-sm text-[#D1D5DB] mt-1">{section.logic}</p>
                      </div>
                      <span className="text-xs rounded-full px-2 py-1 bg-[#818CF8]/20 text-[#C8C4FF] shrink-0">
                        Revealed
                      </span>
                    </div>
                  </div>
                  {mode === "fill" ? (
                    <FillableCodeBlock
                      key={`${active.id}-${index}`}
                      code={section.code}
                      subtopicId={subtopic?.id || template?.id}
                      subtopicName={subtopic?.name || template?.subtopic || undefined}
                      onStatusChange={(status) => handleSectionStatus(index, status)}
                    />
                  ) : (
                    <pre className="bg-[#0E171B] p-4 overflow-x-auto text-xs text-green-300 whitespace-pre min-h-28">
                      {section.code}
                    </pre>
                  )}
                </div>
              ))}

              {revealedCount > 0 && revealedCount < sections.length && (
                <button
                  onClick={revealNextSection}
                  className="w-full bg-[#818CF8] text-white rounded-xl py-3 text-sm font-semibold"
                >
                  Reveal next section ({revealedCount + 1}/{sections.length})
                </button>
              )}

              {revealedCount > 0 && (
                <button
                  onClick={hideCurrentTemplate}
                  className="w-full bg-[#243640] text-[#D1D5DB] rounded-xl py-2.5 text-sm"
                >
                  Hide sections and restart recall
                </button>
              )}

              {revealedCount >= sections.length && (
                <div className="space-y-3">
                  {subtopic ? (
                    <VariantSection subtopic={subtopic} variantsText={subtopic.variants} knownSubtopics={subtopics} />
                  ) : (
                    template.variants && (
                      <div className="bg-[#1C2B33] rounded-xl p-4">
                        <h3 className="text-[#818CF8] font-bold text-xs uppercase tracking-wide mb-2">
                          Variants
                        </h3>
                        <Markdown>{template.variants}</Markdown>
                      </div>
                    )
                  )}
                  <div className="bg-[#372329] border border-[#7A3B4B] rounded-xl p-4">
                    <h3 className="text-[#FF8A8A] font-bold text-xs uppercase tracking-wide mb-2">
                      Common Pitfalls
                    </h3>
                    <Markdown>{subtopic?.common_pitfalls || template.pitfalls}</Markdown>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Practice tab ────────────────────────────────────── */}
      {activeTab === "practice" && (
        <div className="space-y-4">
          {template.recall_tasks.length > 0 && (
            <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
              <h3 className="text-[#38BDF8] font-bold text-xs uppercase tracking-wide">
                Recall Tasks
              </h3>
              <p className="text-xs text-[#9CA3AF]">
                Can you answer these without looking at the code?
              </p>
              <div className="space-y-2">
                {template.recall_tasks.map((task, i) => (
                  <div key={i} className="bg-[#131F24] border border-[#2a3f4a] rounded-lg p-3 flex items-start gap-3">
                    <span className="shrink-0 w-6 h-6 rounded-full bg-[#38BDF8]/20 text-[#38BDF8] text-xs font-bold flex items-center justify-center mt-0.5">
                      {i + 1}
                    </span>
                    <p className="text-sm text-[#D1D5DB]">{task}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <RelatedQuestions item={active} onSelectQuestion={onSelectQuestion} />

          {active.status === "completed" && (
            <button
              onClick={markRework}
              disabled={statusMut.isPending}
              className="w-full bg-[#332026] text-[#FF8A8A] rounded-xl py-3 text-sm font-semibold disabled:opacity-50"
            >
              Rework
            </button>
          )}
        </div>
      )}

      {/* Previous / Next navigation */}
      <div className="flex gap-2">
        <button
          onClick={() => { setActiveIndex((i) => Math.max(0, i - 1)); setActiveTab("concept"); }}
          disabled={activeIndex === 0}
          className="flex-1 bg-[#243640] text-white rounded-lg py-2.5 text-sm disabled:opacity-40"
        >
          Previous template
        </button>
        {activeIndex >= templateItems.length - 1 ? (
          <button
            onClick={() => addTemplatesMut.mutate()}
            disabled={addTemplatesMut.isPending}
            className="flex-1 bg-[#58CC02] text-white rounded-lg py-2.5 text-sm disabled:opacity-50"
          >
            {addTemplatesMut.isPending ? "Adding..." : "More templates"}
          </button>
        ) : (
          <button
            onClick={() => { setActiveIndex((i) => Math.min(templateItems.length - 1, i + 1)); setActiveTab("concept"); }}
            className="flex-1 bg-[#58CC02] text-white rounded-lg py-2.5 text-sm"
          >
            Next template
          </button>
        )}
      </div>
      {addTemplatesMut.isError && (
        <p className="text-xs text-[#FF8A8A]">{(addTemplatesMut.error as Error).message}</p>
      )}
    </div>
  );
}

function PlanItemCard({
  item,
  onSelectQuestion,
}: {
  item: StudyPlanItem;
  onSelectQuestion: (id: number) => void;
}) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const difficulty = String(item.metadata.difficulty || "");
  const number = item.metadata.number as number | undefined;
  const topics = Array.isArray(item.metadata.topics) ? item.metadata.topics.map(String) : [];
  const subtopics = Array.isArray(item.metadata.subtopics) ? item.metadata.subtopics.map(String) : [];

  const pinMut = useMutation({
    mutationFn: () => updateStudyPlanItem(item.id, { pinned: !item.pinned }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["studyPlan"] }),
  });

  const openItem = () => {
    if (item.status === "not_started") {
      updateStudyPlanItem(item.id, { status: "in_progress" }).then(() =>
        queryClient.invalidateQueries({ queryKey: ["studyPlan"] }),
      );
    }
    if (item.question_id) onSelectQuestion(item.question_id);
    else setExpanded((v) => !v);
  };

  const statusDot = item.status === "completed" ? "bg-[#58CC02]"
    : item.status === "in_progress" ? "bg-[#FFC800]"
    : item.status === "rework" ? "bg-[#FF4B4B]"
    : "bg-[#9CA3AF]/40";

  return (
    <div className={`bg-[#1C2B33] rounded-xl p-3 ${item.status === "completed" ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-2">
        <span className={`w-2 h-2 rounded-full shrink-0 mt-2 ${statusDot}`} />
        <button onClick={openItem} className="flex-1 text-left min-w-0 active:opacity-80">
          <div className="flex items-center gap-2 flex-wrap">
            {number && <span className="text-xs text-[#9CA3AF]">#{number}</span>}
            {difficulty && (
              <span className={`text-xs font-medium ${difficultyColor[difficulty] || "text-gray-400"}`}>
                {difficulty}
              </span>
            )}
          </div>
          <p className="text-white font-medium truncate mt-0.5">{item.title}</p>
          {(topics.length > 0 || subtopics.length > 0) && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {topics.map((t) => (
                <span key={t} className="text-[10px] bg-[#58CC02]/15 text-[#7DEB35] rounded-full px-2 py-0.5">{t}</span>
              ))}
              {subtopics.map((st) => (
                <span key={st} className="text-[10px] bg-[#818CF8]/15 text-[#A5B4FC] rounded-full px-2 py-0.5">{st}</span>
              ))}
            </div>
          )}
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); pinMut.mutate(); }}
          disabled={pinMut.isPending}
          className="shrink-0 mt-1 text-lg leading-none disabled:opacity-50"
        >
          {item.pinned ? <span className="text-[#FFC800]">★</span> : <span className="text-[#9CA3AF]/50">☆</span>}
        </button>
      </div>
      {expanded && item.item_type === "template" && (
        <div onClick={(e) => e.stopPropagation()}>
          <TemplatePanel item={item} />
        </div>
      )}
    </div>
  );
}

function SessionSummaryCard({
  session,
  onOpen,
  variant = "card",
}: {
  session: StudyPlanSession;
  onOpen: () => void;
  variant?: "card" | "row";
}) {
  const { total, completed } = sessionStats(session);
  const colors = sessionCardClasses(session.session_type);
  const visibleItems = session.items.filter((item) => item.status !== "skipped").slice(0, 3);

  if (variant === "row") {
    return (
      <button
        onClick={onOpen}
        className={`w-full text-left rounded-2xl p-3 transition-colors relative overflow-hidden flex items-center gap-2 ${colors.card}`}
      >
        <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${colors.accent}`} />
        <div className="min-w-0 flex-1">
          <h3 className="text-white font-semibold text-sm leading-tight">{sessionDisplayTitle(session)}</h3>
          <p className="text-[10px] text-[#9CA3AF] mt-0.5">
            {completed}/{total}
          </p>
        </div>
        <span className="text-[#9CA3AF] text-sm shrink-0">&rsaquo;</span>
      </button>
    );
  }

  return (
    <button
      onClick={onOpen}
      className={`w-full aspect-[1.12] text-left rounded-2xl p-2.5 sm:p-4 lg:p-5 transition-colors flex flex-col justify-between relative overflow-hidden ${colors.card}`}
    >
      <span className={`absolute left-2.5 top-2.5 sm:left-4 sm:top-4 h-1.5 w-1.5 sm:h-2 sm:w-2 rounded-full ${colors.accent}`} />
      <span className="absolute right-2.5 top-2 sm:right-4 sm:top-3 text-[#9CA3AF] text-sm sm:text-xl">&rsaquo;</span>
      <div className="pt-3.5 sm:pt-5">
        <h3 className="text-white font-semibold text-xs sm:text-lg lg:text-xl leading-tight pr-4">
          {sessionDisplayTitle(session)}
        </h3>
        <p className="text-[10px] sm:text-sm text-[#9CA3AF] mt-0.5 sm:mt-1">
          {completed}/{total}
        </p>
      </div>
      <div className="hidden sm:flex flex-wrap gap-1.5 mt-3">
        {visibleItems.map((item) => (
          <span
            key={item.id}
            className={`max-w-full truncate rounded-full px-2 py-1 text-[10px] lg:text-xs ${colors.chip}`}
          >
            {item.title}
          </span>
        ))}
      </div>
    </button>
  );
}

function reviewUrgency(nextReview: string | null): { label: string; cls: string } {
  if (!nextReview) return { label: "Available now", cls: "bg-[#38BDF8]/15 text-[#7DD3FC]" };
  const now = new Date();
  const due = new Date(nextReview);
  const diffMs = due.getTime() - now.getTime();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays < 0) {
    const overdue = Math.abs(diffDays);
    return { label: `Overdue ${overdue}d`, cls: "bg-[#FF4B4B]/20 text-[#FF8A8A]" };
  }
  if (diffDays === 0) return { label: "Due today", cls: "bg-[#FFC800]/20 text-[#FFE08A]" };
  if (diffDays === 1) return { label: "Due tomorrow", cls: "bg-[#FFC800]/15 text-[#FFE08A]" };
  if (diffDays <= 7) return { label: `In ${diffDays}d`, cls: "bg-[#38BDF8]/15 text-[#7DD3FC]" };
  return { label: `In ${diffDays}d`, cls: "bg-[#243640] text-[#9CA3AF]" };
}

function isDueForReview(nextReview: string | null): boolean {
  if (!nextReview) return true;
  const due = new Date(nextReview);
  const endOfToday = new Date();
  endOfToday.setHours(23, 59, 59, 999);
  return due.getTime() <= endOfToday.getTime();
}

function ReviewList({
  onSelectQuestion,
  dueOnly = false,
}: {
  onSelectQuestion: (id: number) => void;
  dueOnly?: boolean;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["reviewAll"],
    queryFn: fetchAllCompleted,
  });
  const { data: templates } = useQuery({
    queryKey: ["templates"],
    queryFn: fetchTemplates,
  });

  if (isLoading) return <p className="text-sm text-[#9CA3AF]">Loading...</p>;
  const visibleItems = (data?.items || []).filter((item) => !dueOnly || isDueForReview(item.next_review));
  if (!data || visibleItems.length === 0) {
    return (
      <p className="text-sm text-[#9CA3AF] bg-[#1C2B33] rounded-xl p-4">
        {dueOnly ? "No scheduled review items due right now." : "No review items yet."}
      </p>
    );
  }

  const groups: Array<{ type: ReviewItem["review_type"]; title: string; empty: string }> = [
    { type: "question", title: "Questions", empty: dueOnly ? "No questions due." : "No completed questions yet." },
    { type: "template", title: "Templates", empty: dueOnly ? "No templates due." : "No template reviews yet." },
    { type: "pattern_drill", title: "Pattern Drills", empty: dueOnly ? "No pattern drills due." : "No completed pattern drills yet." },
  ];

  const itemsByType = visibleItems.reduce<Record<ReviewItem["review_type"], ReviewItem[]>>(
    (acc, item) => {
      acc[item.review_type].push(item);
      return acc;
    },
    { question: [], template: [], pattern_drill: [] },
  );

  return (
    <div className="space-y-4">
      {groups.map((group) => {
        const groupItems = itemsByType[group.type];
        return (
          <section key={group.type} className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">{group.title}</h3>
              <span className="text-xs text-[#9CA3AF]">{groupItems.length}</span>
            </div>
            {groupItems.length === 0 ? (
              <p className="text-xs text-[#9CA3AF] bg-[#1C2B33] rounded-xl p-3">{group.empty}</p>
            ) : (
              groupItems.map((item: ReviewItem) => {
                const urgency = reviewUrgency(item.next_review);
                const template = item.template_id
                  ? templates?.find((t) => t.id === item.template_id)
                  : null;
                const canOpenQuestion = item.question_id != null;
                return (
                  <button
                    key={`${item.review_type}-${item.id}`}
                    onClick={() => {
                      if (canOpenQuestion) onSelectQuestion(item.question_id!);
                    }}
                    className="w-full text-left bg-[#1C2B33] rounded-xl p-3 active:bg-[#243640]"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 flex-wrap min-w-0">
                        {item.number && <span className="text-xs text-[#9CA3AF]">#{item.number}</span>}
                        {item.difficulty && (
                          <span className={`text-xs font-medium ${difficultyColor[item.difficulty] || "text-gray-400"}`}>
                            {item.difficulty}
                          </span>
                        )}
                        <span className={`text-[10px] rounded-full px-2 py-0.5 ${
                          item.status === "rework" ? "bg-[#FF4B4B]/20 text-[#FF8A8A]"
                          : item.status === "done" || item.status === "completed" ? "bg-[#58CC02]/20 text-[#7DEB35]"
                          : "bg-[#334B59] text-[#BFE8FF]"
                        }`}>
                          {item.status}
                        </span>
                      </div>
                      <span className={`shrink-0 text-[10px] font-semibold rounded-full px-2 py-0.5 ${urgency.cls}`}>
                        {urgency.label}
                      </span>
                    </div>
                    <p className="text-white font-medium truncate mt-0.5">{item.title}</p>
                    {template?.when_to_use && (
                      <p className="text-xs text-[#9CA3AF] line-clamp-2 mt-1">{template.when_to_use}</p>
                    )}
                    {(item.topics.length > 0 || item.subtopics.length > 0) && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {item.topics.map((t) => (
                          <span key={t} className="text-[10px] bg-[#58CC02]/15 text-[#7DEB35] rounded-full px-2 py-0.5">{t}</span>
                        ))}
                        {item.subtopics.map((st) => (
                          <span key={st} className="text-[10px] bg-[#818CF8]/15 text-[#A5B4FC] rounded-full px-2 py-0.5">{st}</span>
                        ))}
                      </div>
                    )}
                    {item.next_review && (
                      <p className="text-[10px] text-[#9CA3AF] mt-1">
                        {new Date(item.next_review).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
                        {item.last_reviewed && (
                          <> · last reviewed {new Date(item.last_reviewed).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</>
                        )}
                      </p>
                    )}
                  </button>
                );
              })
            )}
          </section>
        );
      })}
    </div>
  );
}

function SessionDetailPage({
  session,
  onBack,
  onSelectQuestion,
}: {
  session: StudyPlanSession;
  onBack: () => void;
  onSelectQuestion: (id: number) => void;
}) {
  const { total, completed } = sessionStats(session);
  const [reviewFilter, setReviewFilter] = useState<"scheduled" | "quiz" | "all">("scheduled");
  const queryClient = useQueryClient();
  const addDrillsMut = useMutation({
    mutationFn: () => addPatternDrills(5),
    onSuccess: (data) => {
      queryClient.setQueryData(["studyPlan"], data);
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
      queryClient.invalidateQueries({ queryKey: ["patternDeck"] });
    },
  });

  return (
    <div className="space-y-4">
      <div className="sticky top-0 z-20 -mx-4 px-4 py-3 bg-[#131F24]/95 backdrop-blur border-b border-[#2a3f4a]">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={onBack}
              aria-label="Back to study"
              className="w-9 h-9 rounded-lg bg-[#1C2B33] text-white flex items-center justify-center active:bg-[#243640] shrink-0"
            >
              &larr;
            </button>
            <div className="min-w-0">
              <p className="text-xs text-[#9CA3AF]">Study details</p>
              <h2 className="text-white font-bold truncate">{sessionDisplayTitle(session)}</h2>
            </div>
          </div>
          <span className="shrink-0 text-xs bg-[#243640] text-[#58CC02] rounded-full px-2.5 py-1 font-semibold">
            {completed}/{total} complete
          </span>
        </div>
      </div>

      {session.session_type === "review" && (
        <div className="flex rounded-lg overflow-hidden border border-[#2a3f4a]">
          {(["scheduled", "quiz", "all"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setReviewFilter(tab)}
              className={`flex-1 px-3 py-2 text-xs font-semibold ${
                reviewFilter === tab ? "bg-[#38BDF8]/20 text-[#38BDF8]" : "bg-[#1C2B33] text-[#9CA3AF]"
              }`}
            >
              {tab === "scheduled" ? "Scheduled" : tab === "quiz" ? "Review Quiz" : "All Completed"}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {session.session_type === "review" && reviewFilter === "quiz" ? (
          <ReviewQuizSession onSelectQuestion={onSelectQuestion} />
        ) : session.session_type === "review" && reviewFilter === "all" ? (
          <ReviewList onSelectQuestion={onSelectQuestion} />
        ) : session.session_type === "review" && reviewFilter === "scheduled" ? (
          <ReviewList onSelectQuestion={onSelectQuestion} dueOnly />
        ) : session.session_type === "template_review" ? (
          <TemplateStudyDeck items={session.items} onSelectQuestion={onSelectQuestion} />
        ) : session.items.length === 0 ? (
          <div className="bg-[#1C2B33] rounded-xl p-4 text-sm text-[#9CA3AF]">
            No items scheduled for this block.
          </div>
        ) : session.session_type === "pattern_drill" ? (
          <PatternDrillDeck
            cards={session.items
              .filter((item) => item.question_id)
              .map((item) => ({
                questionId: item.question_id!,
                completed: item.status === "completed",
                onStatusChange: async (status: "in_progress" | "completed" | "rework") => {
                  await updateStudyPlanItem(item.id, { status });
                },
              }))}
            onSelectQuestion={onSelectQuestion}
            onGenerateMore={() => addDrillsMut.mutate()}
            isGenerating={addDrillsMut.isPending}
            generateError={addDrillsMut.isError ? (addDrillsMut.error as Error).message : undefined}
          />
        ) : (
          session.items.map((item) => (
            <PlanItemCard key={item.id} item={item} onSelectQuestion={onSelectQuestion} />
          ))
        )}
      </div>
    </div>
  );
}

export function DailyPlan({
  onSelectQuestion,
  onDetailModeChange,
}: {
  onSelectQuestion: (id: number) => void;
  onDetailModeChange?: (active: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const { data: plan, isLoading, isError, error } = useQuery({
    queryKey: ["studyPlan"],
    queryFn: fetchStudyPlan,
  });

  const regenMut = useMutation({
    mutationFn: regenerateStudyPlan,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });

  const selectedSession = plan?.sessions.find((session) => session.id === selectedSessionId) || null;

  useEffect(() => {
    onDetailModeChange?.(!!selectedSession);
    return () => onDetailModeChange?.(false);
  }, [onDetailModeChange, selectedSession]);

  if (isLoading) {
    return <div className="text-center text-[#9CA3AF]">Loading dynamic study plan...</div>;
  }

  if (isError) {
    return <div className="text-red-400 text-sm">{(error as Error).message}</div>;
  }

  if (!plan) return null;

  if (selectedSession) {
    return (
      <SessionDetailPage
        session={selectedSession}
        onBack={() => setSelectedSessionId(null)}
        onSelectQuestion={onSelectQuestion}
      />
    );
  }

  const totalItems = plan.sessions.reduce((sum, session) => sum + session.items.length, 0);
  const completed = plan.sessions.reduce(
    (sum, session) => sum + session.items.filter((item) => item.status === "completed").length,
    0
  );

  // Review gets its own full-width row; the three study sessions sit at the top.
  const reviewSession = plan.sessions.find((session) => session.session_type === "review") || null;
  const topSessions = plan.sessions.filter((session) => session.session_type !== "review");

  return (
    <div className="space-y-3">
      <div className="bg-[#1C2B33] rounded-lg p-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h2 className="text-white font-bold">Today's Plan</h2>
            <p className="text-xs text-[#9CA3AF] mt-1">
              {completed}/{totalItems} complete
            </p>
          </div>
          <button
            onClick={() => regenMut.mutate()}
            disabled={regenMut.isPending}
            className="bg-[#58CC02] text-white rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-50"
          >
            {regenMut.isPending ? "Regenerating..." : "Regenerate remaining plan"}
          </button>
        </div>
        {regenMut.isError && (
          <p className="text-xs text-red-400 mt-2">{(regenMut.error as Error).message}</p>
        )}
      </div>

      <section className="space-y-2">
        <div>
          <h3 className="text-white font-semibold text-sm">Today's sessions</h3>
          <p className="text-xs text-[#9CA3AF] mt-0.5">
            Templates, New Questions, and pattern work.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {topSessions.map((session) => (
            <SessionSummaryCard
              key={session.id}
              session={session}
              onOpen={() => setSelectedSessionId(session.id)}
            />
          ))}
        </div>
      </section>

      {reviewSession && (
        <section className="space-y-2">
          <h3 className="text-white font-semibold text-sm">Review</h3>
          <SessionSummaryCard
            session={reviewSession}
            onOpen={() => setSelectedSessionId(reviewSession.id)}
            variant="row"
          />
        </section>
      )}

    </div>
  );
}
