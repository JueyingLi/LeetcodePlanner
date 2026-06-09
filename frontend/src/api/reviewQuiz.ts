import { api } from "./client";
import type { ReviewQuizItem, ReviewQuizStats } from "../types";

export function buildReviewQuiz(limit = 15): Promise<ReviewQuizItem[]> {
  return api.post<ReviewQuizItem[]>("/review-quiz/build", { limit });
}

export function fetchReviewItems(): Promise<ReviewQuizItem[]> {
  return api.get<ReviewQuizItem[]>("/review-quiz/items");
}

export function answerReviewItem(
  itemId: number,
  answer: string,
  timeSpentSeconds?: number,
): Promise<ReviewQuizItem> {
  return api.patch<ReviewQuizItem>(`/review-quiz/${itemId}/answer`, {
    answer,
    time_spent_seconds: timeSpentSeconds,
  });
}

export function fetchReviewStats(): Promise<ReviewQuizStats> {
  return api.get<ReviewQuizStats>("/review-quiz/stats");
}
