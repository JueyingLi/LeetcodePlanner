import { useQuery } from "@tanstack/react-query";
import { fetchAllCompleted, fetchStudyPlan, fetchTemplates } from "../../api/studyPlan";
import { fetchStats } from "../../api/questions";
import { fetchSubtopics } from "../../api/subtopics";
import { completedTemplateIds, templateUniverseTotal } from "../../lib/templateProgress";

function StatBox({
  value,
  total,
  label,
  color,
}: {
  value: number;
  total: number;
  label: string;
  color: string;
}) {
  return (
    <div className="bg-[#1C2B33] rounded-xl p-2 flex-1 min-w-0 text-center">
      <p className={`text-base font-bold ${color} whitespace-nowrap`}>
        {value}<span className="text-xs font-normal text-[#9CA3AF]">/{total}</span>
      </p>
      <p className="text-[10px] text-[#9CA3AF] mt-0.5">{label}</p>
    </div>
  );
}

function ProgressBar({
  label,
  current,
  total,
  color = "bg-[#58CC02]",
}: {
  label: string;
  current: number;
  total: number;
  color?: string;
}) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="text-[#9CA3AF]">{label}</span>
        <span className="text-white">
          {current}/{total}
        </span>
      </div>
      <div className="w-full bg-[#243640] rounded-full h-2">
        <div className={`${color} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function ProgressDashboard() {
  const { data: plan } = useQuery({
    queryKey: ["studyPlan"],
    queryFn: fetchStudyPlan,
  });

  const { data: stats } = useQuery({
    queryKey: ["questionStats"],
    queryFn: fetchStats,
  });

  const { data: subtopics } = useQuery({
    queryKey: ["subtopics"],
    queryFn: () => fetchSubtopics(),
  });
  const { data: allCompleted } = useQuery({
    queryKey: ["reviewAll"],
    queryFn: fetchAllCompleted,
  });
  const { data: allTemplates } = useQuery({
    queryKey: ["templates"],
    queryFn: fetchTemplates,
  });

  if (!plan) return null;

  const drillSessionIds = new Set(
    plan.sessions.filter((s) => s.session_type === "pattern_drill").map((s) => s.id),
  );

  const studiedTemplateIds = completedTemplateIds(allTemplates, allCompleted?.items);
  const templatesDone = studiedTemplateIds.size;
  const totalSubtopics = templateUniverseTotal(subtopics) || studiedTemplateIds.size;

  const questions = plan.sessions
    .filter((s) => !drillSessionIds.has(s.id))
    .flatMap((s) => s.items.filter((i) => i.item_type === "question"));

  const drills = plan.sessions
    .filter((s) => drillSessionIds.has(s.id))
    .flatMap((s) => s.items);
  const drillsDone = drills.filter((i) => i.status === "completed").length;

  const total = (stats?.total as number) || 0;
  const questionUniverseTotal = total || questions.length || drills.length;
  const byStatus = (stats?.by_status as Record<string, number>) || {};
  const questionsDone = byStatus.done || 0;
  const byDifficulty = (stats?.by_difficulty as Record<string, number>) || {};

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <StatBox
          value={templatesDone}
          total={totalSubtopics}
          label="Templates"
          color="text-[#818CF8]"
        />
        <StatBox
          value={questionsDone}
          total={questionUniverseTotal}
          label="Questions"
          color="text-[#58CC02]"
        />
        <StatBox
          value={drillsDone}
          total={questionUniverseTotal}
          label="Patterns"
          color="text-[#FFC800]"
        />
      </div>

      <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
        <ProgressBar
          label="Easy"
          current={byDifficulty.Easy || 0}
          total={total}
          color="bg-[#58CC02]"
        />
        <ProgressBar
          label="Medium"
          current={byDifficulty.Medium || 0}
          total={total}
          color="bg-[#FFC800]"
        />
        <ProgressBar
          label="Hard"
          current={byDifficulty.Hard || 0}
          total={total}
          color="bg-[#FF4B4B]"
        />
      </div>

      {Object.keys(byStatus).length > 0 && (
        <div className="bg-[#1C2B33] rounded-xl p-4 space-y-3">
          <ProgressBar label="Done" current={byStatus.done || 0} total={total} color="bg-[#58CC02]" />
          <ProgressBar label="In Progress" current={byStatus.in_progress || 0} total={total} color="bg-[#FFC800]" />
          <ProgressBar label="Pattern" current={drillsDone} total={questionUniverseTotal} color="bg-[#818CF8]" />
          <ProgressBar label="Review" current={byStatus.review || 0} total={total} color="bg-blue-500" />
          <ProgressBar label="Rework" current={byStatus.rework || 0} total={total} color="bg-[#FF4B4B]" />
        </div>
      )}
    </div>
  );
}
