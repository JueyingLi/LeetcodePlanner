import { useState } from "react";
import { createPortal } from "react-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchQuestions, createQuestion, importQuestions, fetchTopics } from "../../api/questions";
import type { Difficulty, Question } from "../../types";

const difficultyColor: Record<string, string> = {
  Easy: "bg-green-900/50 text-green-400",
  Medium: "bg-yellow-900/50 text-yellow-400",
  Hard: "bg-red-900/50 text-red-400",
};

const statusColor: Record<string, string> = {
  todo: "bg-gray-700 text-gray-300",
  in_progress: "bg-blue-900/50 text-blue-400",
  done: "bg-green-900/50 text-green-400",
  review: "bg-yellow-900/50 text-yellow-400",
  rework: "bg-red-900/50 text-red-400",
};

export function QuestionList({ onSelectQuestion }: { onSelectQuestion: (id: number) => void }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [topicFilter, setTopicFilter] = useState("");
  const [diffFilter, setDiffFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["questions", { search, topic: topicFilter, difficulty: diffFilter, status: statusFilter }],
    queryFn: () =>
      fetchQuestions({ search: search || undefined, topic: topicFilter || undefined, difficulty: diffFilter || undefined, status: statusFilter || undefined }),
  });

  const { data: topics } = useQuery({
    queryKey: ["topics"],
    queryFn: fetchTopics,
  });

  return (
    <>
      <div className="flex flex-col h-full">
        {/* Search + Filters */}
        <div className="p-4 space-y-3 border-b border-[#2a3f4a] shrink-0">
          <input
            type="text"
            placeholder="Search questions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[#1C2B33] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none focus:ring-2 focus:ring-[#58CC02]/50"
          />
          <div className="flex gap-2 overflow-x-auto pb-1">
            <select
              value={topicFilter}
              onChange={(e) => setTopicFilter(e.target.value)}
              className="bg-[#1C2B33] text-sm text-[#9CA3AF] rounded-lg px-3 py-1.5 outline-none"
            >
              <option value="">All Topics</option>
              {topics?.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <select
              value={diffFilter}
              onChange={(e) => setDiffFilter(e.target.value)}
              className="bg-[#1C2B33] text-sm text-[#9CA3AF] rounded-lg px-3 py-1.5 outline-none"
            >
              <option value="">All Levels</option>
              <option value="Easy">Easy</option>
              <option value="Medium">Medium</option>
              <option value="Hard">Hard</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-[#1C2B33] text-sm text-[#9CA3AF] rounded-lg px-3 py-1.5 outline-none"
            >
              <option value="">All Status</option>
              <option value="todo">Todo</option>
              <option value="in_progress">In Progress</option>
              <option value="done">Done</option>
              <option value="review">Review</option>
              <option value="rework">Rework</option>
            </select>
          </div>
        </div>

        {/* Question List — scrollable */}
        <div className="flex-1 overflow-y-auto">
          <div className="p-4 space-y-2 pb-36">
            {isLoading ? (
              <p className="text-center text-[#9CA3AF]">Loading...</p>
            ) : !data?.items.length ? (
              <div className="text-center py-12">
                <p className="text-[#9CA3AF]">No questions yet</p>
                <button
                  onClick={() => setShowImport(true)}
                  className="mt-3 text-[#FFC800] font-medium"
                >
                  Import questions with AI
                </button>
              </div>
            ) : (
              data.items.map((q) => (
                <button
                  key={q.id}
                  onClick={() => onSelectQuestion(q.id)}
                  className="w-full text-left bg-[#1C2B33] rounded-xl p-4 active:bg-[#243640] transition-colors"
                >
                  <div className="flex items-center gap-2 mb-1">
                    {q.number && <span className="text-[#9CA3AF] text-sm">#{q.number}</span>}
                    <span className={`text-xs px-1.5 py-0.5 rounded ${difficultyColor[q.difficulty] || ""}`}>
                      {q.difficulty}
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${statusColor[q.status] || ""}`}>
                      {q.status.replace("_", " ")}
                    </span>
                    {q.solution_count > 0 && (
                      <span className="text-xs text-[#58CC02]">{q.solution_count} sol</span>
                    )}
                  </div>
                  <p className="text-white font-medium">{q.title}</p>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span className="text-xs text-[#9CA3AF]">{q.topics?.join(", ")}</span>
                    {q.subtopics.slice(0, 3).map((st) => (
                      <span key={st} className="text-xs bg-[#243640] text-[#9CA3AF] px-1.5 py-0.5 rounded">
                        {st}
                      </span>
                    ))}
                  </div>
                </button>
              ))
            )}
          </div>

        </div>
      </div>

      {/* Floating actions */}
      <div className="fixed right-4 bottom-24 z-50 flex flex-col gap-3">
        <button
          onClick={() => setShowImport(true)}
          className="w-14 h-14 bg-[#FFC800] rounded-full flex items-center justify-center text-[#131F24] text-xl font-bold shadow-xl active:bg-[#e6b400]"
          title="Bulk Import"
          aria-label="Bulk import questions with AI"
        >
          AI
        </button>
        <button
          onClick={() => setShowForm(true)}
          className="w-14 h-14 bg-[#58CC02] rounded-full flex items-center justify-center text-white text-2xl shadow-xl active:bg-[#46a302]"
          title="Add One"
          aria-label="Add one question"
        >
          +
        </button>
      </div>

      {/* Modals — portaled to body so they render above everything */}
      {showForm && createPortal(
        <QuestionForm
          onClose={() => setShowForm(false)}
          onCreated={() => {
            setShowForm(false);
            queryClient.invalidateQueries({ queryKey: ["questions"] });
          }}
        />,
        document.body,
      )}

      {showImport && createPortal(
        <ImportDialog
          onClose={() => setShowImport(false)}
          onImported={() => {
            setShowImport(false);
            queryClient.invalidateQueries({ queryKey: ["questions"] });
            queryClient.invalidateQueries({ queryKey: ["topics"] });
          }}
        />,
        document.body,
      )}
    </>
  );
}

function QuestionForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [number, setNumber] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>("Medium");
  const [topic, setTopic] = useState("");
  const [subtopics, setSubtopics] = useState("");
  const [url, setUrl] = useState("");
  const [notes, setNotes] = useState("");

  const mutation = useMutation({
    mutationFn: (data: Parameters<typeof createQuestion>[0]) => createQuestion(data),
    onSuccess: onCreated,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      title,
      number: number ? parseInt(number) : undefined,
      difficulty,
      topics: topic ? topic.split(",").map((s) => s.trim()) : ["Uncategorized"],
      subtopics: subtopics ? subtopics.split(",").map((s) => s.trim()) : [],
      url: url || undefined,
      notes: notes || undefined,
    } as Partial<Question>);
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-[100] flex items-end">
      <div className="bg-[#1C2B33] rounded-t-2xl w-full max-h-[85vh] overflow-y-auto p-6 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-bold text-lg">Add Question</h3>
          <button onClick={onClose} className="text-[#9CA3AF] text-2xl">x</button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            placeholder="Title *"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none"
          />
          <div className="flex gap-3">
            <input
              placeholder="LC #"
              value={number}
              onChange={(e) => setNumber(e.target.value)}
              type="number"
              className="w-24 bg-[#243640] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none"
            />
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value as Difficulty)}
              className="bg-[#243640] rounded-lg px-4 py-2.5 text-white outline-none flex-1"
            >
              <option value="Easy">Easy</option>
              <option value="Medium">Medium</option>
              <option value="Hard">Hard</option>
            </select>
          </div>
          <input
            placeholder="Topic (e.g., Dynamic Programming)"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none"
          />
          <input
            placeholder="Subtopics (comma separated)"
            value={subtopics}
            onChange={(e) => setSubtopics(e.target.value)}
            className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none"
          />
          <input
            placeholder="LeetCode URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none"
          />
          <textarea
            placeholder="Notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none resize-none"
          />
          <button
            type="submit"
            disabled={!title || mutation.isPending}
            className="w-full bg-[#58CC02] text-white font-bold py-3 rounded-xl disabled:opacity-50 active:bg-[#46a302]"
          >
            {mutation.isPending ? "Adding..." : "Add Question"}
          </button>
          {mutation.isError && (
            <p className="text-red-400 text-sm">{(mutation.error as Error).message}</p>
          )}
        </form>
      </div>
    </div>
  );
}

function ImportDialog({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [questionText, setQuestionText] = useState("");
  const [result, setResult] = useState<{
    added: number;
    updated: number;
    skipped: number;
    questions: Question[];
  } | null>(null);

  const mutation = useMutation({
    mutationFn: () => {
      const fullText = prompt
        ? `${prompt}\n\n${questionText}`
        : questionText;
      return importQuestions(fullText);
    },
    onSuccess: (data) => setResult(data),
  });

  return (
    <div className="fixed inset-0 bg-black/60 z-[100] flex items-end">
      <div className="bg-[#1C2B33] rounded-t-2xl w-full max-h-[90vh] overflow-y-auto p-6 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-bold text-lg">AI Bulk Import</h3>
          <button onClick={onClose} className="text-[#9CA3AF] text-2xl">x</button>
        </div>

        {!result ? (
          <div className="space-y-4">
            <div>
              <label className="text-[#9CA3AF] text-sm mb-1.5 block">
                Context / Instructions for AI
              </label>
              <textarea
                placeholder='e.g. "These are Google past 3 months questions, default to Hard difficulty" or "Neetcode 150 list, Arrays section"'
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none resize-none text-sm"
              />
            </div>

            <div>
              <label className="text-[#9CA3AF] text-sm mb-1.5 block">
                Question List
              </label>
              <textarea
                placeholder={`Paste your questions in any format:\n\n1. Two Sum - Easy\n15. 3Sum\n42. Trapping Rain Water\n\nor just copy-paste from a website. AI will figure out the structure.`}
                value={questionText}
                onChange={(e) => setQuestionText(e.target.value)}
                rows={10}
                className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none resize-none text-sm font-mono"
              />
            </div>

            <p className="text-[#9CA3AF] text-xs">
              AI will extract question numbers, titles, difficulty, topics, and tags.
              Duplicates are automatically skipped or merged.
            </p>

            <button
              onClick={() => mutation.mutate()}
              disabled={!questionText.trim() || mutation.isPending}
              className="w-full bg-[#FFC800] text-[#131F24] font-bold py-3 rounded-xl disabled:opacity-50 active:bg-[#e6b400]"
            >
              {mutation.isPending ? "AI is parsing..." : "Import with AI"}
            </button>
            {mutation.isError && (
              <p className="text-red-400 text-sm">{(mutation.error as Error).message}</p>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1 bg-[#243640] rounded-lg p-3 text-center">
                <p className="text-[#58CC02] text-2xl font-bold">{result.added}</p>
                <p className="text-[#9CA3AF] text-xs">Added</p>
              </div>
              <div className="flex-1 bg-[#243640] rounded-lg p-3 text-center">
                <p className="text-[#FFC800] text-2xl font-bold">{result.updated}</p>
                <p className="text-[#9CA3AF] text-xs">Updated</p>
              </div>
              <div className="flex-1 bg-[#243640] rounded-lg p-3 text-center">
                <p className="text-[#9CA3AF] text-2xl font-bold">{result.skipped}</p>
                <p className="text-[#9CA3AF] text-xs">Skipped</p>
              </div>
            </div>

            <div className="space-y-2 max-h-[40vh] overflow-y-auto">
              {result.questions.map((q) => (
                <div key={q.id} className="bg-[#243640] rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    {q.number && <span className="text-[#9CA3AF] text-xs">#{q.number}</span>}
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      q.difficulty === "Easy" ? "bg-green-900/50 text-green-400" :
                      q.difficulty === "Hard" ? "bg-red-900/50 text-red-400" :
                      "bg-yellow-900/50 text-yellow-400"
                    }`}>{q.difficulty}</span>
                  </div>
                  <p className="text-white text-sm font-medium">{q.title}</p>
                  <p className="text-[#9CA3AF] text-xs mt-0.5">{q.topics?.join(", ")}</p>
                </div>
              ))}
            </div>

            <button
              onClick={onImported}
              className="w-full bg-[#58CC02] text-white font-bold py-3 rounded-xl active:bg-[#46a302]"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
