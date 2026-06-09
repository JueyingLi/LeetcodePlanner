import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStudyPlan } from "../../api/studyPlan";
import { useAuth } from "../../auth/AuthProvider";

export function Header({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { user, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const { data: plan } = useQuery({
    queryKey: ["studyPlan"],
    queryFn: fetchStudyPlan,
    refetchInterval: 60_000,
  });

  const d = plan?.days_until_interview ?? null;
  const h = plan?.hours_until_interview ?? 0;
  const m = plan?.minutes_until_interview ?? 0;

  const parts: string[] = [];
  if (d !== null && d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  parts.push(`${m}m`);
  const countdown = parts.join(" ");

  const email = user?.email ?? "";
  const initial = email ? email[0].toUpperCase() : "?";
  const avatarUrl = (user?.user_metadata?.avatar_url as string | undefined) ?? null;

  return (
    <header className="bg-[#1C2B33] px-4 py-3 flex items-center justify-between border-b border-[#2a3f4a] relative">
      <h1 className="text-lg font-bold text-[#58CC02]">LC Crasher</h1>

      <div className="flex items-center gap-3">
        {d !== null && (
          <div className="text-sm font-medium">
            <span className="text-[#FFC800]">{countdown}</span>
            <span className="text-[#9CA3AF] ml-1 hidden sm:inline">to interview</span>
          </div>
        )}

        <button
          onClick={() => setMenuOpen((v) => !v)}
          className="w-8 h-8 rounded-full bg-[#243640] overflow-hidden flex items-center justify-center text-sm text-white shrink-0"
          aria-label="Account menu"
        >
          {avatarUrl ? (
            <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
          ) : (
            initial
          )}
        </button>
      </div>

      {menuOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
          <div className="absolute right-4 top-14 z-50 bg-[#1C2B33] border border-[#2a3f4a] rounded-xl shadow-lg p-3 w-56">
            <p className="text-xs text-[#9CA3AF] mb-2 truncate">{email}</p>
            <button
              onClick={() => {
                setMenuOpen(false);
                onOpenSettings();
              }}
              className="w-full text-left text-sm text-white py-2 px-2 rounded-lg active:bg-[#243640]"
            >
              Settings
            </button>
            <button
              onClick={() => {
                setMenuOpen(false);
                signOut();
              }}
              className="w-full text-left text-sm text-[#FF4B4B] py-2 px-2 rounded-lg active:bg-[#243640]"
            >
              Sign out
            </button>
          </div>
        </>
      )}
    </header>
  );
}
