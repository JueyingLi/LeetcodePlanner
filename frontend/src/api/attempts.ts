import { api } from "./client";
import type { UserAttempt, StepFeedback } from "../types";

export function fetchAttempts(questionId: number) {
  return api.get<UserAttempt[]>(`/questions/${questionId}/attempts`);
}

export function createAttempt(questionId: number) {
  return api.post<UserAttempt>(`/questions/${questionId}/attempts`);
}

export function updateAttempt(
  questionId: number,
  attemptId: number,
  data: Partial<UserAttempt>
) {
  return api.put<UserAttempt>(`/questions/${questionId}/attempts/${attemptId}`, data);
}

export function deleteAttempt(questionId: number, attemptId: number) {
  return api.delete(`/questions/${questionId}/attempts/${attemptId}`);
}

export function requestFeedback(
  questionId: number,
  attemptId: number,
  step: string | null
) {
  return api.post<StepFeedback>(
    `/questions/${questionId}/attempts/${attemptId}/feedback`,
    { step }
  );
}

export function deleteFeedback(
  questionId: number,
  attemptId: number,
  step: string
) {
  return api.delete(`/questions/${questionId}/attempts/${attemptId}/feedback/${step}`);
}

export function generateDescriptions() {
  return api.post<{ updated: number; total_missing?: number; message?: string }>(
    "/questions/generate-descriptions",
    {}
  );
}
