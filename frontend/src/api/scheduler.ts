import { api } from "./client";
import type { DailyPlan, DailyPlanItem, WeaknessInfo } from "../types";

export function fetchDailyPlan() {
  return api.get<DailyPlan>("/scheduler/today");
}

export function recordReview(questionId: number, quality: number) {
  return api.post<unknown>(`/scheduler/review/${questionId}`, { quality });
}

export function fetchWeaknesses() {
  return api.get<WeaknessInfo[]>("/scheduler/weaknesses");
}

export function generateTodaySolutions() {
  return api.post<{
    generated: number;
    total_missing: number;
    errors: { question_id: number; title: string; error: string }[];
  }>("/scheduler/today/generate-solutions");
}

export function fetchRandomQuestion(excludeIds: number[]) {
  return api.post<{ item: DailyPlanItem | null }>("/scheduler/random-question", {
    exclude_ids: excludeIds,
  });
}

export function searchPickQuestions(query: string) {
  return api.post<{ items: DailyPlanItem[] }>("/scheduler/search-pick", { query });
}

export function refillQuestions(excludeIds: number[], count = 5) {
  return api.post<{ items: DailyPlanItem[] }>("/scheduler/refill", {
    exclude_ids: excludeIds,
    count,
  });
}
