import { api } from "./client";
import type { DrillCard } from "../types";

export interface DrillDeckResponse {
  items: DrillCard[];
  total: number;
}

export function fetchPatternDeck(topic?: string, difficulty?: string, limit = 50) {
  const params = new URLSearchParams();
  if (topic) params.set("topic", topic);
  if (difficulty) params.set("difficulty", difficulty);
  params.set("limit", String(limit));
  return api.get<DrillDeckResponse>(`/pattern-drill/deck?${params.toString()}`);
}

export interface DrillReviewResponse {
  question_id: number;
  repetitions: number;
  interval: number;
  next_review: string | null;
  last_reviewed: string | null;
}

export function reviewDrill(questionId: number, quality: number, notes?: string) {
  return api.post<DrillReviewResponse>(`/pattern-drill/${questionId}/review`, {
    quality,
    notes: notes || undefined,
  });
}

export interface DrillAskResponse {
  id: number;
  question_id: number;
  user_question: string;
  answer: string;
  created_at: string;
}

export function askDrill(questionId: number, question: string, stepKind?: string) {
  return api.post<DrillAskResponse>(`/pattern-drill/${questionId}/ask`, {
    question,
    step_kind: stepKind || undefined,
  });
}

export function fetchPatternAnalysis(questionId: number) {
  return api.get<Record<string, unknown>>(`/pattern-drill/${questionId}/analysis`);
}

export function generatePatternAnalysis(questionId: number) {
  return api.post<DrillCard>(`/pattern-drill/${questionId}/generate`);
}

export function regeneratePatternAnalysis(questionId: number) {
  return api.post<DrillCard>(`/pattern-drill/${questionId}/regenerate`);
}

export function regenerateAllPatternAnalyses() {
  return api.post<{ status: string; question_count: number }>("/pattern-drill/regenerate-all");
}
