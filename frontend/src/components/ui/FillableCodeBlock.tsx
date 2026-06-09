import { useState, useEffect, useMemo, useRef } from "react";

const BLANK_MARKER = /\s*#\s*__BLANK__\s*$/;

export function shouldHideCodeLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return false;
  if (trimmed.startsWith("#")) return false;
  if (trimmed.endsWith(":") && !trimmed.includes("=")) return false;
  if (/^(class |def |"""|\'\'\')/.test(trimmed)) return false;
  return true;
}

function stripBlankMarker(line: string): string {
  return line.replace(BLANK_MARKER, "");
}

function tripleQuotedStringLineIndexes(lines: string[]): Set<number> {
  const indexes = new Set<number>();
  let activeQuote: `"""` | "'''" | null = null;

  lines.forEach((line, index) => {
    let isStringLine = activeQuote !== null;
    let pos = 0;

    while (pos < line.length) {
      const doubleIdx = line.indexOf('"""', pos);
      const singleIdx = line.indexOf("'''", pos);
      let nextIdx = -1;
      let quote: `"""` | "'''" | null = null;

      if (doubleIdx >= 0 && (singleIdx < 0 || doubleIdx < singleIdx)) {
        nextIdx = doubleIdx;
        quote = '"""';
      } else if (singleIdx >= 0) {
        nextIdx = singleIdx;
        quote = "'''";
      }

      if (nextIdx < 0 || !quote) break;
      isStringLine = true;

      if (activeQuote === null) {
        activeQuote = quote;
      } else if (activeQuote === quote) {
        activeQuote = null;
      }
      pos = nextIdx + 3;
    }

    if (isStringLine) indexes.add(index);
  });

  return indexes;
}

export function fillableLineIndexes(code: string): number[] {
  const hasMarkers = BLANK_MARKER.test(code);
  const rawLines = code.split("\n");
  const visibleLines = rawLines.map((line) => (hasMarkers ? stripBlankMarker(line) : line));
  const stringLineIndexes = tripleQuotedStringLineIndexes(visibleLines);
  if (hasMarkers) {
    return rawLines
      .map((line, i) => (BLANK_MARKER.test(line) && !stringLineIndexes.has(i) ? i : -1))
      .filter((i) => i >= 0);
  }
  return visibleLines
    .map((line, i) => (shouldHideCodeLine(line) && !stringLineIndexes.has(i) ? i : -1))
    .filter((i) => i >= 0);
}

function cleanInlineComment(comment: string, dropHash = false): string {
  const cleaned = stripBlankMarker(comment).trimEnd();
  return dropHash ? cleaned.replace(/^#\s*/, "") : cleaned;
}

interface LineParts {
  indent: string;
  code: string;
  comment: string;
}

function parseCodeLine(line: string): LineParts {
  const indent = line.match(/^\s*/)?.[0] || "";
  const rest = line.slice(indent.length);

  // Find inline comment: look for "  # " (2+ spaces then # then space)
  // But not at the very start (that's a comment-only line)
  const match = rest.match(/^(.+?)\s{2,}(#\s.+)$/);
  if (match) {
    return { indent, code: match[1].trimEnd(), comment: match[2] };
  }

  // Fallback: look for single space + # (less strict)
  const fallback = rest.match(/^(.+?)\s+(#\s.+)$/);
  if (fallback && !rest.startsWith("#")) {
    return { indent, code: fallback[1].trimEnd(), comment: fallback[2] };
  }

  return { indent, code: rest, comment: "" };
}

function fillTarget(parts: LineParts): { prefix: string; answer: string } {
  const { indent, code } = parts;
  // Try to split on assignment (but not ==, !=, <=, >=, +=, -=, etc.)
  const assignMatch = code.match(/^([^#\n]*?[^<>=!+\-*/%&|^~]\s*=\s)(.+)$/);
  if (assignMatch) {
    return { prefix: indent + assignMatch[1], answer: assignMatch[2].trim() };
  }
  return { prefix: indent, answer: code };
}

const normalizeCode = (s: string) => s.replace(/#.*$/, "").replace(/\s+/g, "").trim();

export function FillableCodeBlock({
  code,
  subtopicId,
  subtopicName,
  onStatusChange,
}: {
  code: string;
  subtopicId?: number;
  subtopicName?: string;
  onStatusChange?: (status: "in_progress" | "done") => void;
}) {
  const hasMarkers = BLANK_MARKER.test(code);
  const rawLines = code.split("\n");
  const lines = rawLines.map((l) => (hasMarkers ? stripBlankMarker(l) : l));
  const hiddenIndexes = useMemo(() => fillableLineIndexes(code), [code]);
  const [inputs, setInputs] = useState<Record<number, string>>({});
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [mistakes, setMistakes] = useState<Record<number, { analysis: string | null; weakness_tag: string | null }>>({});
  const [llmCorrect, setLlmCorrect] = useState<Set<number>>(new Set());
  const inputRefs = useRef<Record<number, HTMLInputElement | null>>({});

  useEffect(() => {
    setInputs({});
    setChecked(new Set());
    setRevealed(new Set());
    setMistakes({});
    setLlmCorrect(new Set());
  }, [code]);

  const evaluateStatus = (
    nextChecked: Set<number>,
    nextRevealed: Set<number>,
    _nextInputs: Record<number, string>,
  ) => {
    if (!onStatusChange) return;
    const allAnswered = hiddenIndexes.every((i) => nextChecked.has(i) || nextRevealed.has(i));
    if (allAnswered) {
      onStatusChange("done");
      return;
    }
    if (nextChecked.size > 0 || nextRevealed.size > 0) onStatusChange("in_progress");
  };

  const recordMistakeForLine = async (index: number, correct: string, userAnswer: string) => {
    if (!subtopicName) return;
    try {
      const { recordMistake } = await import("../../api/codeMistakes");
      const result = await recordMistake({
        subtopic_id: subtopicId ?? null,
        subtopic_name: subtopicName,
        correct_code: correct,
        user_code: userAnswer,
        context_line: code,
      });
      if (result.weakness_tag === "correct" || result.weakness_tag === "ignored_non_code") {
        setLlmCorrect((prev) => new Set(prev).add(index));
      } else {
        setMistakes((prev) => ({
          ...prev,
          [index]: { analysis: result.analysis, weakness_tag: result.weakness_tag },
        }));
      }
    } catch {
      // silently ignore
    }
  };

  const focusNextBlank = (currentIndex: number, nextChecked: Set<number>) => {
    const nextIdx = hiddenIndexes.find((i) => i > currentIndex && !nextChecked.has(i) && !revealed.has(i));
    if (nextIdx !== undefined) {
      setTimeout(() => inputRefs.current[nextIdx]?.focus(), 0);
    }
  };

  const checkLine = (index: number, userInput: string, actual: string) => {
    const nextChecked = new Set(checked).add(index);
    const nextInputs = { ...inputs, [index]: userInput };
    setChecked(nextChecked);
    if (normalizeCode(userInput) !== normalizeCode(actual)) {
      recordMistakeForLine(index, actual, userInput);
    }
    evaluateStatus(nextChecked, revealed, nextInputs);
    focusNextBlank(index, nextChecked);
  };

  const revealAll = () => {
    const next = new Set(hiddenIndexes);
    setRevealed(next);
    evaluateStatus(checked, next, inputs);
  };
  const reset = () => {
    setInputs({});
    setChecked(new Set());
    setRevealed(new Set());
    setMistakes({});
    setLlmCorrect(new Set());
    onStatusChange?.("in_progress");
  };

  if (hiddenIndexes.length === 0) {
    return (
      <pre className="bg-[#0E171B] p-4 overflow-x-auto text-xs text-green-300 whitespace-pre min-h-28">
        {lines.join("\n")}
      </pre>
    );
  }

  const answeredCount = hiddenIndexes.filter((i) => checked.has(i) || revealed.has(i)).length;

  return (
    <div className="bg-[#0E171B] min-h-28 rounded-xl overflow-hidden">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-[#18262D] px-3 py-2">
        <span className="text-xs text-[#9CA3AF]">
          {answeredCount}/{hiddenIndexes.length} blanks filled
        </span>
        <div className="flex gap-2">
          <button onClick={reset} className="text-xs text-[#9CA3AF] bg-[#18262D] rounded px-2 py-1 active:text-white">
            Reset all
          </button>
          <button onClick={revealAll} className="text-xs text-[#58CC02] bg-[#18262D] rounded px-2 py-1">
            Reveal all
          </button>
        </div>
      </div>
      <div className="overflow-x-auto p-4 font-mono text-xs space-y-1.5">
        {lines.map((line, index) => {
          const isHidden = hiddenIndexes.includes(index);
          const parts = parseCodeLine(line);
          const target = fillTarget(parts);
          const displayComment = cleanInlineComment(parts.comment);
          const isChecked = checked.has(index);
          const isRevealed = revealed.has(index);
          const actual = target.answer;
          const userInput = inputs[index] || "";
          const isCorrect = isChecked && (normalizeCode(userInput) === normalizeCode(actual) || llmCorrect.has(index));

          // Visible line (not hidden)
          if (!isHidden) {
            if (!line.trim()) {
              return <div key={`${index}-empty`} className="min-h-[1.25rem]">{" "}</div>;
            }
            // Render code and comment in different colors
            if (parts.comment) {
              return (
                <div key={`${index}-${line}`} className="min-h-[1.25rem] whitespace-pre">
                  <span className={parts.code.startsWith("#") ? "text-[#7C8B93]" : "text-green-300"}>
                    {parts.indent}{parts.code}
                  </span>
                  <span className="text-[#7C8B93]">{"  "}{displayComment}</span>
                </div>
              );
            }
            return (
              <div
                key={`${index}-${line}`}
                className={`min-h-[1.25rem] whitespace-pre ${
                  line.trim().startsWith("#") ? "text-[#7C8B93]" : "text-green-300"
                }`}
              >
                {line || " "}
              </div>
            );
          }

          // Revealed line
          if (isRevealed) {
            return (
              <div key={`${index}-${line}`} className="min-h-[1.25rem] whitespace-pre">
                <span className="text-green-300">{parts.indent}{parts.code}</span>
                {displayComment && <span className="text-[#7C8B93]">{"  "}{displayComment}</span>}
              </div>
            );
          }

          // Checked line (correct or wrong)
          if (isChecked) {
            const mistake = mistakes[index];
            return (
              <div key={`${index}-${line}`} className="min-h-[1.25rem]">
                <div className="whitespace-pre">
                  <span className="text-green-300">{target.prefix}</span>
                  {isCorrect ? (
                    <span className="text-[#58CC02]">{actual}</span>
                  ) : (
                    <>
                      <span className="text-[#FF4B4B] line-through">{userInput || "(empty)"}</span>
                      <span className="text-green-300 ml-3">{actual}</span>
                    </>
                  )}
                  {displayComment && <span className="text-[#7C8B93] ml-2">{displayComment}</span>}
                  <span className={`ml-2 font-sans text-xs ${isCorrect ? "text-[#58CC02]" : "text-[#FF8A8A]"}`}>
                    {isCorrect ? "✓" : ""}
                  </span>
                </div>
                {!isCorrect && mistake?.analysis && (
                  <div className="mt-1 ml-4 bg-[#FF4B4B]/10 rounded px-2 py-1.5 border-l-2 border-[#FF4B4B]/40">
                    <p className="text-xs text-[#FF8A8A]">{mistake.analysis}</p>
                    {mistake.weakness_tag && (
                      <span className="text-[10px] text-[#9CA3AF] mt-0.5 inline-block">
                        {mistake.weakness_tag.replace(/_/g, " ")}
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          }

          // Input line (not yet answered)
          const hint = cleanInlineComment(parts.comment, true);
          const inputWidth = Math.min(Math.max((hint.length || 16) + 4, 24), 96);
          return (
            <div
              key={`${index}-${line}`}
              className="min-w-max min-h-[1.25rem]"
            >
              <div className="flex items-center gap-2 whitespace-pre">
                <span className="text-green-300 shrink-0">{target.prefix}</span>
                <input
                  ref={(el) => { inputRefs.current[index] = el; }}
                  type="text"
                  value={userInput}
                  onChange={(e) => setInputs((prev) => ({ ...prev, [index]: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && userInput.trim()) {
                      checkLine(index, userInput, actual);
                    }
                  }}
                  placeholder={hint || "type the code"}
                  style={{ width: `${inputWidth}ch` }}
                  className="bg-[#18262D] text-[#FFC800] rounded px-2 py-0.5 outline-none font-mono text-xs w-56 sm:w-72 md:w-96 border border-[#2a3f4a] focus:border-[#818CF8]"
                />
                <button
                  onClick={() => checkLine(index, userInput, actual)}
                  disabled={!userInput.trim()}
                  className="ml-2 text-[#818CF8] bg-[#18262D] rounded px-2 py-0.5 font-sans disabled:opacity-30 shrink-0"
                >
                  Check
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
