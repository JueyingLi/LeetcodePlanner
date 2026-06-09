import { api } from "./client";
import type { Solution } from "../types";

export function fetchSolutions(questionId: number) {
  return api.get<Solution[]>(`/questions/${questionId}/solutions`);
}

export function generateSolutions(
  questionId: number,
  opts?: { provider?: string; model?: string }
) {
  return api.post<Solution[]>(`/questions/${questionId}/solutions/generate`, {
    provider: opts?.provider,
    model: opts?.model,
  });
}

export function deleteSolution(questionId: number, solutionId: number) {
  return api.delete(`/questions/${questionId}/solutions/${solutionId}`);
}

export function generateAllSolutions() {
  return api.post<{ generated: number; total_missing: number; errors: { question_id: number; title: string; error: string }[] }>(
    "/solutions/generate-all",
    {}
  );
}

export function fetchMissingSolutionsCount() {
  return api.get<{ count: number }>("/solutions/missing-count");
}
