import { api } from "./client";
import type { Question, QuestionListResponse, Status } from "../types";

export interface QuestionFilters {
  topic?: string;
  difficulty?: string;
  status?: string;
  source?: string;
  search?: string;
  skip?: number;
  limit?: number;
}

export function fetchQuestions(filters: QuestionFilters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== "") params.set(k, String(v));
  });
  const qs = params.toString();
  return api.get<QuestionListResponse>(`/questions${qs ? `?${qs}` : ""}`);
}

export function fetchQuestion(id: number) {
  return api.get<Question>(`/questions/${id}`);
}

export function createQuestion(data: Partial<Question>) {
  return api.post<Question>("/questions", data);
}

export function updateQuestion(id: number, data: Partial<Question>) {
  return api.put<Question>(`/questions/${id}`, data);
}

export function setQuestionStatus(id: number, status: Status) {
  return api.put<Question>(`/questions/${id}/status`, { status });
}

export function deleteQuestion(id: number) {
  return api.delete(`/questions/${id}`);
}

export function fetchTopics() {
  return api.get<string[]>("/questions/topics");
}

export function fetchStats() {
  return api.get<Record<string, unknown>>("/questions/stats");
}

export function importQuestions(text: string, defaultSource?: string) {
  return api.post<{ added: number; updated: number; skipped: number; questions: Question[] }>(
    "/questions/import",
    { text, default_source: defaultSource }
  );
}
