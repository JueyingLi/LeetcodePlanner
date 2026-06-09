import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { generateQuiz, submitQuiz, saveQuizAnswer, fetchQuizHistory, deleteQuizAttempt, clearQuizHistory } from "../../api/quiz";
import { fetchStudyPlan } from "../../api/studyPlan";
import { fetchTopics } from "../../api/questions";
import { fetchSubtopics } from "../../api/subtopics";
import { Markdown } from "../ui/Markdown";
import { saveQuizzesOffline } from "../../offline/db";
import { OfflineQuizzes } from "./OfflineQuizzes";
import type { QuizAttempt, QuizFocus } from "../../types";

const focusOptions: { value: QuizFocus; label: string; desc: string }[] = [
  { value: "pattern_recognition", label: "Pattern Recognition", desc: "Identify the specific sub-type and why" },
  { value: "approach_reasoning", label: "Approach Design", desc: "Detailed design — state, transitions, why this technique" },
  { value: "code_implementation", label: "Code Implementation", desc: "Pick the correct code snippet — find bugs in implementations" },
  { value: "input_output", label: "Input/Output", desc: "Understand what's given and edge inputs" },
  { value: "edge_cases", label: "Edge Cases", desc: "Spot tricky scenarios that break naive solutions" },
  { value: "complexity", label: "Complexity", desc: "Deep time & space analysis" },
  { value: "full_flow", label: "Full Flow", desc: "All steps end-to-end with code" },
];

export function QuizSession() {
  const queryClient = useQueryClient();
  const [quizzes, setQuizzes] = useState<QuizAttempt[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [answers, setAnswers] = useState<Map<number, { answer: string; correct: boolean }>>(new Map());
  const [selectedFocuses, setSelectedFocuses] = useState<QuizFocus[]>(["pattern_recognition"]);
  const [done, setDone] = useState(false);
  const [showPriorSteps, setShowPriorSteps] = useState(false);
  const [showDescription, setShowDescription] = useState(false);
  const [selectedTopic, setSelectedTopic] = useState<string>("");
  const [selectedSubtopic, setSelectedSubtopic] = useState<string>("");
  const [showHistory, setShowHistory] = useState(false);
  const [historyWrongOnly, setHistoryWrongOnly] = useState(true);
  const [showOffline, setShowOffline] = useState(false);
  const [savedOffline, setSavedOffline] = useState(false);

  const { data: topics } = useQuery({
    queryKey: ["topics"],
    queryFn: fetchTopics,
  });

  const { data: subtopics } = useQuery({
    queryKey: ["subtopics"],
    queryFn: () => fetchSubtopics(),
  });

  const { data: history } = useQuery({
    queryKey: ["quizHistory", historyWrongOnly],
    queryFn: () => fetchQuizHistory(historyWrongOnly),
    enabled: showHistory,
  });

  const deleteMut = useMutation({
    mutationFn: deleteQuizAttempt,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["quizHistory"] }),
  });

  const clearMut = useMutation({
    mutationFn: () => clearQuizHistory(false),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["quizHistory"] }),
  });

  const filteredSubtopics = subtopics?.filter(
    (st) => !selectedTopic || st.category === selectedTopic
  );

  const genMut = useMutation({
    mutationFn: async () => {
      const useTodaysPatterns =
        selectedFocuses.includes("pattern_recognition") && !selectedTopic && !selectedSubtopic;
      if (!useTodaysPatterns) {
        return generateQuiz({
          count: 5,
          quiz_focuses: selectedFocuses,
          topics: selectedTopic ? [selectedTopic] : undefined,
          subtopics: selectedSubtopic ? [selectedSubtopic] : undefined,
        });
      }

      const plan = await fetchStudyPlan();
      const patternSession = plan.sessions.find((s) => s.session_type === "pattern_drill");
      const ids = Array.from(
        new Set(
          (patternSession?.items || [])
            .map((item) => item.question_id)
            .filter((id): id is number => typeof id === "number")
        )
      );
      if (!ids.length) {
        throw new Error("No Pattern Drill questions in today's Study plan yet.");
      }
      return generateQuiz({
        count: Math.min(10, Math.max(5, ids.length * selectedFocuses.length)),
        quiz_focuses: selectedFocuses,
        question_ids: ids,
      });
    },
    onSuccess: (data) => {
      setQuizzes(data.quizzes);
      setCurrentIdx(0);
      setSelected(null);
      setShowResult(false);
      setAnswers(new Map());
      setDone(false);
    },
  });

  const submitMut = useMutation({
    mutationFn: submitQuiz,
  });

  const current = quizzes[currentIdx];

  const handleSelect = (option: string) => {
    if (showResult) return;
    setSelected(option);
    setShowResult(true);
    const correct = option === current.correct_answer;
    setAnswers(new Map(answers.set(current.id, { answer: option, correct })));
    saveQuizAnswer(current.id, option).catch(() => {});
    if (correct) {
      setTimeout(() => handleNext(), 1200);
    }
  };

  const handleNext = () => {
    if (currentIdx < quizzes.length - 1) {
      setCurrentIdx(currentIdx + 1);
      setSelected(null);
      setShowResult(false);
      setShowPriorSteps(false);
      setShowDescription(false);
    } else {
      setDone(true);
      submitMut.mutate(
        Array.from(answers.entries()).map(([id, { answer }]) => ({
          quiz_id: id,
          answer,
        }))
      );
    }
  };

  if (!quizzes.length || done) {
    const correctCount = Array.from(answers.values()).filter((a) => a.correct).length;
    return (
      <div className="p-4 space-y-6">
        {done && answers.size > 0 && (
          <div className="bg-[#1C2B33] rounded-xl p-6 text-center space-y-3">
            <p className="text-3xl">{correctCount === answers.size ? "🎉" : correctCount > answers.size / 2 ? "💪" : "📖"}</p>
            <p className="text-white font-bold text-xl">
              {correctCount}/{answers.size} correct
            </p>
            <div className="w-full bg-[#243640] rounded-full h-3">
              <div
                className="bg-[#58CC02] h-3 rounded-full transition-all"
                style={{ width: `${(correctCount / answers.size) * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* Topic / Subtopic filters */}
        <div className="space-y-3">
          <h3 className="text-white font-bold">Filter by Topic</h3>
          <div className="flex flex-col sm:flex-row gap-2">
            <select
              value={selectedTopic}
              onChange={(e) => {
                setSelectedTopic(e.target.value);
                setSelectedSubtopic("");
              }}
              className="flex-1 bg-[#1C2B33] text-sm text-[#9CA3AF] rounded-lg px-3 py-2 outline-none"
            >
              <option value="">All Topics</option>
              {topics?.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <select
              value={selectedSubtopic}
              onChange={(e) => setSelectedSubtopic(e.target.value)}
              className="flex-1 bg-[#1C2B33] text-sm text-[#9CA3AF] rounded-lg px-3 py-2 outline-none"
            >
              <option value="">All Subtopics</option>
              {filteredSubtopics?.map((st) => (
                <option key={st.id} value={st.name}>{st.name} ({st.question_count})</option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-3">
          <h3 className="text-white font-bold">Choose Practice Focus <span className="text-xs text-[#9CA3AF] font-normal">(select one or more)</span></h3>
          {focusOptions.map((f) => {
            const isSelected = selectedFocuses.includes(f.value);
            return (
              <button
                key={f.value}
                onClick={() => {
                  if (f.value === "full_flow") {
                    setSelectedFocuses(isSelected ? [] : ["full_flow"]);
                  } else {
                    const without = selectedFocuses.filter((x) => x !== "full_flow" && x !== f.value);
                    if (isSelected) {
                      setSelectedFocuses(without);
                    } else {
                      setSelectedFocuses([...without, f.value]);
                    }
                  }
                }}
                className={`w-full text-left p-4 rounded-xl transition-colors ${
                  isSelected
                    ? "bg-[#58CC02]/20 border border-[#58CC02]"
                    : "bg-[#1C2B33] active:bg-[#243640]"
                }`}
              >
                <p className="text-white font-medium">{f.label}</p>
                <p className="text-[#9CA3AF] text-sm">{f.desc}</p>
                {f.value === "pattern_recognition" && !selectedTopic && !selectedSubtopic && (
                  <p className="text-[#58CC02] text-xs mt-1">
                    Uses today's Pattern Drill questions when no filter is selected.
                  </p>
                )}
              </button>
            );
          })}
        </div>

        <button
          onClick={() => genMut.mutate()}
          disabled={genMut.isPending || selectedFocuses.length === 0}
          className="w-full bg-[#58CC02] text-white font-bold py-4 rounded-xl disabled:opacity-50 active:bg-[#46a302] text-lg"
        >
          {genMut.isPending
            ? "Generating..."
            : selectedFocuses.length === 0
              ? "Select at least one focus"
              : `Start Quiz (${selectedFocuses.length} focus${selectedFocuses.length > 1 ? "es" : ""})`}
        </button>
        {genMut.isError && (
          <p className="text-red-400 text-sm">{(genMut.error as Error).message}</p>
        )}

        {/* Review Past Quizzes */}
        <div className="space-y-3">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="w-full text-left flex items-center justify-between bg-[#1C2B33] rounded-xl p-4"
          >
            <span className="text-white font-bold">Review Past Quizzes</span>
            <span className="text-[#9CA3AF]">{showHistory ? "▾" : "▸"}</span>
          </button>

          {showHistory && (
            <div className="space-y-3">
              <div className="flex gap-2 items-center">
                <button
                  onClick={() => setHistoryWrongOnly(true)}
                  className={`text-xs px-3 py-1.5 rounded-full ${
                    historyWrongOnly ? "bg-[#FF4B4B]/20 text-[#FF4B4B]" : "bg-[#1C2B33] text-[#9CA3AF]"
                  }`}
                >
                  Wrong Only
                </button>
                <button
                  onClick={() => setHistoryWrongOnly(false)}
                  className={`text-xs px-3 py-1.5 rounded-full ${
                    !historyWrongOnly ? "bg-[#58CC02]/20 text-[#58CC02]" : "bg-[#1C2B33] text-[#9CA3AF]"
                  }`}
                >
                  All
                </button>
                <div className="flex-1" />
                {history && history.length > 0 && (
                  <button
                    onClick={() => { if (confirm("Clear all quiz history?")) clearMut.mutate(); }}
                    disabled={clearMut.isPending}
                    className="text-xs text-[#FF4B4B] px-2 py-1"
                  >
                    {clearMut.isPending ? "Clearing..." : "Clear All"}
                  </button>
                )}
              </div>

              {history && history.length > 0 ? (
                history.map((q) => {
                  const unanswered = q.is_correct === null;
                  return (
                    <div
                      key={q.id}
                      className={`rounded-xl p-4 space-y-2 ${
                        unanswered ? "bg-[#1C2B33]" : q.is_correct ? "bg-green-900/20" : "bg-red-900/20"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold ${
                          unanswered ? "text-[#9CA3AF]" : q.is_correct ? "text-[#58CC02]" : "text-[#FF4B4B]"
                        }`}>
                          {unanswered ? "Unanswered" : q.is_correct ? "Correct" : "Wrong"}
                        </span>
                        <span className="text-xs text-[#9CA3AF] flex-1">
                          {q.quiz_data.question_title}
                        </span>
                        <button
                          onClick={() => deleteMut.mutate(q.id)}
                          className="text-xs text-[#9CA3AF] hover:text-[#FF4B4B] px-1"
                        >
                          ×
                        </button>
                      </div>
                      <p className="text-white text-sm">{q.quiz_data.prompt}</p>
                      {!unanswered && q.user_answer && !q.is_correct && (
                        <div className="text-xs space-y-1">
                          <p className="text-[#FF4B4B]">Your answer: {q.user_answer}</p>
                          <p className="text-[#58CC02]">Correct: {q.correct_answer}</p>
                        </div>
                      )}
                      {unanswered && (
                        <div className="text-xs space-y-1">
                          <p className="text-[#58CC02]">Answer: {q.correct_answer}</p>
                        </div>
                      )}
                      {q.quiz_data.explanation && (
                        <div className="text-xs text-[#9CA3AF] bg-[#131F24] rounded-lg p-2">
                          <Markdown>{q.quiz_data.explanation}</Markdown>
                        </div>
                      )}
                    </div>
                  );
                })
              ) : (
                <p className="text-[#9CA3AF] text-sm text-center py-4">
                  {history ? "No quiz history yet." : "Loading..."}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Offline saved quizzes */}
        <div className="space-y-3">
          <button
            onClick={() => setShowOffline(!showOffline)}
            className="w-full text-left flex items-center justify-between bg-[#1C2B33] rounded-xl p-4"
          >
            <span className="text-white font-bold">Offline Quizzes</span>
            <span className="text-[#9CA3AF]">{showOffline ? "▾" : "▸"}</span>
          </button>
          {showOffline && <OfflineQuizzes />}
        </div>
      </div>
    );
  }

  const questionTitle = current.quiz_data.question_title;
  const questionNumber = current.quiz_data.question_number;
  const questionDescription = current.quiz_data.question_description;

  return (
    <div className="p-4 flex flex-col h-full">
      {/* Progress bar */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 bg-[#243640] rounded-full h-2">
          <div
            className="bg-[#58CC02] h-2 rounded-full transition-all"
            style={{ width: `${((currentIdx + (showResult ? 1 : 0)) / quizzes.length) * 100}%` }}
          />
        </div>
        <span className="text-sm text-[#9CA3AF]">
          {currentIdx + 1}/{quizzes.length}
        </span>
        <button
          onClick={async () => {
            await saveQuizzesOffline(quizzes);
            setSavedOffline(true);
            setTimeout(() => setSavedOffline(false), 2000);
          }}
          className="text-xs text-[#58CC02] px-2 py-1 rounded-lg active:bg-[#243640] shrink-0"
        >
          {savedOffline ? "Saved ✓" : "Save offline"}
        </button>
      </div>

      {/* Question title header */}
      {questionTitle && (
        <div className="mb-3">
          <p className="text-xs text-[#9CA3AF]">
            {questionNumber ? `#${questionNumber} ` : ""}{questionTitle}
          </p>
        </div>
      )}

      {/* View description toggle */}
      {questionDescription && (
        <div className="bg-[#243640] rounded-xl p-3 mb-3">
          <button
            onClick={() => setShowDescription(!showDescription)}
            className="w-full text-left flex items-center justify-between"
          >
            <span className="text-sm text-[#58CC02] font-medium">Problem Description</span>
            <span className="text-[#9CA3AF] text-sm">{showDescription ? "▾" : "▸"}</span>
          </button>
          {showDescription && (
            <div className="mt-2">
              <Markdown>{questionDescription!}</Markdown>
            </div>
          )}
        </div>
      )}

      {/* Prior steps summary */}
      {current.quiz_data.prior_steps_summary && (
        <div className="bg-[#243640] rounded-xl p-3 mb-3">
          <button
            onClick={() => setShowPriorSteps(!showPriorSteps)}
            className="w-full text-left flex items-center justify-between"
          >
            <span className="text-sm text-[#FFC800] font-medium">Prior steps</span>
            <span className="text-[#9CA3AF] text-sm">{showPriorSteps ? "▾" : "▸"}</span>
          </button>
          {showPriorSteps && (
            <p className="text-sm text-[#9CA3AF] mt-2 whitespace-pre-wrap">
              {current.quiz_data.prior_steps_summary}
            </p>
          )}
        </div>
      )}

      {/* Question */}
      <div className="mb-4">
        <p className="text-white text-lg font-medium">{current.quiz_data.prompt}</p>
      </div>

      {/* Options */}
      <div className="space-y-3 flex-1">
        {(() => {
          const opts = current.quiz_data.options || [];
          const isCodeChoice = current.quiz_type === "code_completion";

          const diffLines = new Set<number>();
          if (isCodeChoice && opts.length > 1) {
            const split = opts.map((o) => o.split("\n"));
            const maxLen = Math.max(...split.map((s) => s.length));
            for (let i = 0; i < maxLen; i++) {
              const lines = split.map((s) => (s[i] || "").trimEnd());
              if (new Set(lines).size > 1) diffLines.add(i);
            }
          }

          return opts.map((option, idx) => {
            let bg = "bg-[#1C2B33] active:bg-[#243640]";
            if (showResult) {
              if (option === current.correct_answer) {
                bg = "bg-green-900/40 border-green-500";
              } else if (option === selected) {
                bg = "bg-red-900/40 border-red-500";
              } else {
                bg = "bg-[#1C2B33] opacity-50";
              }
            } else if (option === selected) {
              bg = "bg-[#243640]";
            }
            return (
              <button
                key={idx}
                onClick={() => handleSelect(option)}
                className={`w-full text-left p-4 rounded-xl border border-transparent transition-colors ${bg}`}
              >
                {isCodeChoice ? (
                  <pre className="text-xs font-mono whitespace-pre-wrap overflow-x-auto">
                    <code>
                      {option.split("\n").map((line, li) => (
                        <span
                          key={li}
                          className={diffLines.has(li) ? "text-[#FFC800] bg-[#FFC800]/10 block" : "text-white block"}
                        >
                          {line}{"\n"}
                        </span>
                      ))}
                    </code>
                  </pre>
                ) : (
                  <p className="text-white">{option}</p>
                )}
              </button>
            );
          });
        })()}
      </div>

      {/* Result explanation + next */}
      {showResult && (
        <div className="mt-4 space-y-3">
          {selected === current.correct_answer ? (
            <p className="text-[#58CC02] font-bold text-center">Correct!</p>
          ) : (
            <p className="text-[#FF4B4B] font-bold text-center">Incorrect</p>
          )}
          {current.quiz_data.explanation && (
            <div className="text-[#9CA3AF] text-sm bg-[#1C2B33] rounded-lg p-3">
              <Markdown>{current.quiz_data.explanation}</Markdown>
            </div>
          )}
          <button
            onClick={handleNext}
            className="w-full bg-[#58CC02] text-white font-bold py-3 rounded-xl active:bg-[#46a302]"
          >
            {currentIdx < quizzes.length - 1 ? "Next" : "See Results"}
          </button>
        </div>
      )}
    </div>
  );
}
