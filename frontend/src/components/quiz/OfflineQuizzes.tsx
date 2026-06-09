import { useEffect, useState } from "react";
import {
  listSavedQuizzes,
  removeSavedQuiz,
  enqueueAnswer,
  countPending,
  type SavedQuiz,
} from "../../offline/db";
import { flushPendingAnswers } from "../../offline/sync";
import { Markdown } from "../ui/Markdown";

export function OfflineQuizzes() {
  const [saved, setSaved] = useState<SavedQuiz[]>([]);
  const [pending, setPending] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});

  const refresh = async () => {
    setSaved(await listSavedQuizzes());
    setPending(await countPending());
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleAnswer = async (quiz: SavedQuiz, option: string) => {
    if (answers[quiz.id]) return; // already answered this session
    setAnswers((a) => ({ ...a, [quiz.id]: option }));
    await enqueueAnswer(quiz.id, option);
    setPending(await countPending());
  };

  const handleSync = async () => {
    await flushPendingAnswers();
    await refresh();
  };

  const handleRemove = async (id: number) => {
    await removeSavedQuiz(id);
    await refresh();
  };

  if (saved.length === 0) {
    return (
      <p className="text-[#9CA3AF] text-sm text-center py-4">
        No quizzes saved for offline yet. Generate a quiz and tap “Save for offline”.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {pending > 0 && (
        <div className="flex items-center justify-between bg-[#243640] rounded-lg p-3">
          <span className="text-sm text-[#FFC800]">{pending} answer{pending !== 1 ? "s" : ""} waiting to sync</span>
          <button
            onClick={handleSync}
            disabled={!navigator.onLine}
            className="text-xs bg-[#58CC02] text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
          >
            {navigator.onLine ? "Sync now" : "Offline"}
          </button>
        </div>
      )}

      {saved.map((quiz) => {
        const opts = quiz.quiz_data.options || [];
        const chosen = answers[quiz.id];
        const isCode = quiz.quiz_type === "code_completion";
        return (
          <div key={quiz.id} className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs text-[#9CA3AF]">{quiz.quiz_data.question_title}</p>
              <button
                onClick={() => handleRemove(quiz.id)}
                className="text-xs text-[#9CA3AF] hover:text-[#FF4B4B] shrink-0"
              >
                ×
              </button>
            </div>
            <p className="text-white text-sm font-medium">{quiz.quiz_data.prompt}</p>

            <div className="space-y-2">
              {opts.map((option, idx) => {
                let bg = "bg-[#243640] active:bg-[#2a4a56]";
                if (chosen) {
                  if (option === quiz.correct_answer) bg = "bg-green-900/40 border border-green-500";
                  else if (option === chosen) bg = "bg-red-900/40 border border-red-500";
                  else bg = "bg-[#243640] opacity-50";
                }
                return (
                  <button
                    key={idx}
                    onClick={() => handleAnswer(quiz, option)}
                    className={`w-full text-left p-3 rounded-lg transition-colors ${bg}`}
                  >
                    {isCode ? (
                      <pre className="text-xs font-mono whitespace-pre-wrap overflow-x-auto text-white">{option}</pre>
                    ) : (
                      <span className="text-white text-sm">{option}</span>
                    )}
                  </button>
                );
              })}
            </div>

            {chosen && quiz.quiz_data.explanation && (
              <div className="text-xs text-[#9CA3AF] bg-[#131F24] rounded-lg p-2">
                <Markdown>{quiz.quiz_data.explanation}</Markdown>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
