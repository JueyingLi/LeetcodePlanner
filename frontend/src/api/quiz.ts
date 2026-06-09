import { api } from "./client";
import type { QuizAttempt, QuizFocus, QuizStats } from "../types";

export function generateQuiz(params: {
  count?: number;
  topics?: string[];
  subtopics?: string[];
  focus?: string;
  quiz_focuses?: QuizFocus[];
  question_ids?: number[];
}) {
  return api.post<{ quizzes: QuizAttempt[]; total: number }>(
    "/quiz/generate",
    params
  );
}

export function submitQuiz(
  attempts: { quiz_id: number; answer: string; time_spent_seconds?: number }[]
) {
  return api.post<QuizAttempt[]>("/quiz/submit", { attempts });
}

export function saveQuizAnswer(quizId: number, answer: string) {
  return api.patch<QuizAttempt>(`/quiz/${quizId}/answer`, { answer });
}

export function fetchQuizHistory(wrongOnly = false) {
  return api.get<QuizAttempt[]>(`/quiz/history?wrong_only=${wrongOnly}&include_unanswered=true&limit=50`);
}

export function deleteQuizAttempt(quizId: number) {
  return api.delete(`/quiz/${quizId}`);
}

export function clearQuizHistory(unansweredOnly = false) {
  return api.delete(`/quiz?unanswered_only=${unansweredOnly}`);
}

export function fetchQuizStats() {
  return api.get<QuizStats>("/quiz/stats");
}
