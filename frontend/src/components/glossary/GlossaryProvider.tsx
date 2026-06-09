import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchGlossaryTerm } from "../../api/glossary";
import { Markdown } from "../ui/Markdown";

const GlossaryContext = createContext<{ open: (term: string) => void }>({ open: () => {} });

export function useGlossary() {
  return useContext(GlossaryContext);
}

// Curated technique keywords that become clickable wherever they appear in drill text.
export const GLOSSARY_TERMS = [
  "Binary Search on Answer", "Binary Indexed Tree", "Monotonic Stack", "Monotonic Queue",
  "Topological Sort", "Union Find", "Sweep Line", "Merge Intervals", "Merge Sort", "Quickselect",
  "Reservoir Sampling", "Segment Tree", "Fenwick Tree", "Priority Queue", "Sliding Window",
  "Two Pointers", "Prefix Sum", "Difference Array", "Rolling Hash", "Dynamic Programming",
  "Memoization", "Backtracking", "Bit Manipulation", "Bitmask", "Binary Search", "Dijkstra",
  "Bellman-Ford", "Floyd-Warshall", "Kahn's Algorithm", "Kruskal", "Tarjan", "Greedy", "Trie",
  "Heap", "BFS", "DFS", "KMP",
].sort((a, b) => b.length - a.length); // longest first so phrases win over substrings

const TERM_REGEX = new RegExp(
  `\\b(${GLOSSARY_TERMS.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`,
  "gi"
);

function GlossaryModal({ term, onClose }: { term: string; onClose: () => void }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["glossary", term.toLowerCase()],
    queryFn: () => fetchGlossaryTerm(term),
    staleTime: Infinity,
  });

  return (
    <div className="fixed inset-0 z-[90]">
      <button className="absolute inset-0 bg-black/60" onClick={onClose} aria-label="Close" />
      <div className="absolute inset-x-0 bottom-0 sm:inset-0 sm:m-auto sm:max-w-lg sm:h-fit sm:max-h-[85vh] max-h-[85vh] overflow-y-auto bg-[#131F24] border border-[#2a3f4a] rounded-t-2xl sm:rounded-2xl shadow-2xl">
        <div className="sticky top-0 bg-[#131F24] border-b border-[#2a3f4a] px-4 py-3 flex items-center justify-between">
          <h2 className="text-white font-bold">{data?.name || term}</h2>
          <button onClick={onClose} className="text-[#9CA3AF] bg-[#1C2B33] rounded-lg px-3 py-1.5 text-sm active:text-white">
            Close
          </button>
        </div>
        <div className="p-4 space-y-4">
          {isLoading && <p className="text-sm text-[#9CA3AF]">Explaining “{term}”… this can take a few seconds.</p>}
          {isError && <p className="text-sm text-red-400">{(error as Error).message}</p>}
          {data && (
            <>
              <div>
                <p className="text-xs text-[#58CC02] font-medium mb-1">Definition</p>
                <p className="text-sm text-[#D1D5DB]">{data.definition}</p>
              </div>
              {data.how_it_works && (
                <div>
                  <p className="text-xs text-[#FFC800] font-medium mb-1">How it works</p>
                  <div className="text-sm text-[#D1D5DB]"><Markdown>{data.how_it_works}</Markdown></div>
                </div>
              )}
              {data.example && (
                <div>
                  <p className="text-xs text-[#38BDF8] font-medium mb-1">Example</p>
                  <div className="text-sm text-[#D1D5DB]"><Markdown>{data.example}</Markdown></div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function GlossaryProvider({ children }: { children: ReactNode }) {
  const [term, setTerm] = useState<string | null>(null);
  const value = useMemo(() => ({ open: (t: string) => setTerm(t) }), []);
  return (
    <GlossaryContext.Provider value={value}>
      {children}
      {term && <GlossaryModal term={term} onClose={() => setTerm(null)} />}
    </GlossaryContext.Provider>
  );
}

/** A clickable keyword chip/link that opens its glossary definition. */
export function Term({ name, className }: { name: string; className?: string }) {
  const { open } = useGlossary();
  return (
    <button
      onClick={() => open(name)}
      className={className ?? "underline decoration-dotted underline-offset-2 text-[#7DEB35] active:text-white"}
      title={`What is ${name}?`}
    >
      {name}
    </button>
  );
}

/** Renders plain text, turning any known glossary keyword into a clickable Term. */
export function LinkifyTerms({ text, className }: { text: string; className?: string }) {
  const { open } = useGlossary();
  if (!text) return null;
  const parts: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  TERM_REGEX.lastIndex = 0;
  let i = 0;
  while ((m = TERM_REGEX.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const matched = m[0];
    parts.push(
      <button
        key={`t-${i++}-${m.index}`}
        onClick={() => open(matched)}
        className="underline decoration-dotted underline-offset-2 text-[#7DEB35] active:text-white"
        title={`What is ${matched}?`}
      >
        {matched}
      </button>
    );
    last = m.index + matched.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <span className={className}>{parts}</span>;
}
