import { api } from "./client";
import type { ApiKeyInfo, StudyPreferences } from "../types";

export function fetchApiKeys() {
  return api.get<ApiKeyInfo[]>("/settings/api-keys");
}

export function upsertApiKey(data: {
  provider: string;
  api_key: string;
  model?: string;
  is_active?: boolean;
}) {
  return api.post<ApiKeyInfo>("/settings/api-keys", data);
}

export function deleteApiKey(provider: string) {
  return api.delete(`/settings/api-keys/${provider}`);
}

export function testApiKey(provider: string, apiKey?: string) {
  return api.post<{ success: boolean; message: string }>(
    "/settings/api-keys/test",
    { provider, api_key: apiKey }
  );
}

export function fetchInterviewDate() {
  return api.get<{ date: string }>("/settings/interview-date");
}

export function updateInterviewDate(date: string) {
  return api.put<{ date: string }>("/settings/interview-date", { date });
}

export function fetchStudyPreferences() {
  return api.get<StudyPreferences>("/settings/study-preferences");
}

export function updateStudyPreferences(data: Partial<StudyPreferences>) {
  return api.put<StudyPreferences>("/settings/study-preferences", data);
}
