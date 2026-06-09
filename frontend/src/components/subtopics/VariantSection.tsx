import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { generateVariant } from "../../api/subtopics";
import type { SubtopicInfo } from "../../types";
import { Markdown } from "../ui/Markdown";

export function parseVariantItems(text: string | null): { name: string; detail: string }[] {
  if (!text) return [];
  const bold = [...text.matchAll(/[-*]\s+\*\*(.+?)\*\*[:\s]*(.+)/g)];
  if (bold.length > 0) return bold.map((m) => ({ name: m[1].trim(), detail: m[2].trim() }));
  const colon = [...text.matchAll(/[-*]\s+(.+?):\s+(.+)/g)];
  if (colon.length > 0) return colon.map((m) => ({ name: m[1].trim(), detail: m[2].trim() }));
  return [];
}

const VARIANT_COLORS = [
  { bg: "bg-[#818CF8]/15", text: "text-[#C8C4FF]", border: "border-[#818CF8]/30", hover: "hover:bg-[#818CF8]/25" },
  { bg: "bg-[#F472B6]/15", text: "text-[#F9A8D4]", border: "border-[#F472B6]/30", hover: "hover:bg-[#F472B6]/25" },
  { bg: "bg-[#38BDF8]/15", text: "text-[#7DD3FC]", border: "border-[#38BDF8]/30", hover: "hover:bg-[#38BDF8]/25" },
  { bg: "bg-[#FFC800]/15", text: "text-[#FFE08A]", border: "border-[#FFC800]/30", hover: "hover:bg-[#FFC800]/25" },
  { bg: "bg-[#34D399]/15", text: "text-[#6EE7B7]", border: "border-[#34D399]/30", hover: "hover:bg-[#34D399]/25" },
];

export function VariantSection({
  subtopic,
  variantsText,
  onOpenVariant,
  studiedIds,
  knownSubtopics,
}: {
  subtopic: SubtopicInfo;
  variantsText?: string | null;
  onOpenVariant?: (id: number) => void;
  studiedIds?: Set<number>;
  knownSubtopics?: SubtopicInfo[];
}) {
  const queryClient = useQueryClient();
  const [generatingName, setGeneratingName] = useState<string | null>(null);
  const variants = parseVariantItems(variantsText ?? subtopic.variants);

  const genMut = useMutation({
    mutationFn: (variantName: string) => generateVariant(subtopic.id, variantName),
    onMutate: (name) => setGeneratingName(name),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["subtopics"] });
      queryClient.invalidateQueries({ queryKey: ["subtopic", subtopic.id] });
      onOpenVariant?.(data.id);
    },
    onSettled: () => setGeneratingName(null),
  });

  const normalizeName = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const generatedMap = new Map<string, { id: number; name: string; slug?: string | null }>();
  const addKnown = (item: { id: number; name: string; slug?: string | null } | null | undefined) => {
    if (!item || item.id === subtopic.id) return;
    const key = normalizeName(item.name);
    if (key) generatedMap.set(key, item);
  };
  for (const child of subtopic.variant_children || []) addKnown(child);
  for (const known of knownSubtopics || []) {
    addKnown(known);
    for (const child of known.variant_children || []) addKnown(child);
  }

  type VariantEntry = { name: string; detail: string; childId: number | null };
  const merged: VariantEntry[] = [];
  const seen = new Set<string>();

  for (const v of variants) {
    const child = generatedMap.get(normalizeName(v.name));
    merged.push({ name: v.name, detail: v.detail, childId: child?.id ?? null });
    seen.add(v.name.toLowerCase());
  }
  for (const c of subtopic.variant_children || []) {
    if (!seen.has(c.name.toLowerCase())) {
      merged.push({ name: c.name, detail: "", childId: c.id });
    }
  }

  if (merged.length === 0 && !subtopic.variants) return null;

  return (
    <div className="bg-[#1C2B33] rounded-lg p-3 space-y-2">
      <h3 className="text-[#818CF8] font-bold text-[11px] uppercase tracking-wide">
        Variants
      </h3>

      {merged.length > 0 ? (
        <div className="space-y-2">
          {merged.map((v, i) => {
            const color = VARIANT_COLORS[i % VARIANT_COLORS.length];
            const isGenerating = generatingName === v.name;

            if (v.childId != null) {
              const isStudied = studiedIds?.has(v.childId) || false;
              if (!onOpenVariant) {
                return (
                  <div
                    key={v.childId}
                    className={`w-full text-left ${color.bg} ${color.text} border ${color.border} rounded-lg p-2.5`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium flex-1">{v.name}</span>
                      {isStudied && (
                        <span className="text-[10px] rounded-full bg-[#58CC02]/20 text-[#58CC02] px-2 py-0.5">
                          Done
                        </span>
                      )}
                    </div>
                    {v.detail && <p className="text-[11px] opacity-70 mt-1">{v.detail}</p>}
                  </div>
                );
              }

              return (
                <button
                  key={v.childId}
                  onClick={() => onOpenVariant(v.childId!)}
                  className={`w-full text-left ${color.bg} ${color.text} border ${color.border} ${color.hover} rounded-lg p-2.5 transition-colors`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium flex-1">{v.name}</span>
                    {isStudied && (
                      <span className="text-[10px] rounded-full bg-[#58CC02]/20 text-[#58CC02] px-2 py-0.5">
                        Done
                      </span>
                    )}
                    <span className="text-xs opacity-60">&rsaquo;</span>
                  </div>
                  {v.detail && <p className="text-[11px] opacity-70 mt-1">{v.detail}</p>}
                </button>
              );
            }

            return (
              <div
                key={`ungen-${i}`}
                className="bg-[#131F24] border border-[#2a3f4a] rounded-lg p-2.5"
              >
                <div className="flex items-center gap-2">
                  <p className="text-white text-xs font-medium flex-1">{v.name}</p>
                  <button
                    onClick={() => genMut.mutate(v.name)}
                    disabled={genMut.isPending}
                    className={`text-[10px] px-2.5 py-1 rounded-full ${color.bg} ${color.text} border ${color.border} ${color.hover} disabled:opacity-50`}
                  >
                    {isGenerating ? "Generating..." : "Generate"}
                  </button>
                </div>
                {v.detail && <p className="text-xs text-[#9CA3AF] mt-1">{v.detail}</p>}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-[#D1D5DB]">
          <Markdown>{subtopic.variants || ""}</Markdown>
        </div>
      )}

      {genMut.isError && (
        <p className="text-xs text-[#FF8A8A] mt-1">{(genMut.error as Error).message}</p>
      )}
    </div>
  );
}
