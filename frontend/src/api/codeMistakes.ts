import { api } from "./client";

export interface CodeMistakeCreate {
  subtopic_id?: number | null;
  subtopic_name: string;
  correct_code: string;
  user_code: string;
  context_line?: string | null;
}

export interface CodeMistakeResponse {
  id: number;
  subtopic_id: number | null;
  subtopic_name: string;
  correct_code: string;
  user_code: string;
  context_line: string | null;
  analysis: string | null;
  weakness_tag: string | null;
  created_at: string;
}

export interface MistakeSummary {
  subtopic_name: string;
  subtopic_id: number | null;
  mistake_count: number;
  latest: string | null;
}

export function recordMistake(data: CodeMistakeCreate) {
  return api.post<CodeMistakeResponse>("/code-mistakes", data);
}

export function fetchMistakes(subtopicId?: number, subtopicName?: string) {
  const params = new URLSearchParams();
  if (subtopicId != null) params.set("subtopic_id", String(subtopicId));
  if (subtopicName) params.set("subtopic_name", subtopicName);
  const qs = params.toString();
  return api.get<CodeMistakeResponse[]>(`/code-mistakes${qs ? `?${qs}` : ""}`);
}

export function fetchMistakeSummary() {
  return api.get<MistakeSummary[]>("/code-mistakes/summary");
}
