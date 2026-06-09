import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchQuestion, updateQuestion, setQuestionStatus } from "../../api/questions";
import { fetchSolutions, generateSolutions } from "../../api/solutions";
import { createSubtopic, fetchTopicOrder, fetchSubtopics, regenerateSubtopicDescription } from "../../api/subtopics";
import { addTemplates, fetchAllCompleted, fetchTemplates } from "../../api/studyPlan";
import { SolveView } from "./SolveView";
import { Markdown } from "../ui/Markdown";
import type { Status, ExampleItem, SourceTag, SubtopicInfo, StudyPlan } from "../../types";

function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
  titleColor = "text-[#9CA3AF]",
  badge,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  titleColor?: string;
  badge?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="w-full text-left flex items-center gap-2 py-1"
      >
        <span className="text-[#9CA3AF] text-xs w-4">{open ? "▾" : "▸"}</span>
        <span className={`text-sm font-medium ${titleColor}`}>{title}</span>
        {badge}
      </button>
      {open && <div className="pl-6 pt-1">{children}</div>}
    </div>
  );
}

function ExamplesSection({ examples }: { examples: ExampleItem[] }) {
  return (
    <div className="space-y-3">
      {examples.map((ex, i) => (
        <div key={i} className="bg-[#1C2B33] rounded-lg p-3 space-y-1.5">
          <p className="text-sm text-[#9CA3AF]">
            Example {i + 1}
          </p>
          <div className="text-sm">
            <span className="text-[#9CA3AF]">Input: </span>
            <code className="text-[#58CC02]">{ex.input}</code>
          </div>
          <div className="text-sm">
            <span className="text-[#9CA3AF]">Output: </span>
            <code className="text-[#FFC800]">{ex.output}</code>
          </div>
        </div>
      ))}
    </div>
  );
}

function QuestionProgressControl({
  status,
  isPending,
  onSetStatus,
}: {
  status: Status;
  isPending: boolean;
  onSetStatus: (status: Status) => void;
}) {
  const label = status.replace("_", " ");
  const index = status === "done" || status === "review" || status === "rework"
    ? 2
    : status === "in_progress"
      ? 1
      : 0;
  const nextStatus: Status | null =
    status === "todo" || status === "rework"
      ? "in_progress"
      : status === "in_progress" || status === "review"
        ? "done"
        : null;
  const nextLabel =
    status === "todo"
      ? "Start"
      : status === "rework"
        ? "Start rework"
        : status === "in_progress" || status === "review"
          ? "Mark done"
          : "";
  const statusTone =
    status === "done"
      ? "bg-[#58CC02]/20 text-[#7DEB35]"
      : status === "in_progress"
        ? "bg-blue-900/50 text-blue-300"
        : status === "review"
          ? "bg-yellow-900/50 text-yellow-300"
          : status === "rework"
            ? "bg-red-900/50 text-red-300"
            : "bg-[#1C2B33] text-[#D1D5DB]";

  return (
    <div className="flex items-center gap-2 shrink-0">
      <div className="flex items-center gap-1" aria-label={`Progress: ${label}`}>
        {[0, 1, 2].map((step) => (
          <span
            key={step}
            className={`h-1.5 w-7 rounded-full ${
              step <= index ? "bg-[#58CC02]" : "bg-[#243640]"
            }`}
          />
        ))}
      </div>
      <span className={`text-xs rounded-full px-2 py-1 capitalize whitespace-nowrap ${statusTone}`}>
        {label}
      </span>
      {nextStatus && (
        <button
          onClick={() => onSetStatus(nextStatus)}
          disabled={isPending}
          className="text-xs rounded-full bg-[#58CC02] text-white px-3 py-1 font-semibold disabled:opacity-50 whitespace-nowrap"
        >
          {nextLabel}
        </button>
      )}
      {status !== "rework" && (
        <button
          onClick={() => onSetStatus("rework")}
          disabled={isPending}
          className="text-xs rounded-full bg-[#332026] text-[#FF8A8A] px-3 py-1 font-semibold disabled:opacity-50 whitespace-nowrap"
        >
          Rework
        </button>
      )}
    </div>
  );
}

function EditableTagRow({
  label,
  tags,
  color,
  bgColor,
  suggestions,
  onAdd,
  onRemove,
}: {
  label: string;
  tags: string[];
  color: string;
  bgColor: string;
  suggestions?: string[];
  onAdd: (tag: string) => void;
  onRemove: (tag: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [input, setInput] = useState("");

  const available = (suggestions || []).filter(
    (s) => !tags.includes(s) && s.toLowerCase().includes(input.toLowerCase())
  );

  const exactMatch = input.trim() && (suggestions || []).some(
    (s) => s.toLowerCase() === input.trim().toLowerCase()
  );
  const showCreate = input.trim().length > 1 && !exactMatch && !tags.some(
    (t) => t.toLowerCase() === input.trim().toLowerCase()
  );

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-xs text-[#9CA3AF] shrink-0">{label}:</span>
        <div className="flex flex-wrap gap-1.5 flex-1">
          {tags.map((t) => (
            <span
              key={t}
              className={`text-xs ${bgColor} ${color} px-2.5 py-1 rounded-full font-medium inline-flex items-center gap-1`}
            >
              {t}
              <button
                onClick={() => onRemove(t)}
                className="opacity-60 hover:opacity-100 ml-0.5"
              >
                ×
              </button>
            </span>
          ))}
          {!adding ? (
            <button
              onClick={() => setAdding(true)}
              className="text-xs text-[#9CA3AF] bg-[#243640] px-2 py-1 rounded-full"
            >
              +
            </button>
          ) : (
            <div className="relative">
              <input
                autoFocus
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && input.trim()) {
                    onAdd(input.trim());
                    setInput("");
                    setAdding(false);
                  } else if (e.key === "Escape") {
                    setInput("");
                    setAdding(false);
                  }
                }}
                onBlur={() => {
                  setTimeout(() => {
                    setInput("");
                    setAdding(false);
                  }, 200);
                }}
                placeholder={`Add ${label.toLowerCase()}...`}
                className="text-xs bg-[#243640] text-white rounded-full px-2.5 py-1 w-40 outline-none"
              />
              {(available.length > 0 || showCreate) && (
                <div className="absolute top-full left-0 mt-1 bg-[#1C2B33] border border-[#2a3f4a] rounded-lg shadow-lg z-10 max-h-48 overflow-y-auto w-52">
                  {showCreate && (
                    <button
                      onMouseDown={(e) => {
                        e.preventDefault();
                        onAdd(input.trim());
                        setInput("");
                        setAdding(false);
                      }}
                      className="w-full text-left text-xs px-3 py-1.5 hover:bg-[#243640] text-[#58CC02] font-medium border-b border-[#2a3f4a]"
                    >
                      + Create "{input.trim()}"
                    </button>
                  )}
                  {available.slice(0, 8).map((s) => (
                    <button
                      key={s}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        onAdd(s);
                        setInput("");
                        setAdding(false);
                      }}
                      className="w-full text-left text-xs text-white px-3 py-1.5 hover:bg-[#243640]"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SourceTagRow({
  sources,
  onAdd,
  onRemove,
}: {
  sources: SourceTag[];
  onAdd: (name: string) => void;
  onRemove: (name: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [input, setInput] = useState("");

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-xs text-[#9CA3AF] shrink-0">Source:</span>
        <div className="flex flex-wrap gap-1.5 flex-1">
          {sources.map((src) => (
            <span
              key={src.name}
              className="text-xs bg-[#2a3f4a] text-[#FFC800] px-2.5 py-1 rounded-full font-medium inline-flex items-center gap-1"
            >
              {src.name}
              <button
                onClick={() => onRemove(src.name)}
                className="opacity-60 hover:opacity-100 ml-0.5"
              >
                ×
              </button>
            </span>
          ))}
          {!adding ? (
            <button
              onClick={() => setAdding(true)}
              className="text-xs text-[#9CA3AF] bg-[#243640] px-2 py-1 rounded-full"
            >
              +
            </button>
          ) : (
            <input
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && input.trim()) {
                  onAdd(input.trim());
                  setInput("");
                  setAdding(false);
                } else if (e.key === "Escape") {
                  setInput("");
                  setAdding(false);
                }
              }}
              onBlur={() => {
                setInput("");
                setAdding(false);
              }}
              placeholder="Add source..."
              className="text-xs bg-[#243640] text-white rounded-full px-2.5 py-1 w-32 outline-none"
            />
          )}
        </div>
      </div>
    </div>
  );
}

function StudySubtopicsPrompt({
  subtopics,
  completedSubtopics,
  activeName,
  onStudy,
}: {
  subtopics: string[];
  completedSubtopics: Set<string>;
  activeName: string | null;
  onStudy: (name: string) => void;
}) {
  if (!subtopics.length) {
    return (
      <div className="bg-[#1C2B33] rounded-xl p-3 border border-[#2a3f4a]">
        <p className="text-sm text-white font-medium">Study the pattern behind this question</p>
        <p className="text-xs text-[#9CA3AF] mt-1">
          Add a subtopic in Metadata, then queue it into Popular Templates.
        </p>
      </div>
    );
  }

  const visibleSubtopics = subtopics.filter((name) => !completedSubtopics.has(name.toLowerCase().trim()));
  if (!visibleSubtopics.length) return null;

  return (
    <div className="bg-[#1E3328] border border-[#2F6B46] rounded-xl p-3 space-y-2">
      <div>
        <p className="text-sm text-white font-medium">Study the pattern{subtopics.length > 1 ? "s" : ""}</p>
        <p className="text-xs text-[#BFE8C8] mt-1">
          Queue a subtopic into Popular Templates before solving or reviewing the solution.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {visibleSubtopics.map((name) => (
          <button
            key={name}
            onClick={() => onStudy(name)}
            disabled={activeName === name}
            className="rounded-full bg-[#58CC02]/20 text-[#7DEB35] px-3 py-1.5 text-xs font-semibold disabled:opacity-60 active:bg-[#58CC02]/30"
          >
            {activeName === name ? "Adding..." : `+ Study ${name}`}
          </button>
        ))}
      </div>
    </div>
  );
}

type SolutionPick = "optimal" | "basic";

function NotesEditor({
  questionId,
  initialNotes,
}: {
  questionId: number;
  initialNotes: string;
}) {
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState(initialNotes);
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);

  const saveMut = useMutation({
    mutationFn: () => updateQuestion(questionId, { notes }),
    onSuccess: () => {
      setDirty(false);
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["question", questionId] });
    },
  });

  if (!editing) {
    return (
      <div className="bg-[#243640] rounded-lg p-3">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs text-[#FFC800] font-medium">My Notes</p>
          <button
            onClick={() => setEditing(true)}
            className="text-xs text-[#58CC02]"
          >
            {notes ? "Edit" : "Add notes"}
          </button>
        </div>
        {notes ? (
          <div className="text-sm text-white">
            <Markdown>{notes}</Markdown>
          </div>
        ) : (
          <p className="text-sm text-[#9CA3AF] italic">No notes yet.</p>
        )}
      </div>
    );
  }

  return (
    <div className="bg-[#243640] rounded-lg p-3 space-y-2">
      <p className="text-xs text-[#FFC800] font-medium">My Notes</p>
      <textarea
        value={notes}
        onChange={(e) => {
          setNotes(e.target.value);
          setDirty(true);
        }}
        placeholder="Add your own notes, observations, key takeaways..."
        rows={4}
        className="w-full bg-[#1C2B33] text-white rounded-lg px-3 py-2 text-sm placeholder-[#9CA3AF]/50 resize-y focus:outline-none focus:ring-1 focus:ring-[#FFC800]"
      />
      <div className="flex gap-2">
        <button
          onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending || !dirty}
          className="text-xs bg-[#58CC02] text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
        >
          {saveMut.isPending ? "Saving..." : "Save"}
        </button>
        <button
          onClick={() => {
            setEditing(false);
            setNotes(initialNotes);
            setDirty(false);
          }}
          className="text-xs text-[#9CA3AF] px-3 py-1.5"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export function QuestionDetail({
  questionId,
  onBack,
  forceReview = false,
}: {
  questionId: number;
  onBack: () => void;
  forceReview?: boolean;
}) {
  const queryClient = useQueryClient();
  const [solutionPick, setSolutionPick] = useState<SolutionPick>("optimal");
  const [descriptionWidth, setDescriptionWidth] = useState(50);
  const splitContainerRef = useRef<HTMLDivElement | null>(null);

  const { data: question, isLoading } = useQuery({
    queryKey: ["question", questionId],
    queryFn: () => fetchQuestion(questionId),
  });

  const { data: solutions, isLoading: solLoading } = useQuery({
    queryKey: ["solutions", questionId],
    queryFn: () => fetchSolutions(questionId),
  });

  const { data: topicOrder } = useQuery({
    queryKey: ["topicOrder"],
    queryFn: fetchTopicOrder,
  });

  const { data: allSubtopics } = useQuery({
    queryKey: ["subtopics"],
    queryFn: () => fetchSubtopics(),
  });
  const { data: allTemplates } = useQuery({
    queryKey: ["templates"],
    queryFn: fetchTemplates,
  });
  const { data: allCompleted } = useQuery({
    queryKey: ["reviewAll"],
    queryFn: fetchAllCompleted,
  });

  const tagMut = useMutation({
    mutationFn: (data: Partial<{ topics: string[]; subtopics: string[]; sources: { name: string; type: string }[] }>) =>
      updateQuestion(questionId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["question", questionId] });
      queryClient.invalidateQueries({ queryKey: ["questions"] });
    },
  });
  const [studySubtopicName, setStudySubtopicName] = useState<string | null>(null);

  const findKnownSubtopic = (name: string) =>
    allSubtopics?.find((st) => st.name.toLowerCase().trim() === name.toLowerCase().trim()) || null;

  const completedSubtopics = new Set(
    [
      ...(allTemplates || [])
        .filter((template) => !!template.last_reviewed)
        .flatMap((template) => [template.title, template.subtopic || ""]),
      ...(allCompleted?.items || [])
        .filter((item) => item.review_type === "template" && !!item.last_reviewed)
        .flatMap((item) => [item.title, ...(item.subtopics || [])]),
    ]
      .map((name) => name.toLowerCase().trim())
      .filter(Boolean),
  );

  const ensureSubtopic = async (name: string, category?: string): Promise<SubtopicInfo> => {
    const existing = findKnownSubtopic(name);
    if (existing) return existing;
    try {
      const created = await createSubtopic({
        name,
        category: category || question?.topics?.[0] || "Uncategorized",
      });
      regenerateSubtopicDescription(created.id).then(() => {
        queryClient.invalidateQueries({ queryKey: ["subtopics"] });
      }).catch(() => {});
      return created;
    } catch (error) {
      const fresh = await fetchSubtopics();
      queryClient.setQueryData(["subtopics"], fresh);
      const found = fresh.find((st) => st.name.toLowerCase().trim() === name.toLowerCase().trim());
      if (found) return found;
      throw error;
    }
  };

  const addQuestionSubtopicMut = useMutation({
    mutationFn: async (name: string) => {
      const category = question?.topics?.[0] || "Uncategorized";
      const subtopic = await ensureSubtopic(name, category);
      const current = question?.subtopics || [];
      if (current.some((st) => st.toLowerCase().trim() === subtopic.name.toLowerCase().trim())) {
        return question;
      }
      return updateQuestion(questionId, { subtopics: [...current, subtopic.name] });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["question", questionId] });
      queryClient.invalidateQueries({ queryKey: ["questions"] });
      queryClient.invalidateQueries({ queryKey: ["subtopics"] });
    },
  });

  const studySubtopicMut = useMutation({
    mutationFn: async (name: string): Promise<StudyPlan> => {
      setStudySubtopicName(name);
      const category = findKnownSubtopic(name)?.category || question?.topics?.[0] || "Uncategorized";
      const subtopic = await ensureSubtopic(name, category);
      return addTemplates(1, subtopic.id);
    },
    onSuccess: (plan) => {
      queryClient.setQueryData(["studyPlan"], plan);
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
      queryClient.invalidateQueries({ queryKey: ["subtopics"] });
    },
    onSettled: () => {
      setStudySubtopicName(null);
    },
  });

  const generateMut = useMutation({
    mutationFn: () => generateSolutions(questionId),
    onSuccess: async (newSolutions) => {
      queryClient.setQueryData(["solutions", questionId], newSolutions);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["solutions", questionId] }),
        queryClient.invalidateQueries({ queryKey: ["question", questionId] }),
        queryClient.invalidateQueries({ queryKey: ["questions"] }),
        queryClient.invalidateQueries({ queryKey: ["patternDeck"] }),
      ]);
    },
  });

  const statusMut = useMutation({
    mutationFn: (status: Status) => setQuestionStatus(questionId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["question", questionId] });
      queryClient.invalidateQueries({ queryKey: ["questions"] });
      queryClient.invalidateQueries({ queryKey: ["questionStats"] });
      queryClient.invalidateQueries({ queryKey: ["dailyPlan"] });
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });

  const handleSplitPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const container = splitContainerRef.current;
    if (!container) return;

    const updateWidth = (clientX: number) => {
      const rect = container.getBoundingClientRect();
      const rawPct = ((clientX - rect.left) / rect.width) * 100;
      setDescriptionWidth(Math.min(72, Math.max(28, rawPct)));
    };

    updateWidth(event.clientX);

    const onPointerMove = (moveEvent: globalThis.PointerEvent) => {
      updateWidth(moveEvent.clientX);
    };
    const onPointerUp = () => {
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  };

  if (isLoading) {
    return <div className="p-4 text-center text-[#9CA3AF]">Loading...</div>;
  }
  if (!question) {
    return <div className="p-4 text-center text-red-400">Question not found</div>;
  }

  const diffColor =
    question.difficulty === "Easy"
      ? "text-[#58CC02]"
      : question.difficulty === "Medium"
        ? "text-[#FFC800]"
        : "text-[#FF4B4B]";

  const descriptionPanel = (
    <div className="space-y-4">
      {/* Description */}
      {question.description ? (
        <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
          <h3 className="text-white font-bold text-sm">Description</h3>
          <Markdown>{question.description}</Markdown>
          {question.examples && question.examples.length > 0 && (
            <ExamplesSection examples={question.examples} />
          )}
        </div>
      ) : (
        <div className="bg-[#1C2B33] rounded-xl p-4 text-center">
          <p className="text-[#9CA3AF] text-sm">
            No description yet. Generate AI solutions to auto-fill the problem description and examples.
          </p>
        </div>
      )}

      <StudySubtopicsPrompt
        subtopics={question.subtopics || []}
        completedSubtopics={completedSubtopics}
        activeName={studySubtopicName}
        onStudy={(name) => studySubtopicMut.mutate(name)}
      />
      {studySubtopicMut.isError && (
        <p className="text-xs text-[#FF8A8A]">{(studySubtopicMut.error as Error).message}</p>
      )}

      {/* Metadata */}
      <div className="bg-[#1C2B33] rounded-xl p-3">
        <CollapsibleSection
          title="Metadata"
          badge={
            <span className="text-xs bg-[#243640] text-[#9CA3AF] rounded px-2 py-0.5">
              topic · subtopic · source
            </span>
          }
        >
          <div className="space-y-2 pt-2">
            <EditableTagRow
              label="Topics"
              tags={question.topics || []}
              color="text-[#58CC02]"
              bgColor="bg-[#58CC02]/20"
              suggestions={topicOrder || []}
              onAdd={(t) => tagMut.mutate({ topics: [...(question.topics || []), t] })}
              onRemove={(t) => tagMut.mutate({ topics: (question.topics || []).filter((x) => x !== t) })}
            />
            <EditableTagRow
              label="Subtopics"
              tags={question.subtopics || []}
              color="text-[#d1d5db]"
              bgColor="bg-[#243640]"
              suggestions={
                allSubtopics
                  ? [
                      ...allSubtopics.filter((st) => question.topics?.includes(st.category)).map((st) => st.name),
                      ...allSubtopics.filter((st) => !question.topics?.includes(st.category)).map((st) => st.name),
                    ]
                  : []
              }
              onAdd={(st) => addQuestionSubtopicMut.mutate(st)}
              onRemove={(st) => tagMut.mutate({ subtopics: (question.subtopics || []).filter((x) => x !== st) })}
            />
            <SourceTagRow
              sources={question.sources || []}
              onAdd={(name) =>
                tagMut.mutate({
                  sources: [...(question.sources || []), { name, type: "list" }],
                })
              }
              onRemove={(name) =>
                tagMut.mutate({
                  sources: (question.sources || []).filter((s) => s.name !== name),
                })
              }
            />
            {addQuestionSubtopicMut.isError && (
              <p className="text-xs text-[#FF8A8A]">{(addQuestionSubtopicMut.error as Error).message}</p>
            )}
          </div>
        </CollapsibleSection>
      </div>

      {/* User Notes */}
      <NotesEditor
        questionId={questionId}
        initialNotes={question.notes || ""}
      />
    </div>
  );

  const optimal = solutions?.find((s) => s.is_optimal) ?? solutions?.[0] ?? null;
  const basic = solutions?.find((s) => !s.is_optimal) ?? null;
  const activeSolution = solutionPick === "basic" && basic ? basic : optimal;
  const isReview = forceReview || question.status === "review" || question.status === "rework";

  const workPanel = (
    <div className="space-y-4">
      {/* Solution selector + generate */}
      {solLoading ? (
        <p className="text-[#9CA3AF] text-sm">Loading solutions...</p>
      ) : !solutions?.length ? (
        <div className="text-center py-4">
          <p className="text-[#9CA3AF] text-sm mb-3">No solutions yet.</p>
          <button
            onClick={() => generateMut.mutate()}
            disabled={generateMut.isPending}
            className="text-sm bg-[#58CC02] text-white px-4 py-2 rounded-lg disabled:opacity-50 active:bg-[#46a302]"
          >
            {generateMut.isPending ? "Generating..." : "Generate AI Solutions"}
          </button>
          {generateMut.isError && (
            <p className="text-red-400 text-sm mt-2">{(generateMut.error as Error).message}</p>
          )}
        </div>
      ) : (
        <>
          {/* Solution picker dropdown */}
          {basic && (
            <div className="flex items-center gap-2">
              <select
                value={solutionPick}
                onChange={(e) => setSolutionPick(e.target.value as SolutionPick)}
                className="bg-[#1C2B33] text-white text-sm rounded-lg px-3 py-2 border border-[#2a3f4a] focus:outline-none focus:ring-1 focus:ring-[#58CC02]"
              >
                <option value="optimal">
                  {optimal?.approach_name || "Optimal"} (Optimal)
                </option>
                <option value="basic">
                  {basic.approach_name || "Basic"} (Basic)
                </option>
              </select>
              <button
                onClick={() => generateMut.mutate()}
                disabled={generateMut.isPending}
                className="text-xs text-[#9CA3AF] active:text-white disabled:opacity-50"
              >
                {generateMut.isPending ? "Regenerating..." : "Regenerate"}
              </button>
            </div>
          )}

          {/* Code */}
          <SolveView
            questionId={questionId}
            questionTitle={question.title}
            questionDescription={question.description}
            subtopicName={question.subtopics?.[0] || undefined}
            onStatusChange={(status) => statusMut.mutate(status)}
            activeSolution={activeSolution}
            isReview={isReview}
          />
        </>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-full overflow-y-auto md:overflow-hidden pb-4 md:pb-0 max-w-7xl mx-auto w-full">
      {/* Header */}
      <div className="p-4 border-b border-[#2a3f4a] flex items-center gap-3 md:shrink-0">
        <button onClick={onBack} className="text-[#9CA3AF] text-xl">←</button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {question.number && <span className="text-[#9CA3AF] text-sm">#{question.number}</span>}
            <span className={`text-sm font-medium ${diffColor}`}>{question.difficulty}</span>
          </div>
          <div className="flex items-center gap-3 min-w-0 flex-wrap">
            <h2 className="text-white font-bold truncate min-w-0 flex-1">{question.title}</h2>
            <QuestionProgressControl
              status={question.status}
              isPending={statusMut.isPending}
              onSetStatus={(status) => statusMut.mutate(status)}
            />
          </div>
        </div>
        {question.url && (
          <a
            href={question.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[#58CC02] underline shrink-0"
          >
            LeetCode
          </a>
        )}
      </div>

      {/* Mobile: stacked layout / Medium+ screens: resizable side-by-side panes */}
      <div ref={splitContainerRef} className="p-4 md:flex md:gap-0 md:flex-1 md:min-h-0 md:overflow-hidden">
        <div
          className="md:shrink-0 md:grow-0 mb-4 md:mb-0 md:h-full md:overflow-y-auto md:pr-3 md:min-w-0"
          style={{ flexBasis: `${descriptionWidth}%` }}
        >
          {descriptionPanel}
        </div>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize question and answer panes"
          onPointerDown={handleSplitPointerDown}
          className="hidden md:flex w-4 shrink-0 cursor-col-resize items-stretch justify-center group"
        >
          <div className="w-px bg-[#2a3f4a] group-hover:bg-[#58CC02] transition-colors" />
        </div>
        <div className="md:flex-1 min-w-0 md:h-full md:overflow-y-auto md:pl-3">
          {workPanel}
        </div>
      </div>
    </div>
  );
}
