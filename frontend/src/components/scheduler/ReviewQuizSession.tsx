import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  answerReviewItem,
  buildReviewQuiz,
  fetchReviewItems,
  fetchReviewStats,
} from "../../api/reviewQuiz";
import { Markdown } from "../ui/Markdown";
import type { ReviewQuizItem, ReviewQuizStats } from "../../types";

const FORMAT_LABELS: Record<string, { label: string; color: string; icon: string }> = {
  scenario_match: { label: "Scenario Match", color: "bg-purple-500/20 text-purple-300", icon: "🎯" },
  signal_recognition: { label: "Signal Recognition", color: "bg-blue-500/20 text-blue-300", icon: "📡" },
  code_repair: { label: "Code Repair", color: "bg-red-500/20 text-red-300", icon: "🔧" },
  drill_recall: { label: "Drill Recall", color: "bg-amber-500/20 text-amber-300", icon: "🧠" },
  when_to_use: { label: "When to Use", color: "bg-green-500/20 text-green-300", icon: "💡" },
  approach_select: { label: "Approach Select", color: "bg-cyan-500/20 text-cyan-300", icon: "🧭" },
  mistake_retry: { label: "Mistake Retry", color: "bg-orange-500/20 text-orange-300", icon: "🔄" },
};

function sourceLinkLabel(item: ReviewQuizItem): { text: string; type: string; id: number } | null {
  const meta = item.metadata_json;
  const linkType = meta?.link_type as string | undefined;
  const linkId = meta?.link_id as number | undefined;
  if (!linkType || !linkId) return null;
  if (linkType === "question") return { text: `Question #${linkId}`, type: "question", id: linkId };
  if (linkType === "subtopic") {
    const name = (meta?.subtopic_name as string) || `Pattern #${linkId}`;
    return { text: name, type: "subtopic", id: linkId };
  }
  return null;
}

function MCRenderer({
  item,
  onAnswer,
  answered,
}: {
  item: ReviewQuizItem;
  onAnswer: (answer: string) => void;
  answered: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(item.user_answer);
  const options = item.options || [];

  const handleSelect = (opt: string) => {
    if (answered) return;
    setSelected(opt);
    onAnswer(opt);
  };

  return (
    <div className="space-y-2 mt-3">
      {options.map((opt, i) => {
        const isSelected = selected === opt;
        const isCorrect = opt.toLowerCase().trim() === item.correct_answer.toLowerCase().trim();
        let cls = "border-[#2a3f4a] bg-[#1C2B33] text-white";
        if (answered) {
          if (isCorrect) cls = "border-[#58CC02] bg-[#58CC02]/15 text-[#7DEB35]";
          else if (isSelected && !isCorrect) cls = "border-[#FF4B4B] bg-[#FF4B4B]/15 text-[#FF8A8A]";
        } else if (isSelected) {
          cls = "border-[#38BDF8] bg-[#38BDF8]/15 text-[#7DD3FC]";
        }

        return (
          <button
            key={i}
            onClick={() => handleSelect(opt)}
            disabled={answered}
            className={`w-full text-left p-3 rounded-xl border ${cls} transition-colors`}
          >
            <span className="text-xs font-mono text-[#9CA3AF] mr-2">
              {String.fromCharCode(65 + i)}.
            </span>
            {opt}
          </button>
        );
      })}
    </div>
  );
}

function CodeContextBlock({ code }: { code: string }) {
  const BLANK = "___BLANK___";
  if (!code.includes(BLANK)) {
    return (
      <div className="bg-[#0d1b22] rounded-xl border border-[#2a3f4a] p-3 max-h-72 overflow-auto">
        <pre className="text-xs font-mono text-[#9CA3AF] whitespace-pre">{code}</pre>
      </div>
    );
  }
  const parts = code.split(BLANK);
  return (
    <div className="bg-[#0d1b22] rounded-xl border border-[#2a3f4a] p-3 max-h-72 overflow-auto">
      <pre className="text-xs font-mono whitespace-pre">
        <span className="text-[#9CA3AF]">{parts[0]}</span>
        <span className="bg-[#FFC800]/20 text-[#FFC800] px-1 rounded font-bold">{"????"}</span>
        <span className="text-[#9CA3AF]">{parts[1]}</span>
      </pre>
    </div>
  );
}

function CodeMCRenderer({
  item,
  onAnswer,
  answered,
}: {
  item: ReviewQuizItem;
  onAnswer: (answer: string) => void;
  answered: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(item.user_answer);
  const options = item.options || [];
  const normalize = (s: string) => s.replace(/\s+/g, " ").trim().toLowerCase();
  const codeContext = item.metadata_json?.code_context as string | undefined;

  const handleSelect = (opt: string) => {
    if (answered) return;
    setSelected(opt);
    onAnswer(opt);
  };

  return (
    <div className="space-y-3 mt-3">
      {codeContext && <CodeContextBlock code={codeContext} />}

      <div className="space-y-2">
        {options.map((opt, i) => {
          const isSelected = selected === opt;
          const isCorrect = normalize(opt) === normalize(item.correct_answer);
          let border = "border-[#2a3f4a]";
          let bg = "bg-[#0d1b22]";
          if (answered) {
            if (isCorrect) { border = "border-[#58CC02]"; bg = "bg-[#58CC02]/10"; }
            else if (isSelected) { border = "border-[#FF4B4B]"; bg = "bg-[#FF4B4B]/10"; }
          } else if (isSelected) {
            border = "border-[#38BDF8]"; bg = "bg-[#38BDF8]/10";
          }

          const isWrongCode = normalize(opt) === normalize(
            (item.metadata_json?.user_wrong_code as string) || "",
          );

          return (
            <button
              key={i}
              onClick={() => handleSelect(opt)}
              disabled={answered}
              className={`w-full text-left rounded-xl border ${border} ${bg} overflow-hidden transition-colors`}
            >
              <div className="flex items-center justify-between px-3 pt-2 pb-1">
                <span className="text-xs font-semibold text-[#9CA3AF]">
                  Option {String.fromCharCode(65 + i)}
                </span>
                {answered && isWrongCode && !isCorrect && (
                  <span className="text-[10px] bg-[#FF4B4B]/20 text-[#FF8A8A] rounded-full px-2 py-0.5">
                    Your previous mistake
                  </span>
                )}
                {answered && isCorrect && (
                  <span className="text-[10px] bg-[#58CC02]/20 text-[#7DEB35] rounded-full px-2 py-0.5">
                    Correct
                  </span>
                )}
              </div>
              <div className="px-3 pb-3 max-h-40 overflow-auto">
                <pre className="text-xs font-mono text-[#BFE8FF] whitespace-pre">{opt}</pre>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function FreeTextRenderer({
  item,
  onAnswer,
  answered,
}: {
  item: ReviewQuizItem;
  onAnswer: (answer: string) => void;
  answered: boolean;
}) {
  const [text, setText] = useState(item.user_answer || "");
  const [submitted, setSubmitted] = useState(answered);

  const handleSubmit = () => {
    if (!text.trim()) return;
    setSubmitted(true);
    onAnswer(text);
  };

  return (
    <div className="mt-3 space-y-3">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={submitted}
        className="w-full bg-[#0d1b22] border border-[#2a3f4a] rounded-xl p-3 text-sm text-white focus:outline-none focus:border-[#38BDF8]"
        placeholder="Type your answer..."
        onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
      />
      {!submitted && (
        <button
          onClick={handleSubmit}
          disabled={!text.trim()}
          className="w-full py-2.5 rounded-xl text-sm font-semibold bg-[#38BDF8] text-[#131F24] disabled:opacity-40"
        >
          Submit
        </button>
      )}
      {submitted && (
        <div className={`rounded-xl p-3 text-sm ${
          item.is_correct ? "bg-[#58CC02]/15 border border-[#58CC02] text-[#7DEB35]"
            : "bg-[#FF4B4B]/15 border border-[#FF4B4B] text-[#FF8A8A]"
        }`}>
          {item.is_correct ? "Correct!" : (
            <span>Correct answer: <strong>{item.correct_answer}</strong></span>
          )}
        </div>
      )}
    </div>
  );
}

function QuizCard({
  item,
  index,
  total,
  onAnswer,
  onNext,
  onSourceClick,
  isLast,
}: {
  item: ReviewQuizItem;
  index: number;
  total: number;
  onAnswer: (answer: string) => void;
  onNext: () => void;
  onSourceClick: (type: string, id: number) => void;
  isLast: boolean;
}) {
  const answered = item.user_answer != null;
  const fmt = FORMAT_LABELS[item.quiz_format] || { label: item.quiz_format, color: "bg-[#243640] text-[#9CA3AF]", icon: "?" };
  const link = sourceLinkLabel(item);

  return (
    <div className="bg-[#1C2B33] rounded-2xl overflow-hidden">
      <div className="px-4 pt-4 pb-2 flex items-center justify-between">
        <span className={`text-xs font-semibold rounded-full px-2.5 py-1 ${fmt.color}`}>
          {fmt.icon} {fmt.label}
        </span>
        <span className="text-xs text-[#9CA3AF]">{index + 1} / {total}</span>
      </div>

      <div className="px-4 pb-2">
        <div className="text-sm text-white">
          <Markdown>{item.prompt}</Markdown>
        </div>

        {item.quiz_format === "code_repair" && item.options && item.options.length > 0 ? (
          <CodeMCRenderer item={item} onAnswer={onAnswer} answered={answered} />
        ) : item.options && item.options.length > 0 ? (
          <MCRenderer item={item} onAnswer={onAnswer} answered={answered} />
        ) : (
          <FreeTextRenderer item={item} onAnswer={onAnswer} answered={answered} />
        )}
      </div>

      {answered && item.explanation && (
        <div className="mx-4 mb-3 p-3 bg-[#0d1b22] rounded-xl border border-[#2a3f4a]">
          <p className="text-xs font-semibold text-[#9CA3AF] mb-1">Explanation</p>
          <div className="text-sm text-[#BFE8FF]">
            <Markdown>{item.explanation}</Markdown>
          </div>
        </div>
      )}

      <div className="px-4 pb-4 flex items-center justify-between gap-2">
        {link && (
          <button
            onClick={() => onSourceClick(link.type, link.id)}
            className="text-xs text-[#38BDF8] underline underline-offset-2"
          >
            View: {link.text}
          </button>
        )}
        {!link && <span />}
        {answered && (
          <button
            onClick={onNext}
            className="px-5 py-2 rounded-xl text-sm font-semibold bg-[#58CC02] text-[#131F24]"
          >
            {isLast ? "See Results" : "Next"}
          </button>
        )}
      </div>
    </div>
  );
}

function StatsView({
  items,
  stats,
  onRestart,
  onSourceClick,
}: {
  items: ReviewQuizItem[];
  stats: ReviewQuizStats | undefined;
  onRestart: () => void;
  onSourceClick: (type: string, id: number) => void;
}) {
  const answered = items.filter((i) => i.user_answer != null);
  const correct = answered.filter((i) => i.is_correct);
  const pct = answered.length ? Math.round((correct.length / answered.length) * 100) : 0;

  return (
    <div className="space-y-4">
      <div className="bg-[#1C2B33] rounded-2xl p-6 text-center">
        <div className={`text-5xl font-bold ${pct >= 70 ? "text-[#58CC02]" : pct >= 40 ? "text-[#FFC800]" : "text-[#FF4B4B]"}`}>
          {pct}%
        </div>
        <p className="text-sm text-[#9CA3AF] mt-1">
          {correct.length} / {answered.length} correct
        </p>

        {stats && stats.total > answered.length && (
          <p className="text-xs text-[#9CA3AF] mt-3">
            All-time: {stats.correct}/{stats.total} ({stats.accuracy}%)
          </p>
        )}
      </div>

      {stats && Object.keys(stats.by_format).length > 0 && (
        <div className="bg-[#1C2B33] rounded-2xl p-4 space-y-2">
          <h4 className="text-xs font-semibold text-[#9CA3AF]">By Format</h4>
          {Object.entries(stats.by_format).map(([fmt, s]) => {
            const f = FORMAT_LABELS[fmt];
            return (
              <div key={fmt} className="flex items-center justify-between text-sm">
                <span className="text-white">{f?.icon} {f?.label || fmt}</span>
                <span className={s.accuracy >= 70 ? "text-[#58CC02]" : s.accuracy >= 40 ? "text-[#FFC800]" : "text-[#FF4B4B]"}>
                  {s.correct}/{s.total} ({s.accuracy}%)
                </span>
              </div>
            );
          })}
        </div>
      )}

      <div className="bg-[#1C2B33] rounded-2xl p-4 space-y-2">
        <h4 className="text-xs font-semibold text-[#9CA3AF]">Review Wrong Answers</h4>
        {answered.filter((i) => !i.is_correct).length === 0 ? (
          <p className="text-sm text-[#58CC02]">All correct — great job!</p>
        ) : (
          answered
            .filter((i) => !i.is_correct)
            .map((item) => {
              const link = sourceLinkLabel(item);
              const f = FORMAT_LABELS[item.quiz_format];
              return (
                <div key={item.id} className="bg-[#0d1b22] rounded-xl p-3 border border-[#2a3f4a]">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-[10px] rounded-full px-2 py-0.5 ${f?.color || "bg-[#243640] text-[#9CA3AF]"}`}>
                      {f?.icon} {f?.label}
                    </span>
                  </div>
                  <p className="text-sm text-white line-clamp-2">{item.prompt.replace(/[*#`]/g, "").slice(0, 120)}</p>
                  <p className="text-xs text-[#FF8A8A] mt-1">
                    Your answer: {item.user_answer?.slice(0, 80)}
                  </p>
                  <p className="text-xs text-[#7DEB35] mt-0.5">
                    Correct: {item.correct_answer.slice(0, 80)}
                  </p>
                  {link && (
                    <button
                      onClick={() => onSourceClick(link.type, link.id)}
                      className="text-xs text-[#38BDF8] underline underline-offset-2 mt-1"
                    >
                      Review: {link.text}
                    </button>
                  )}
                </div>
              );
            })
        )}
      </div>

      <button
        onClick={onRestart}
        className="w-full py-3 rounded-xl text-sm font-semibold bg-[#38BDF8] text-[#131F24]"
      >
        Generate New Quiz
      </button>
    </div>
  );
}

export function ReviewQuizSession({
  onSelectQuestion,
}: {
  onSelectQuestion: (id: number) => void;
}) {
  const queryClient = useQueryClient();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showResults, setShowResults] = useState(false);
  const startTimeRef = useRef<number>(Date.now());

  const { data: existingItems, isLoading: loadingExisting } = useQuery({
    queryKey: ["reviewQuizItems"],
    queryFn: fetchReviewItems,
  });

  const buildMut = useMutation({
    mutationFn: (limit: number) => buildReviewQuiz(limit),
    onSuccess: (data) => {
      queryClient.setQueryData(["reviewQuizItems"], data);
      setCurrentIndex(0);
      setShowResults(false);
    },
  });

  const answerMut = useMutation({
    mutationFn: ({ id, answer, time }: { id: number; answer: string; time?: number }) =>
      answerReviewItem(id, answer, time),
    onSuccess: (updated) => {
      queryClient.setQueryData(["reviewQuizItems"], (old: ReviewQuizItem[] | undefined) =>
        old?.map((i) => (i.id === updated.id ? updated : i)),
      );
    },
  });

  const { data: stats } = useQuery({
    queryKey: ["reviewQuizStats"],
    queryFn: fetchReviewStats,
    enabled: showResults,
  });

  const hasStaleItems = existingItems?.some(
    (i) => i.quiz_format === "code_repair" && (!i.options || i.options.length === 0),
  ) ?? false;

  const unanswered = existingItems?.filter((i) => !i.user_answer) || [];
  const items = existingItems || [];
  const hasActiveQuiz = unanswered.length > 0 && !hasStaleItems;

  useEffect(() => {
    if (!loadingExisting && hasStaleItems && !buildMut.isPending) {
      buildMut.mutate(15);
    }
  }, [loadingExisting, hasStaleItems]);

  useEffect(() => {
    if (!loadingExisting && items.length > 0 && unanswered.length > 0 && !hasStaleItems) {
      const firstUnansweredIdx = items.findIndex((i) => !i.user_answer);
      if (firstUnansweredIdx >= 0) setCurrentIndex(firstUnansweredIdx);
    }
  }, [loadingExisting, hasStaleItems]);

  const handleAnswer = (answer: string) => {
    const item = items[currentIndex];
    if (!item || item.user_answer != null) return;
    const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000);
    answerMut.mutate({ id: item.id, answer, time: elapsed });
  };

  const handleNext = () => {
    if (currentIndex < items.length - 1) {
      setCurrentIndex(currentIndex + 1);
      startTimeRef.current = Date.now();
    } else {
      setShowResults(true);
      queryClient.invalidateQueries({ queryKey: ["reviewQuizStats"] });
    }
  };

  const handleSourceClick = (type: string, id: number) => {
    if (type === "question") onSelectQuestion(id);
  };

  const handleBuild = () => buildMut.mutate(15);

  if (loadingExisting) {
    return <p className="text-sm text-[#9CA3AF] p-4">Loading review quiz...</p>;
  }

  if (!hasActiveQuiz && !showResults && items.length === 0) {
    return (
      <div className="bg-[#1C2B33] rounded-2xl p-6 text-center space-y-3">
        <p className="text-3xl">🧠</p>
        <p className="text-white font-semibold">Review Quiz</p>
        <p className="text-sm text-[#9CA3AF]">
          Test yourself on patterns, signals, and code from your study sessions.
          Quizzes are built from your existing data — no AI generation needed.
        </p>
        <button
          onClick={handleBuild}
          disabled={buildMut.isPending}
          className="w-full py-3 rounded-xl text-sm font-semibold bg-[#58CC02] text-[#131F24] disabled:opacity-50"
        >
          {buildMut.isPending ? "Building..." : "Start Review Quiz"}
        </button>
        {buildMut.isError && (
          <p className="text-xs text-[#FF8A8A]">{(buildMut.error as Error).message}</p>
        )}
      </div>
    );
  }

  if (showResults || (!hasActiveQuiz && items.length > 0)) {
    return (
      <StatsView
        items={items}
        stats={stats}
        onRestart={handleBuild}
        onSourceClick={handleSourceClick}
      />
    );
  }

  const currentItem = items[currentIndex];
  if (!currentItem) {
    return (
      <div className="bg-[#1C2B33] rounded-2xl p-4 text-sm text-[#9CA3AF]">
        No quiz items available.
        <button onClick={handleBuild} className="ml-2 text-[#38BDF8] underline">
          Build new quiz
        </button>
      </div>
    );
  }

  const progress = items.filter((i) => i.user_answer != null).length;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-[#243640] rounded-full overflow-hidden">
          <div
            className="h-full bg-[#58CC02] rounded-full transition-all"
            style={{ width: `${(progress / items.length) * 100}%` }}
          />
        </div>
        <span className="text-xs text-[#9CA3AF] shrink-0">{progress}/{items.length}</span>
      </div>

      <QuizCard
        key={currentItem.id}
        item={currentItem}
        index={currentIndex}
        total={items.length}
        onAnswer={handleAnswer}
        onNext={handleNext}
        onSourceClick={handleSourceClick}
        isLast={currentIndex === items.length - 1}
      />
    </div>
  );
}
