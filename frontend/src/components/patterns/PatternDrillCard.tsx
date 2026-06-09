import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchQuestion } from "../../api/questions";
import {
  askDrill,
  fetchPatternAnalysis,
  generatePatternAnalysis,
  regeneratePatternAnalysis,
  reviewDrill,
} from "../../api/patternDrill";
import { Markdown } from "../ui/Markdown";
import { LinkifyTerms, Term } from "../glossary/GlossaryProvider";
import type { ApproachStep, DrillCard, DrillQuestion, PatternAnalysis } from "../../types";

const CATEGORY_META: Record<string, { label: string; chip: string }> = {
  data_structure: { label: "Data Structure", chip: "bg-[#334B59] text-[#BFE8FF]" },
  algorithm: { label: "Algorithm", chip: "bg-[#3A3764] text-[#C8C4FF]" },
  optimization: { label: "Optimization", chip: "bg-[#4A4024] text-[#FFE08A]" },
};

const difficultyColor: Record<string, string> = {
  Easy: "text-green-400",
  Medium: "text-yellow-400",
  Hard: "text-red-400",
};

const GRADES: { label: string; quality: number; cls: string; hint: string }[] = [
  {
    label: "Rework",
    quality: 2,
    cls: "bg-[#FF4B4B]/20 text-[#FF8A8A]",
    hint: "Bring it back soon.",
  },
  {
    label: "Normal",
    quality: 4,
    cls: "bg-[#58CC02]/20 text-[#7DEB35]",
    hint: "Default review later.",
  },
  {
    label: "Easy",
    quality: 5,
    cls: "bg-[#58CC02]/30 text-[#7DEB35]",
    hint: "Push it far out.",
  },
];

function ApproachView({ approach }: { approach: ApproachStep }) {
  const meta = CATEGORY_META[approach.category] || { label: approach.category, chip: "bg-[#243640] text-[#D1D5DB]" };
  return (
    <div className="bg-[#131F24] rounded-lg p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-xs rounded-full px-2 py-0.5 ${meta.chip}`}>
          {meta.label}
        </span>
        <Term
          name={approach.label}
          className="text-sm font-semibold text-white active:text-[#58CC02]"
        />
      </div>
      <p className="text-sm text-[#D1D5DB]">
        <LinkifyTerms text={approach.why} />
      </p>
      {approach.code_steps.length > 0 && (
        <div className="space-y-1.5">
          {approach.code_steps.map((cs, i) => (
            <div key={i} className="bg-[#0A1419] rounded p-2">
              <pre className="text-xs text-[#BFE8FF] font-mono whitespace-pre-wrap">{cs.code}</pre>
              <p className="text-xs text-[#9CA3AF] mt-1">{cs.explanation}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const STEP_LABEL_STYLE: Record<string, string> = {
  observation: "bg-[#2A3B26] text-[#A3D977]",
  "data structure": "bg-[#334B59] text-[#BFE8FF]",
  algorithm: "bg-[#3A3764] text-[#C8C4FF]",
  approach: "bg-[#3A3764] text-[#C8C4FF]",
  optimization: "bg-[#4A4024] text-[#FFE08A]",
};

function QuestionView({
  dq,
  revealed,
  onReveal,
}: {
  dq: DrillQuestion;
  revealed: boolean;
  onReveal: () => void;
}) {
  const stepLabel = dq.approach_label?.toLowerCase() || "";
  const chipCls = STEP_LABEL_STYLE[stepLabel] || "bg-[#243640] text-[#D1D5DB]";
  return (
    <div className="bg-[#131F24] rounded-lg p-3 space-y-2">
      {dq.approach_label && (
        <span className={`text-[10px] font-semibold uppercase tracking-wider rounded px-2 py-0.5 ${chipCls}`}>
          {dq.approach_label}
        </span>
      )}
      <p className="text-white text-sm font-medium">{dq.question}</p>
      {revealed ? (
        <div className="text-sm text-[#D1D5DB] bg-[#0A1419] rounded p-2">
          <Markdown>{dq.answer}</Markdown>
        </div>
      ) : (
        <button
          onClick={onReveal}
          className="bg-[#58CC02] text-white text-xs font-semibold rounded-lg px-3 py-1.5"
        >
          Reveal answer
        </button>
      )}
    </div>
  );
}

export interface DeckEntry {
  questionId: number;
  preloaded?: DrillCard;
  completed?: boolean;
  onStatusChange?: (status: "in_progress" | "completed" | "rework") => void | Promise<void>;
  onAllRevealed?: () => void;
}

export function PatternDrillDeck({
  cards,
  onSelectQuestion,
  onGenerateMore,
  onRegenerateAll,
  isGenerating,
  isRegeneratingAll,
  generateError,
}: {
  cards: DeckEntry[];
  onSelectQuestion?: (id: number) => void;
  onGenerateMore?: () => void;
  onRegenerateAll?: () => void;
  isGenerating?: boolean;
  isRegeneratingAll?: boolean;
  generateError?: string;
}) {
  const [showCompleted, setShowCompleted] = useState(false);
  const [done, setDone] = useState<Set<number>>(
    () => new Set(cards.filter((c) => c.completed).map((c) => c.questionId))
  );

  useEffect(() => {
    setDone(new Set(cards.filter((c) => c.completed).map((c) => c.questionId)));
  }, [cards]);

  const pendingCards = cards.filter((c) => !done.has(c.questionId));
  const completedCards = cards.filter((c) => done.has(c.questionId));
  const visibleCards = showCompleted ? cards : pendingCards;

  const [idx, setIdx] = useState(0);
  const [allRevealedCards, setAllRevealedCards] = useState<Set<number>>(new Set());

  if (cards.length === 0) {
    return (
      <div className="space-y-3">
        <div className="bg-[#1C2B33] rounded-xl p-4 text-sm text-[#9CA3AF]">
          No pattern drills here yet.
        </div>
        {onGenerateMore && (
          <button
            onClick={onGenerateMore}
            disabled={isGenerating}
            className="w-full bg-[#8B7CFF] text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-50"
          >
            {isGenerating ? "Generating..." : "Generate More"}
          </button>
        )}
      </div>
    );
  }

  const safeIdx = Math.min(idx, Math.max(visibleCards.length - 1, 0));
  const card = visibleCards[safeIdx];
  const doneCount = completedCards.length;
  const atEnd = safeIdx >= visibleCards.length - 1;

  const handleNext = async () => {
    if (card && allRevealedCards.has(card.questionId) && !done.has(card.questionId)) {
      setDone((prev) => new Set([...prev, card.questionId]));
      await card.onStatusChange?.("completed");
    }
    setIdx(safeIdx + 1);
  };

  const markCardAllRevealed = (questionId: number) => {
    setAllRevealedCards((prev) => new Set([...prev, questionId]));
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[#9CA3AF]">
          {visibleCards.length > 0
            ? `Card ${safeIdx + 1} of ${visibleCards.length}`
            : "All complete"}
          {" · "}{doneCount}/{cards.length} complete
        </span>
        {completedCards.length > 0 && (
          <button
            onClick={() => {
              setShowCompleted((s) => !s);
              setIdx(0);
            }}
            className="text-xs rounded-lg px-3 py-1.5 bg-[#1C2B33] text-[#9CA3AF] active:text-white"
          >
            {showCompleted ? "Hide reviewed" : `Review (${completedCards.length})`}
          </button>
        )}
      </div>

      {visibleCards.length > 0 && card ? (
        <PatternDrillCard
          key={card.questionId}
          questionId={card.questionId}
          preloaded={card.preloaded}
          completed={done.has(card.questionId)}
          onStatusChange={card.onStatusChange}
          onSelectQuestion={onSelectQuestion}
          onAllRevealed={() => markCardAllRevealed(card.questionId)}
        />
      ) : (
        <div className="bg-[#1C2B33] rounded-xl p-6 text-center space-y-2">
          <p className="text-white font-semibold">All drills completed</p>
          <p className="text-sm text-[#9CA3AF]">Generate more or review the completed drills.</p>
        </div>
      )}

      <div className="flex justify-center gap-1.5">
        {visibleCards.map((c, i) => (
          <button
            key={c.questionId}
            onClick={() => setIdx(i)}
            aria-label={`Go to card ${i + 1}`}
            className={`h-2 w-2 rounded-full ${
              done.has(c.questionId)
                ? "bg-[#58CC02]"
                : i === safeIdx
                ? "bg-[#C8C4FF]"
                : "bg-[#3A3764]"
            }`}
          />
        ))}
      </div>

      {/* Navigation — at the bottom */}
      <div className="flex gap-2">
        <button
          onClick={() => setIdx(safeIdx - 1)}
          disabled={safeIdx === 0}
          className="flex-1 bg-[#1C2B33] text-[#9CA3AF] rounded-xl py-3 text-sm font-semibold disabled:opacity-40 active:text-white"
        >
          ← Previous
        </button>
        {atEnd ? (
          onGenerateMore ? (
            <button
              onClick={async () => {
                if (card && allRevealedCards.has(card.questionId) && !done.has(card.questionId)) {
                  setDone((prev) => new Set([...prev, card.questionId]));
                  await card.onStatusChange?.("completed");
                }
                onGenerateMore();
              }}
              disabled={isGenerating}
              className="flex-1 bg-[#8B7CFF] text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-50"
            >
              {isGenerating ? "Generating..." : "Generate More"}
            </button>
          ) : (
            <button
              disabled
              className="flex-1 bg-[#282642] text-[#C8C4FF] rounded-xl py-3 text-sm font-semibold opacity-40"
            >
              Next →
            </button>
          )
        ) : (
          <button
            onClick={handleNext}
            className="flex-1 bg-[#282642] text-[#C8C4FF] rounded-xl py-3 text-sm font-semibold"
          >
            Next →
          </button>
        )}
      </div>
      {onRegenerateAll && (
        <button
          onClick={onRegenerateAll}
          disabled={isRegeneratingAll}
          className="w-full bg-[#FF4B4B]/20 text-[#FF8A8A] rounded-xl py-3 text-sm font-semibold disabled:opacity-50"
        >
          {isRegeneratingAll ? "Regenerating all..." : "Regenerate All"}
        </button>
      )}
      {generateError && (
        <p className="text-sm text-[#FF4B4B]">{generateError}</p>
      )}
    </div>
  );
}

export function PatternDrillCard({
  questionId,
  preloaded,
  completed,
  onStatusChange,
  onSelectQuestion,
  onAllRevealed,
}: {
  questionId: number;
  preloaded?: DrillCard;
  completed?: boolean;
  onStatusChange?: (status: "in_progress" | "completed" | "rework") => void | Promise<void>;
  onSelectQuestion?: (id: number) => void;
  onAllRevealed?: () => void;
}) {
  const queryClient = useQueryClient();
  const needsFetch = !preloaded?.pattern_analysis;

  const { data: fetchedAnalysis, isLoading: analysisLoading } = useQuery({
    queryKey: ["patternAnalysis", questionId],
    queryFn: () => fetchPatternAnalysis(questionId).catch(() => null),
    enabled: needsFetch,
    retry: false,
  });

  const { data: fetched, isLoading } = useQuery({
    queryKey: ["question", questionId],
    queryFn: () => fetchQuestion(questionId),
  });

  const analysis: PatternAnalysis | null =
    preloaded?.pattern_analysis ?? (fetchedAnalysis as PatternAnalysis | null) ?? null;
  const title = preloaded?.title ?? fetched?.title ?? "";
  const number = preloaded?.number ?? fetched?.number ?? null;
  const difficulty = preloaded?.difficulty ?? fetched?.difficulty ?? "";

  const questions = useMemo(() => analysis?.questions ?? [], [analysis]);
  const approaches = useMemo(() => analysis?.approaches ?? [], [analysis]);

  const [revealedQuestions, setRevealedQuestions] = useState<Set<number>>(new Set());
  const [showApproaches, setShowApproaches] = useState(false);
  const [showTitle, setShowTitle] = useState(false);
  const [graded, setGraded] = useState<number | null>(null);
  const [askText, setAskText] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);

  const allQuestionsRevealed = revealedQuestions.size >= questions.length;

  useEffect(() => {
    if (allQuestionsRevealed && questions.length > 0) {
      onAllRevealed?.();
    }
  }, [allQuestionsRevealed, questions.length]);

  const reviewMut = useMutation({
    mutationFn: (quality: number) => reviewDrill(questionId, quality),
    onSuccess: async (_d, quality) => {
      setGraded(quality);
      if (quality <= 2) {
        await onStatusChange?.("rework");
      } else {
        await onStatusChange?.("in_progress");
      }
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });

  const askMut = useMutation({
    mutationFn: () => askDrill(questionId, askText),
    onSuccess: (d) => {
      setAnswer(d.answer);
      setAskText("");
    },
  });

  const genMut = useMutation({
    mutationFn: () => generatePatternAnalysis(questionId),
    onSuccess: (data) => {
      if (data.pattern_analysis) {
        queryClient.setQueryData(["patternAnalysis", questionId], data.pattern_analysis);
      }
      queryClient.invalidateQueries({ queryKey: ["patternDeck"] });
    },
  });

  const regenMut = useMutation({
    mutationFn: () => regeneratePatternAnalysis(questionId),
    onSuccess: (data) => {
      if (data.pattern_analysis) {
        queryClient.setQueryData(["patternAnalysis", questionId], data.pattern_analysis);
      }
      queryClient.invalidateQueries({ queryKey: ["patternDeck"] });
    },
  });

  const [autoTried, setAutoTried] = useState(false);
  useEffect(() => {
    if (!analysis && !isLoading && !analysisLoading && !autoTried && !genMut.isPending) {
      setAutoTried(true);
      genMut.mutate();
    }
  }, [analysis, isLoading, analysisLoading, autoTried, genMut]);

  if (needsFetch && (isLoading || analysisLoading)) {
    return <div className="bg-[#1C2B33] rounded-xl p-4 text-sm text-[#9CA3AF]">Loading…</div>;
  }

  if (!analysis) {
    return (
      <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
        <p className="text-white font-medium">
          {number ? `#${number} ` : ""}{title || "Preparing drill…"}
        </p>
        {genMut.isError ? (
          <>
            <p className="text-sm text-red-400">{(genMut.error as Error).message}</p>
            <button
              onClick={() => genMut.mutate()}
              disabled={genMut.isPending}
              className="bg-[#58CC02] text-white text-sm font-semibold rounded-lg px-3 py-2 disabled:opacity-50"
            >
              {genMut.isPending ? "Generating…" : "Try again"}
            </button>
          </>
        ) : (
          <p className="text-sm text-[#9CA3AF]">
            Generating pattern analysis… this can take ~30s.
          </p>
        )}
      </div>
    );
  }

  const revealQuestion = async (idx: number) => {
    setRevealedQuestions((prev) => new Set([...prev, idx]));
    if (revealedQuestions.size === 0 && !completed) {
      await onStatusChange?.("in_progress");
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    }
  };

  return (
    <div className="bg-[#1C2B33] rounded-xl p-4 space-y-4">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs rounded-full px-2 py-0.5 bg-[#282642] text-[#C8C4FF]">
              Pattern drill
            </span>
            {completed ? (
              <span className="text-xs rounded-full px-2 py-0.5 bg-[#1E3328] text-[#7DEB35]">
                ✓ Done
              </span>
            ) : graded !== null ? (
              <span className="text-xs rounded-full px-2 py-0.5 bg-[#243640] text-[#C8C4FF]">
                Reviewed
              </span>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => regenMut.mutate()}
              disabled={regenMut.isPending}
              className="text-xs text-[#FF8A8A] active:text-white disabled:opacity-50"
            >
              {regenMut.isPending ? "Regenerating…" : "Regenerate"}
            </button>
            <button
              onClick={() => setShowTitle((s) => !s)}
              className="text-xs text-[#9CA3AF] active:text-white"
            >
              {showTitle ? "Hide problem" : "Reveal problem"}
            </button>
          </div>
        </div>

        {/* Scenario */}
        {analysis.scenario && (
          <p className="text-white text-sm leading-snug">
            <LinkifyTerms text={analysis.scenario} />
          </p>
        )}

        {/* Example */}
        {analysis.example && (
          <div className="bg-[#0A1419] rounded-lg px-3 py-2 space-y-0.5">
            {analysis.example.split("\n").map((line, i) => (
              <p key={i} className="text-xs text-[#BFE8FF] font-mono">{line}</p>
            ))}
          </div>
        )}

        {showTitle && (
          <button
            onClick={() => onSelectQuestion?.(questionId)}
            className="text-left text-sm text-[#58CC02]"
          >
            {number ? `#${number} ` : ""}{title}
            {difficulty && (
              <span className={`ml-2 text-xs ${difficultyColor[difficulty] || "text-gray-400"}`}>
                {difficulty}
              </span>
            )}
          </button>
        )}
      </div>

      {/* Drill questions */}
      {questions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-[#9CA3AF] font-medium uppercase tracking-wide">
            Questions ({revealedQuestions.size}/{questions.length})
          </p>
          {questions.map((dq, i) => (
            <QuestionView
              key={i}
              dq={dq}
              revealed={revealedQuestions.has(i)}
              onReveal={() => revealQuestion(i)}
            />
          ))}
        </div>
      )}

      {/* Approaches — shown after all questions revealed */}
      {allQuestionsRevealed && approaches.length > 0 && (
        <div className="space-y-2">
          <button
            onClick={() => setShowApproaches((s) => !s)}
            className="text-xs text-[#C8C4FF] font-medium uppercase tracking-wide"
          >
            {showApproaches ? "Hide approaches" : `Show approaches (${approaches.length})`}
          </button>
          {showApproaches && (
            <div className="space-y-2">
              {approaches.map((app, i) => (
                <ApproachView key={i} approach={app} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Self-grade after all questions revealed */}
      {allQuestionsRevealed && (
        <div className="space-y-2">
          <p className="text-xs text-[#9CA3AF]">
            {graded === null
              ? "How well did you know this? Pick one to save and move on."
              : graded <= 2
              ? "Saved as rework. It can appear again in Study."
              : graded >= 5
              ? "Saved as easy."
              : "Saved as normal review for later."}
          </p>
          <div className="grid grid-cols-3 gap-2">
            {GRADES.map((g) => (
              <button
                key={g.label}
                onClick={() => reviewMut.mutate(g.quality)}
                disabled={reviewMut.isPending}
                className={`rounded-lg py-2 px-2 disabled:opacity-50 ${
                  graded === g.quality ? `${g.cls} ring-1 ring-current` : g.cls
                }`}
              >
                <span className="block text-sm font-semibold">{g.label}</span>
                <span className="block text-[10px] font-normal opacity-80">{g.hint}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Q&A tutor box */}
      <div className="border-t border-[#2a3f4a] pt-3 space-y-2">
        <p className="text-xs text-[#9CA3AF] font-medium">Ask a question about this problem or pattern</p>
        <textarea
          value={askText}
          onChange={(e) => setAskText(e.target.value)}
          rows={2}
          placeholder="e.g. Why a heap instead of sorting here?"
          className="w-full bg-[#131F24] text-sm text-white rounded-lg p-2 outline-none resize-none"
        />
        <button
          onClick={() => askMut.mutate()}
          disabled={askMut.isPending || !askText.trim()}
          className="bg-[#243640] text-[#D1D5DB] text-sm font-semibold rounded-lg px-3 py-1.5 disabled:opacity-50"
        >
          {askMut.isPending ? "Asking…" : "Ask"}
        </button>
        {askMut.isError && <p className="text-xs text-red-400">{(askMut.error as Error).message}</p>}
        {answer && (
          <div className="bg-[#131F24] rounded-lg p-3 text-sm text-[#D1D5DB]">
            <Markdown>{answer}</Markdown>
          </div>
        )}
      </div>
    </div>
  );
}
