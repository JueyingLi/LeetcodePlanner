import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BottomNav, type Tab } from "./components/layout/BottomNav";
import { Header } from "./components/layout/Header";
import { DailyPlan } from "./components/scheduler/DailyPlan";
import { ProgressDashboard } from "./components/scheduler/ProgressDashboard";
import { QuestionList } from "./components/questions/QuestionList";
import { QuestionDetail } from "./components/questions/QuestionDetail";
import { QuizSession } from "./components/quiz/QuizSession";
import { SettingsPage } from "./components/settings/SettingsPage";
import { SubtopicBrowser } from "./components/subtopics/SubtopicBrowser";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { LoginScreen } from "./auth/LoginScreen";
import { GlossaryProvider } from "./components/glossary/GlossaryProvider";
import { initSync } from "./offline/sync";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

function AppContent() {
  const [tab, setTab] = useState<Tab>("study");
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);
  const [studyQuestionId, setStudyQuestionId] = useState<number | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [studyDetailOpen, setStudyDetailOpen] = useState(false);

  // Flush any quiz answers recorded offline once we're authenticated/online.
  useEffect(() => initSync(), []);

  // Auto-sync timezone from browser on each session start
  useEffect(() => {
    (async () => {
      try {
        const { fetchStudyPreferences, updateStudyPreferences } = await import("./api/settings");
        const prefs = await fetchStudyPreferences();
        const browserOffset = Math.round(-(new Date().getTimezoneOffset() / 60));
        if (prefs.timezone_offset !== browserOffset) {
          await updateStudyPreferences({ timezone_offset: browserOffset });
        }
      } catch { /* not authenticated yet or network error */ }
    })();
  }, []);

  const handleSelectQuestion = (id: number) => {
    if (tab === "study") {
      setStudyQuestionId(id);
    } else {
      setSelectedQuestionId(id);
      setTab("questions");
    }
  };

  const handleBack = () => {
    setSelectedQuestionId(null);
  };

  return (
    <div className="flex flex-col h-[100dvh]">
      <Header onOpenSettings={() => setSettingsOpen(true)} />
      <main className="flex-1 overflow-hidden relative">
        <div className="h-full overflow-y-auto" id="main-scroll">
          {tab === "study" && (
            studyQuestionId ? (
              <QuestionDetail
                questionId={studyQuestionId}
                onBack={() => setStudyQuestionId(null)}
                forceReview
              />
            ) : (
              <div className="p-4 space-y-6 max-w-3xl mx-auto">
                <DailyPlan
                  onSelectQuestion={handleSelectQuestion}
                  onDetailModeChange={setStudyDetailOpen}
                />
                {!studyDetailOpen && <ProgressDashboard />}
              </div>
            )
          )}

          {tab === "questions" && (
            selectedQuestionId ? (
              <QuestionDetail questionId={selectedQuestionId} onBack={handleBack} />
            ) : (
              <div className="max-w-3xl mx-auto">
                <QuestionList onSelectQuestion={setSelectedQuestionId} />
              </div>
            )
          )}

          {tab === "patterns" && (
            <div className="p-4 max-w-3xl mx-auto">
              <SubtopicBrowser onSelectQuestion={handleSelectQuestion} />
            </div>
          )}

          {tab === "quiz" && (
            <div className="max-w-3xl mx-auto">
              <QuizSession />
            </div>
          )}

        </div>
      </main>
      <BottomNav active={tab} onChange={(t) => { setTab(t); setSelectedQuestionId(null); setStudyQuestionId(null); }} />

      {settingsOpen && (
        <div className="fixed inset-0 z-[80]">
          <button
            className="absolute inset-0 bg-black/50"
            onClick={() => setSettingsOpen(false)}
            aria-label="Close settings"
          />
          <aside className="absolute right-0 top-0 h-full w-full max-w-xl bg-[#131F24] border-l border-[#2a3f4a] shadow-2xl overflow-y-auto">
            <div className="sticky top-0 z-10 bg-[#131F24] border-b border-[#2a3f4a] px-4 py-3 flex items-center justify-between">
              <h2 className="text-white font-bold text-lg">Settings</h2>
              <button
                onClick={() => setSettingsOpen(false)}
                className="text-[#9CA3AF] bg-[#1C2B33] rounded-lg px-3 py-1.5 text-sm active:text-white"
              >
                Close
              </button>
            </div>
            <SettingsPage compact />
          </aside>
        </div>
      )}
    </div>
  );
}

function Gate() {
  const { session, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[100dvh] bg-[#131F24] text-[#9CA3AF]">
        Loading...
      </div>
    );
  }

  if (!session) return <LoginScreen />;
  return (
    <GlossaryProvider>
      <AppContent />
    </GlossaryProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <QueryClientProvider client={queryClient}>
        <Gate />
      </QueryClientProvider>
    </AuthProvider>
  );
}
