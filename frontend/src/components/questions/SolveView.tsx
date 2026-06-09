import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Markdown } from "../ui/Markdown";
import { FillableCodeBlock } from "../ui/FillableCodeBlock";
import {
  fetchAttempts,
  createAttempt,
  updateAttempt,
  requestFeedback,
  deleteFeedback,
} from "../../api/attempts";
import { generateSolutions } from "../../api/solutions";
import type { Solution, UserAttempt, StepFeedback } from "../../types";


const STEPS = [
  { key: "observation", label: "Data Characteristics", placeholder: "What does the data look like? What are its structural properties and access patterns?" },
  { key: "approach", label: "Approach & Reasoning", placeholder: "What data structure/algorithm will you use and why does it fit this data?" },
  { key: "code", label: "Code", placeholder: "Write your solution code here..." },
] as const;

function extractCodeStub(code: string): string {
  const lines = code.split("\n");
  const stub: string[] = [];
  let inBody = false;
  for (const line of lines) {
    const trimmed = line.trimStart();
    if (trimmed.startsWith("class ") || trimmed.startsWith("def ")) {
      if (inBody) stub.push("");
      stub.push(line);
      inBody = true;
    } else if (inBody && (trimmed.startsWith('"""') || trimmed.startsWith("'''"))) {
      stub.push(line);
    } else if (inBody && trimmed === "") {
      continue;
    } else if (!inBody) {
      stub.push(line);
    }
  }
  if (stub.length > 0) {
    stub.push("        # Write your solution here");
    stub.push("");
  }
  return stub.join("\n");
}

function buildWriteStub(code: string): string {
  const lines = code.split("\n");
  const stub: string[] = [];
  for (const line of lines) {
    const trimmed = line.trimStart();
    const indent = line.match(/^(\s*)/)?.[0] || "";
    if (trimmed.startsWith("class ")) {
      stub.push(line);
    } else if (trimmed.startsWith("def ")) {
      stub.push(line);
      const match = trimmed.match(/def \w+\((self,?\s*)?(.*?)\)\s*(?:->\s*(.+?))?:/);
      if (match) {
        const params = match[2]?.trim();
        const returnType = match[3]?.trim();
        if (params) stub.push(`${indent}    # Input: ${params}`);
        if (returnType) stub.push(`${indent}    # Output: ${returnType}`);
      }
      stub.push(`${indent}    pass`);
      stub.push("");
    }
  }
  return stub.join("\n");
}

function FeedbackBadge({ fb, stepLabel, onDelete }: { fb: StepFeedback; stepLabel: string; onDelete?: () => void }) {
  const [collapsed, setCollapsed] = useState(true);
  const color =
    fb.score && fb.score >= 4
      ? "bg-[#58CC02]/20 text-[#58CC02]"
      : fb.score && fb.score >= 3
        ? "bg-[#FFC800]/20 text-[#FFC800]"
        : "bg-[#FF4B4B]/20 text-[#FF4B4B]";
  return (
    <div className={`rounded-lg mt-2 ${color}`}>
      <div className="flex items-center justify-between px-3 py-2 cursor-pointer" onClick={() => setCollapsed(!collapsed)}>
        <span className="text-xs font-bold">
          {collapsed ? `Feedback for ${stepLabel} — ${fb.score}/5 ▸` : `Score: ${fb.score}/5 ▾`}
        </span>
        {onDelete && (
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="opacity-60 hover:opacity-100 text-xs ml-2"
          >✕</button>
        )}
      </div>
      {!collapsed && (
        <div className="px-3 pb-3">
          <Markdown>{fb.feedback}</Markdown>
          {fb.suggestions.length > 0 && (
            <ul className="mt-2 space-y-1">
              {fb.suggestions.map((s, i) => (
                <li key={i} className="text-xs opacity-80">• {s}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function SolveView({
  questionId,
  subtopicName,
  onStatusChange,
  activeSolution,
  isReview = false,
}: {
  questionId: number;
  questionTitle: string;
  questionDescription: string | null;
  subtopicName?: string;
  onStatusChange?: (status: "in_progress" | "done" | "rework") => void;
  activeSolution?: Solution | null;
  isReview?: boolean;
}) {
  const queryClient = useQueryClient();
  const [attempt, setAttempt] = useState<UserAttempt | null>(null);
  const [observation, setObservation] = useState("");
  const [approach, setApproach] = useState("");
  const [code, setCode] = useState("");
  const [timeCx, setTimeCx] = useState("");
  const [spaceCx, setSpaceCx] = useState("");
  const [dirty, setDirty] = useState(false);
  const [revealedAnswers, setRevealedAnswers] = useState<Set<string>>(new Set());
  const [codeMode, setCodeMode] = useState<"write" | "fill">("fill");
  const [stepByStepOpen, setStepByStepOpen] = useState(false);
  const [edgeCasesOpen, setEdgeCasesOpen] = useState(false);
  const [revealAll, setRevealAll] = useState(false);

  const { data: attempts } = useQuery({
    queryKey: ["attempts", questionId],
    queryFn: () => fetchAttempts(questionId),
  });

  const optimal = activeSolution ?? null;

  const createMut = useMutation({
    mutationFn: () => createAttempt(questionId),
    onSuccess: (a) => {
      setAttempt(a);
      setObservation("");
      setApproach("");
      setCode(isReview ? codeStub : writeStub);
      setTimeCx("");
      setSpaceCx("");
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: ["attempts", questionId] });
    },
  });

  const saveMut = useMutation({
    mutationFn: (data: Partial<UserAttempt>) =>
      updateAttempt(questionId, attempt!.id, data),
    onSuccess: (a) => {
      setAttempt(a);
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: ["attempts", questionId] });
    },
  });

  const feedbackMut = useMutation({
    mutationFn: (step: string | null) =>
      requestFeedback(questionId, attempt!.id, step),
    onSuccess: (fb) => {
      if (attempt) {
        const updated = {
          ...attempt,
          ai_feedback: { ...(attempt.ai_feedback || {}), [fb.step]: fb },
        };
        setAttempt(updated);
      }
      queryClient.invalidateQueries({ queryKey: ["attempts", questionId] });
      if (onStatusChange && (fb.step === "code" || fb.step === "full") && fb.score != null) {
        onStatusChange(fb.score >= 4 ? "done" : "rework");
      }
    },
  });

  const delFeedbackMut = useMutation({
    mutationFn: (step: string) => deleteFeedback(questionId, attempt!.id, step),
    onSuccess: (_result, step) => {
      if (attempt) {
        const updated = { ...attempt, ai_feedback: { ...(attempt.ai_feedback || {}) } };
        delete (updated.ai_feedback as Record<string, unknown>)[step];
        setAttempt(updated);
      }
      queryClient.invalidateQueries({ queryKey: ["attempts", questionId] });
    },
  });

  const genSolMut = useMutation({
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

  const codeStub = activeSolution?.code ? extractCodeStub(activeSolution.code) : "";
  const writeStub = activeSolution?.code ? buildWriteStub(activeSolution.code) : "";

  useEffect(() => {
    if (attempts && attempts.length > 0 && !attempt) {
      const latest = attempts[0];
      setAttempt(latest);
      setObservation(latest.observation || "");
      setApproach(latest.approach || "");
      setCode(latest.code || (isReview ? codeStub : writeStub));
      setTimeCx(latest.time_complexity || "");
      setSpaceCx(latest.space_complexity || "");
    }
  }, [attempts, attempt]);

  const handleSave = useCallback(() => {
    if (!attempt) return;
    saveMut.mutate({
      observation: observation || undefined,
      approach: approach || undefined,
      code: code || undefined,
      time_complexity: timeCx || undefined,
      space_complexity: spaceCx || undefined,
    });
  }, [attempt, observation, approach, code, timeCx, spaceCx]);

  const handleFeedback = (step: string | null) => {
    if (!attempt) return;
    if (dirty) {
      saveMut.mutate(
        {
          observation: observation || undefined,
          approach: approach || undefined,
          code: code || undefined,
          time_complexity: timeCx || undefined,
          space_complexity: spaceCx || undefined,
        },
        { onSuccess: () => feedbackMut.mutate(step) }
      );
    } else {
      feedbackMut.mutate(step);
    }
  };

  const feedback = attempt?.ai_feedback as Record<string, StepFeedback> | null;

  const referenceForStep = (stepKey: string): string | null => {
    if (!optimal) return null;
    switch (stepKey) {
      case "observation": return optimal.initial_observation || null;
      case "approach": return optimal.approach_reasoning || null;
      case "code": return optimal.code || null;
      default: return null;
    }
  };
  const toggleAnswer = (key: string) =>
    setRevealedAnswers((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  // Auto-create attempt in review mode so user lands on the review layout immediately
  useEffect(() => {
    if (isReview && !attempt && attempts !== undefined && !createMut.isPending) {
      createMut.mutate();
    }
  }, [isReview, attempt, attempts]);

  if (!attempt) {
    if (isReview) {
      return <p className="text-sm text-[#9CA3AF]">Loading review...</p>;
    }
    return (
      <div className="space-y-4">
        {attempts && attempts.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm text-[#9CA3AF]">Previous attempts ({attempts.length})</p>
            {attempts.map((a) => (
              <button
                key={a.id}
                onClick={() => {
                  setAttempt(a);
                  setObservation(a.observation || "");
                  setApproach(a.approach || "");
                  setCode(a.code || "");
                  setTimeCx(a.time_complexity || "");
                  setSpaceCx(a.space_complexity || "");
                  setDirty(false);
                }}
                className="w-full text-left bg-[#1C2B33] rounded-lg p-3 text-sm active:bg-[#243640]"
              >
                <span className="text-white">
                  {new Date(a.created_at).toLocaleDateString()}
                </span>
                {a.ai_feedback && (
                  <span className="text-[#58CC02] ml-2 text-xs">has feedback</span>
                )}
              </button>
            ))}
          </div>
        )}
        <button
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending}
          className="w-full bg-[#58CC02] text-white font-bold py-3 rounded-xl active:bg-[#46a302] disabled:opacity-50"
        >
          {createMut.isPending ? "Creating..." : "Start New Attempt"}
        </button>
      </div>
    );
  }

  const codeFeedback = feedback?.code;
  const fullFeedback = feedback?.full;

  const codeBlock = (
    <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium text-white">Code</h4>
        <div className="flex gap-1.5">
          {referenceForStep("code") && (
            <button
              onClick={() => toggleAnswer("code")}
              className={`text-[10px] px-2 py-0.5 rounded-lg font-medium ${
                revealedAnswers.has("code")
                  ? "bg-[#818CF8]/20 text-[#818CF8]"
                  : "bg-[#818CF8]/10 text-[#818CF8]"
              }`}
            >
              {revealedAnswers.has("code") ? "Hide Answer" : "Show Answer"}
            </button>
          )}
          <button
            onClick={() => handleFeedback("code")}
            disabled={feedbackMut.isPending || !code}
            className="text-[10px] bg-[#FFC800] text-[#131F24] px-2 py-0.5 rounded-lg font-medium disabled:opacity-50"
          >
            {feedbackMut.isPending && feedbackMut.variables === "code" ? "..." : "AI Feedback"}
          </button>
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg overflow-hidden border border-[#2a3f4a]">
            <button
              onClick={() => setCodeMode("fill")}
              disabled={!optimal?.code}
              className={`px-3 py-1.5 text-xs font-medium disabled:opacity-30 ${codeMode === "fill" ? "bg-[#818CF8] text-white" : "bg-[#243640] text-[#9CA3AF]"}`}
            >
              Fill in
            </button>
            <button
              onClick={() => setCodeMode("write")}
              className={`px-3 py-1.5 text-xs font-medium ${codeMode === "write" ? "bg-[#58CC02] text-white" : "bg-[#243640] text-[#9CA3AF]"}`}
            >
              Write
            </button>
          </div>
          <button
            onClick={() => genSolMut.mutate()}
            disabled={genSolMut.isPending}
            className="text-xs text-[#9CA3AF] active:text-white disabled:opacity-50"
          >
            {genSolMut.isPending ? "Regenerating..." : "Regenerate"}
          </button>
          {codeMode === "write" && (
            <button
              onClick={() => { setCode(isReview ? codeStub : writeStub); setDirty(true); }}
              className="text-xs text-[#9CA3AF] active:text-white"
            >
              Reset
            </button>
          )}
        </div>
        {(codeMode === "fill" && optimal?.code) ? (
          <FillableCodeBlock
            code={optimal.fill_in_code || optimal.code}
            subtopicName={subtopicName}
            onStatusChange={onStatusChange}
          />
        ) : (
          <textarea
            value={code}
            onChange={(e) => { setCode(e.target.value); setDirty(true); }}
            placeholder="Write your solution code here..."
            rows={8}
            className="w-full bg-[#243640] text-white rounded-lg px-3 py-2 text-sm placeholder-[#9CA3AF]/50 resize-y focus:outline-none focus:ring-1 focus:ring-[#58CC02] font-mono"
          />
        )}
      </div>
      {revealedAnswers.has("code") && referenceForStep("code") && (
        <div className="bg-[#818CF8]/10 rounded-lg p-3 mt-2 border border-[#818CF8]/20">
          <p className="text-xs text-[#818CF8] font-medium mb-1">
            Reference Answer{optimal?.is_optimal ? " (Optimal)" : ""}
          </p>
          <pre className="text-sm font-mono whitespace-pre-wrap overflow-x-auto">
            {(referenceForStep("code") || "").split("\n").map((line, i) => {
              const cidx = line.search(/\s{2}#\s/);
              if (cidx >= 0) return <span key={i}><span className="text-green-300">{line.slice(0, cidx)}</span><span className="text-[#7C8B93]">{line.slice(cidx)}</span>{"\n"}</span>;
              return <span key={i} className={line.trim().startsWith("#") ? "text-[#7C8B93]" : "text-green-300"}>{line}{"\n"}</span>;
            })}
          </pre>
        </div>
      )}
      {codeFeedback && (
        <FeedbackBadge fb={codeFeedback} stepLabel="Code" onDelete={() => delFeedbackMut.mutate("code")} />
      )}
      {feedbackMut.isError && feedbackMut.variables === "code" && (
        <p className="text-red-400 text-xs mt-1">{(feedbackMut.error as Error).message}</p>
      )}
    </div>
  );

  const complexityBlock = (
    <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium text-white">Complexity</h4>
        <button
          onClick={() => handleFeedback("complexity")}
          disabled={feedbackMut.isPending || !(timeCx || spaceCx)}
          className="text-[10px] bg-[#FFC800] text-[#131F24] px-2 py-0.5 rounded-lg font-medium disabled:opacity-50"
        >
          {feedbackMut.isPending && feedbackMut.variables === "complexity" ? "..." : "AI Feedback"}
        </button>
      </div>
      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs text-[#9CA3AF]">Time</label>
          <input
            value={timeCx}
            onChange={(e) => { setTimeCx(e.target.value); setDirty(true); }}
            placeholder="O(n log n)"
            className="w-full bg-[#243640] text-white rounded-lg px-3 py-2 text-sm placeholder-[#9CA3AF]/50 focus:outline-none focus:ring-1 focus:ring-[#58CC02]"
          />
        </div>
        <div className="flex-1">
          <label className="text-xs text-[#9CA3AF]">Space</label>
          <input
            value={spaceCx}
            onChange={(e) => { setSpaceCx(e.target.value); setDirty(true); }}
            placeholder="O(n)"
            className="w-full bg-[#243640] text-white rounded-lg px-3 py-2 text-sm placeholder-[#9CA3AF]/50 focus:outline-none focus:ring-1 focus:ring-[#58CC02]"
          />
        </div>
      </div>
      {feedback?.complexity && (
        <FeedbackBadge fb={feedback.complexity} stepLabel="Complexity" onDelete={() => delFeedbackMut.mutate("complexity")} />
      )}
    </div>
  );

  if (isReview) {
    return (
      <div className="space-y-4">
        {codeBlock}
        {complexityBlock}

        {/* Action buttons */}
        <div className="flex gap-2">
          <button
            onClick={handleSave}
            disabled={saveMut.isPending || !dirty}
            className="flex-1 bg-[#58CC02] text-white font-bold py-3 rounded-xl active:bg-[#46a302] disabled:opacity-50"
          >
            {saveMut.isPending ? "Saving..." : "Save"}
          </button>
          <button
            onClick={() => handleFeedback(null)}
            disabled={feedbackMut.isPending}
            className="flex-1 bg-[#FFC800] text-[#131F24] font-bold py-3 rounded-xl disabled:opacity-50"
          >
            {feedbackMut.isPending && feedbackMut.variables === null ? "Reviewing..." : "Full Review"}
          </button>
        </div>

        {fullFeedback && (
          <FeedbackBadge fb={fullFeedback} stepLabel="Full Review" onDelete={() => delFeedbackMut.mutate("full")} />
        )}

        {/* Reveal All */}
        <button
          onClick={() => setRevealAll(!revealAll)}
          className={`w-full text-sm font-medium py-2 rounded-xl ${
            revealAll
              ? "bg-[#818CF8]/20 text-[#818CF8]"
              : "bg-[#1C2B33] text-[#9CA3AF]"
          }`}
        >
          {revealAll ? "Hide Study Notes ▾" : "Reveal All ▸"}
        </button>

        {revealAll && (
          <div className="space-y-4">
            {optimal?.initial_observation && (
              <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2">
                <h4 className="text-xs font-medium text-white">Data Characteristics</h4>
                <div className="text-sm text-[#D1D5DB]">
                  <Markdown>{optimal.initial_observation}</Markdown>
                </div>
              </div>
            )}
            {optimal?.approach_reasoning && (
              <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2">
                <h4 className="text-xs font-medium text-white">Approach & Reasoning</h4>
                <div className="text-sm text-[#D1D5DB]">
                  <Markdown>{optimal.approach_reasoning}</Markdown>
                </div>
              </div>
            )}
            {activeSolution?.step_by_step && (
              <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2">
                <h4 className="text-xs font-medium text-white">Step by Step</h4>
                <div className="text-sm text-[#D1D5DB]">
                  <Markdown>{activeSolution.step_by_step}</Markdown>
                </div>
              </div>
            )}
            {activeSolution && activeSolution.edge_cases.length > 0 && (
              <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2">
                <h4 className="text-xs font-medium text-white">Edge Cases</h4>
                <div className="space-y-2">
                  {activeSolution.edge_cases.map((ec, i) => (
                    <div key={i} className="bg-[#243640] rounded-lg p-3">
                      <p className="text-white text-sm font-medium">{ec.case}</p>
                      <p className="text-[#9CA3AF] text-sm mt-1">{ec.reasoning}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {optimal?.code && (
              <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2">
                <h4 className="text-xs font-medium text-white">Full Solution</h4>
                <pre className="text-sm font-mono whitespace-pre-wrap overflow-x-auto bg-[#131F24] rounded-lg p-3">
                  {optimal.code.split("\n").map((line, i) => {
                    const cidx = line.search(/\s{2}#\s/);
                    if (cidx >= 0) return <span key={i}><span className="text-green-300">{line.slice(0, cidx)}</span><span className="text-[#7C8B93]">{line.slice(cidx)}</span>{"\n"}</span>;
                    return <span key={i} className={line.trim().startsWith("#") ? "text-[#7C8B93]" : "text-green-300"}>{line}{"\n"}</span>;
                  })}
                </pre>
              </div>
            )}
          </div>
        )}

        {feedbackMut.isError && feedbackMut.variables === null && (
          <p className="text-red-400 text-sm">{(feedbackMut.error as Error).message}</p>
        )}
      </div>
    );
  }

  // Study mode
  return (
    <div className="space-y-4">
      {/* Observation */}
      {STEPS.filter((s) => s.key !== "code").map((step) => {
        const stepFeedback = feedback?.[step.key];
        const val = step.key === "observation" ? observation : approach;
        return (
          <div key={step.key}>
            <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-medium text-white">{step.label}</h4>
                <div className="flex gap-1.5">
                  {referenceForStep(step.key) && (
                    <button
                      onClick={() => toggleAnswer(step.key)}
                      className={`text-[10px] px-2 py-0.5 rounded-lg font-medium ${
                        revealedAnswers.has(step.key)
                          ? "bg-[#818CF8]/20 text-[#818CF8]"
                          : "bg-[#818CF8]/10 text-[#818CF8]"
                      }`}
                    >
                      {revealedAnswers.has(step.key) ? "Hide Answer" : "Show Answer"}
                    </button>
                  )}
                  <button
                    onClick={() => handleFeedback(step.key)}
                    disabled={feedbackMut.isPending || !val}
                    className="text-[10px] bg-[#FFC800] text-[#131F24] px-2 py-0.5 rounded-lg font-medium disabled:opacity-50"
                  >
                    {feedbackMut.isPending && feedbackMut.variables === step.key ? "..." : "AI Feedback"}
                  </button>
                </div>
              </div>
              <textarea
                value={val}
                onChange={(e) => {
                  setDirty(true);
                  if (step.key === "observation") setObservation(e.target.value);
                  else setApproach(e.target.value);
                }}
                placeholder={step.placeholder}
                rows={3}
                className="w-full bg-[#243640] text-white rounded-lg px-3 py-2 text-sm placeholder-[#9CA3AF]/50 resize-y focus:outline-none focus:ring-1 focus:ring-[#58CC02]"
              />
              {revealedAnswers.has(step.key) && referenceForStep(step.key) && (
                <div className="bg-[#818CF8]/10 rounded-lg p-3 mt-2 border border-[#818CF8]/20">
                  <p className="text-xs text-[#818CF8] font-medium mb-1">
                    Reference Answer{optimal?.is_optimal ? " (Optimal)" : ""}
                  </p>
                  <div className="text-sm text-[#D1D5DB]">
                    <Markdown>{referenceForStep(step.key)!}</Markdown>
                  </div>
                </div>
              )}
              {stepFeedback && (
                <FeedbackBadge fb={stepFeedback} stepLabel={step.label} onDelete={() => delFeedbackMut.mutate(step.key)} />
              )}
              {feedbackMut.isError && feedbackMut.variables === step.key && (
                <p className="text-red-400 text-xs mt-1">{(feedbackMut.error as Error).message}</p>
              )}
            </div>

            {/* Step by Step — after approach */}
            {step.key === "approach" && activeSolution?.step_by_step && (
              <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2 mt-4">
                <button
                  onClick={() => setStepByStepOpen(!stepByStepOpen)}
                  className="flex items-center justify-between w-full"
                >
                  <h4 className="text-xs font-medium text-white">Step by Step</h4>
                  <span className="text-xs text-[#9CA3AF]">{stepByStepOpen ? "▾" : "▸"}</span>
                </button>
                {stepByStepOpen && (
                  <div className="text-sm text-[#D1D5DB]">
                    <Markdown>{activeSolution.step_by_step}</Markdown>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {codeBlock}

      {/* Edge Cases — after code */}
      {activeSolution && activeSolution.edge_cases.length > 0 && (
        <div className="bg-[#1C2B33] rounded-xl p-3 space-y-2">
          <button
            onClick={() => setEdgeCasesOpen(!edgeCasesOpen)}
            className="flex items-center justify-between w-full"
          >
            <h4 className="text-xs font-medium text-[#FFC800]">Edge Cases</h4>
            <span className="text-xs text-[#9CA3AF]">{edgeCasesOpen ? "▾" : "▸"}</span>
          </button>
          {edgeCasesOpen && (
            <div className="space-y-2">
              {activeSolution.edge_cases.map((ec, i) => (
                <div key={i} className="bg-[#243640] rounded-lg p-3">
                  <p className="text-white text-sm font-medium">{ec.case}</p>
                  <p className="text-[#9CA3AF] text-sm mt-1">{ec.reasoning}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saveMut.isPending || !dirty}
          className="flex-1 bg-[#58CC02] text-white font-bold py-3 rounded-xl active:bg-[#46a302] disabled:opacity-50"
        >
          {saveMut.isPending ? "Saving..." : "Save"}
        </button>
        <button
          onClick={() => handleFeedback(null)}
          disabled={feedbackMut.isPending}
          className="flex-1 bg-[#FFC800] text-[#131F24] font-bold py-3 rounded-xl disabled:opacity-50"
        >
          {feedbackMut.isPending && feedbackMut.variables === null ? "Reviewing..." : "Full Review"}
        </button>
      </div>

      {fullFeedback && (
        <FeedbackBadge fb={fullFeedback} stepLabel="Full Review" onDelete={() => delFeedbackMut.mutate("full")} />
      )}
      {feedbackMut.isError && feedbackMut.variables === null && (
        <p className="text-red-400 text-sm">{(feedbackMut.error as Error).message}</p>
      )}
    </div>
  );
}
