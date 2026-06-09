export type Tab = "study" | "questions" | "patterns" | "quiz";

const tabs: { id: Tab; label: string; icon: string }[] = [
  { id: "study", label: "Study", icon: "📚" },
  { id: "questions", label: "Questions", icon: "📋" },
  { id: "patterns", label: "Topic", icon: "🔗" },
  { id: "quiz", label: "Quiz", icon: "✏️" },
];

export function BottomNav({
  active,
  onChange,
}: {
  active: Tab;
  onChange: (tab: Tab) => void;
}) {
  return (
    <nav className="shrink-0 bg-[#1C2B33] border-t border-[#2a3f4a] flex justify-around py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] z-50">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`flex flex-col items-center gap-0.5 px-3 py-1 text-xs transition-colors ${
            active === t.id
              ? "text-[#58CC02]"
              : "text-[#9CA3AF] active:text-white"
          }`}
        >
          <span className="text-lg">{t.icon}</span>
          <span>{t.label}</span>
        </button>
      ))}
    </nav>
  );
}
