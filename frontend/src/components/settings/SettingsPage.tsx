import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchApiKeys,
  fetchInterviewDate,
  fetchStudyPreferences,
  testApiKey,
  updateInterviewDate,
  updateStudyPreferences,
  upsertApiKey,
} from "../../api/settings";
import { generateDescriptions } from "../../api/attempts";
import type { StudyPreferences } from "../../types";

export function SettingsPage({ compact = false }: { compact?: boolean }) {
  return (
    <div className="p-4 space-y-6 pb-4">
      {!compact && <h2 className="text-white font-bold text-lg">Settings</h2>}
      <ApiKeySection />
      <InterviewDateSection />
      <DailyRefreshSection />
      <StudyPreferencesSection />
      <BatchActionsSection />
    </div>
  );
}

function ApiKeySection() {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const { data: keys } = useQuery({
    queryKey: ["apiKeys"],
    queryFn: fetchApiKeys,
  });

  const saveMut = useMutation({
    mutationFn: () => upsertApiKey({ provider, api_key: apiKey, is_active: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["apiKeys"] });
      setApiKey("");
    },
  });

  const testMut = useMutation({
    mutationFn: () => testApiKey(provider, apiKey || undefined),
    onSuccess: setTestResult,
  });

  return (
    <div className="bg-[#1C2B33] rounded-xl p-4 space-y-4">
      <h3 className="text-white font-medium">API Keys</h3>

      {keys?.map((k) => (
        <div key={k.provider} className="flex items-center justify-between bg-[#243640] rounded-lg p-3">
          <div>
            <p className="text-white text-sm font-medium capitalize">{k.provider}</p>
            <p className="text-[#9CA3AF] text-xs">{k.api_key_masked} · {k.model}</p>
          </div>
          {k.is_active && (
            <span className="text-xs bg-[#58CC02]/20 text-[#58CC02] px-2 py-1 rounded">Active</span>
          )}
        </div>
      ))}

      <div className="space-y-3 pt-2 border-t border-[#2a3f4a]">
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white outline-none"
        >
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
        </select>
        <input
          type="password"
          placeholder="API Key"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white placeholder-[#9CA3AF] outline-none"
        />
        <div className="flex gap-2">
          <button
            onClick={() => testMut.mutate()}
            disabled={!apiKey || testMut.isPending}
            className="flex-1 bg-[#243640] text-white py-2.5 rounded-lg disabled:opacity-50"
          >
            {testMut.isPending ? "Testing..." : "Test"}
          </button>
          <button
            onClick={() => saveMut.mutate()}
            disabled={!apiKey || saveMut.isPending}
            className="flex-1 bg-[#58CC02] text-white py-2.5 rounded-lg disabled:opacity-50"
          >
            {saveMut.isPending ? "Saving..." : "Save"}
          </button>
        </div>
        {testResult && (
          <p className={`text-sm ${testResult.success ? "text-green-400" : "text-red-400"}`}>
            {testResult.message}
          </p>
        )}
      </div>
    </div>
  );
}

function BatchActionsSection() {
  const queryClient = useQueryClient();

  const descMut = useMutation({
    mutationFn: generateDescriptions,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["questions"] });
    },
  });

  return (
    <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
      <h3 className="text-white font-medium">Batch Actions</h3>
      <button
        onClick={() => descMut.mutate()}
        disabled={descMut.isPending}
        className="w-full bg-[#FFC800] text-[#131F24] font-medium py-2.5 rounded-lg disabled:opacity-50"
      >
        {descMut.isPending ? "Generating descriptions..." : "Generate All Missing Descriptions"}
      </button>
      {descMut.isSuccess && (
        <p className="text-[#58CC02] text-sm">
          Updated {descMut.data.updated} question{descMut.data.updated !== 1 ? "s" : ""}.
          {descMut.data.message && ` ${descMut.data.message}`}
        </p>
      )}
      {descMut.isError && (
        <p className="text-red-400 text-sm">{(descMut.error as Error).message}</p>
      )}
      <p className="text-xs text-[#9CA3AF]">
        Uses AI to generate problem descriptions and examples for questions that don't have them yet.
      </p>
    </div>
  );
}

function DailyRefreshSection() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["studyPreferences"],
    queryFn: fetchStudyPreferences,
  });

  const mutation = useMutation({
    mutationFn: updateStudyPreferences,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studyPreferences"] });
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });

  const hour = data?.daily_refresh_hour ?? 5;
  const tzOffset = data?.timezone_offset ?? Math.round(-(new Date().getTimezoneOffset() / 60));
  const browserTzName = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const browserOffset = Math.round(-(new Date().getTimezoneOffset() / 60));
  const isSynced = tzOffset === browserOffset;

  return (
    <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
      <div>
        <h3 className="text-white font-medium">Daily Plan Refresh</h3>
        <p className="text-xs text-[#9CA3AF] mt-1">
          New study day starts at this hour. Unworked items carry over; completed items move to review.
        </p>
      </div>
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="text-xs text-[#9CA3AF]">Refresh hour</label>
          <select
            value={hour}
            onChange={(e) => mutation.mutate({ daily_refresh_hour: Number(e.target.value) })}
            className="w-full bg-[#243640] rounded-lg px-3 py-2 text-white text-sm outline-none mt-1"
          >
            {Array.from({ length: 24 }, (_, i) => (
              <option key={i} value={i}>
                {i === 0 ? "12:00 AM" : i < 12 ? `${i}:00 AM` : i === 12 ? "12:00 PM" : `${i - 12}:00 PM`}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-[#9CA3AF]">Timezone</label>
          <select
            value={tzOffset}
            onChange={(e) => mutation.mutate({ timezone_offset: Number(e.target.value) })}
            className="w-full bg-[#243640] rounded-lg px-3 py-2 text-white text-sm outline-none mt-1"
          >
            {Array.from({ length: 27 }, (_, i) => {
              const v = i - 12;
              return (
                <option key={v} value={v}>
                  UTC{v >= 0 ? "+" : ""}{v}
                </option>
              );
            })}
          </select>
        </div>
      </div>
      <p className="text-[10px] text-[#9CA3AF]">
        {isSynced
          ? `Auto-synced: ${browserTzName} (UTC${browserOffset >= 0 ? "+" : ""}${browserOffset})`
          : `Browser: ${browserTzName} (UTC${browserOffset >= 0 ? "+" : ""}${browserOffset}) — override active`}
      </p>
      {mutation.isSuccess && <p className="text-[#58CC02] text-xs">Saved</p>}
    </div>
  );
}

function InterviewDateSection() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["interviewDate"],
    queryFn: fetchInterviewDate,
  });

  const mutation = useMutation({
    mutationFn: updateInterviewDate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["interviewDate"] });
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });

  return (
    <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
      <h3 className="text-white font-medium">Interview Date & Time</h3>
      <input
        type="datetime-local"
        value={data?.date || ""}
        onChange={(e) => mutation.mutate(e.target.value)}
        className="w-full bg-[#243640] rounded-lg px-4 py-2.5 text-white outline-none"
      />
      {mutation.isSuccess && (
        <p className="text-[#58CC02] text-xs">Saved</p>
      )}
    </div>
  );
}

function StudyPreferencesSection() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["studyPreferences"],
    queryFn: fetchStudyPreferences,
  });

  const mutation = useMutation({
    mutationFn: updateStudyPreferences,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studyPreferences"] });
      queryClient.invalidateQueries({ queryKey: ["studyPlan"] });
    },
  });

  const updateCount = (key: keyof StudyPreferences, value: number) => {
    mutation.mutate({ [key]: Math.max(0, Math.min(20, value)) });
  };

  const rows: { key: keyof StudyPreferences; label: string; hint: string }[] = [
    { key: "review_count", label: "Review questions", hint: "Due and rework items" },
    { key: "template_count", label: "Popular templates", hint: "Segment tree, union find, etc." },
    { key: "google_count", label: "Google/new questions", hint: "Recent or Google-tagged items" },
    { key: "hard_count", label: "Hard questions", hint: "Idea-generation practice" },
    { key: "pattern_count", label: "Pattern drills", hint: "Weak-topic practice" },
  ];

  return (
    <div className="bg-[#1C2B33] rounded-xl p-4 space-y-4">
      <div>
        <h3 className="text-white font-medium">Study Plan Size</h3>
        <p className="text-xs text-[#9CA3AF] mt-1">
          Choose how many items each regenerated daily plan should include.
        </p>
      </div>
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.key} className="flex items-center justify-between gap-3 bg-[#243640] rounded-lg p-3">
            <div className="min-w-0">
              <p className="text-sm text-white font-medium">{row.label}</p>
              <p className="text-xs text-[#9CA3AF]">{row.hint}</p>
            </div>
            <input
              type="number"
              min={0}
              max={20}
              value={data?.[row.key] ?? 0}
              onChange={(e) => updateCount(row.key, Number(e.target.value))}
              className="w-16 bg-[#1C2B33] text-white rounded-lg px-2 py-1.5 text-sm text-center outline-none"
            />
          </div>
        ))}
      </div>
      {mutation.isSuccess && <p className="text-[#58CC02] text-xs">Saved. Regenerate the plan to apply new counts.</p>}
      {mutation.isError && <p className="text-red-400 text-xs">{(mutation.error as Error).message}</p>}
    </div>
  );
}
