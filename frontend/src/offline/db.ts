import Dexie, { type Table } from "dexie";
import type { QuizAttempt } from "../types";

// A quiz saved to the device for offline review/answering.
export interface SavedQuiz {
  id: number; // server quiz attempt id
  quiz_data: QuizAttempt["quiz_data"];
  quiz_type: QuizAttempt["quiz_type"];
  correct_answer: string;
  savedAt: number;
}

// An answer recorded while offline, queued to sync to the server.
export interface PendingAnswer {
  quizId: number; // server quiz attempt id
  answer: string;
  time_spent_seconds: number | null;
  answeredAt: number;
}

class OfflineDB extends Dexie {
  savedQuizzes!: Table<SavedQuiz, number>;
  pendingAnswers!: Table<PendingAnswer, number>;

  constructor() {
    super("lc-offline");
    this.version(1).stores({
      savedQuizzes: "id, savedAt",
      pendingAnswers: "quizId, answeredAt",
    });
  }
}

export const offlineDb = new OfflineDB();

export async function saveQuizzesOffline(quizzes: QuizAttempt[]): Promise<void> {
  const now = Date.now();
  await offlineDb.savedQuizzes.bulkPut(
    quizzes.map((q) => ({
      id: q.id,
      quiz_data: q.quiz_data,
      quiz_type: q.quiz_type,
      correct_answer: q.correct_answer,
      savedAt: now,
    }))
  );
}

export async function listSavedQuizzes(): Promise<SavedQuiz[]> {
  return offlineDb.savedQuizzes.orderBy("savedAt").reverse().toArray();
}

export async function removeSavedQuiz(id: number): Promise<void> {
  await offlineDb.savedQuizzes.delete(id);
}

export async function enqueueAnswer(
  quizId: number,
  answer: string,
  timeSpent: number | null = null
): Promise<void> {
  await offlineDb.pendingAnswers.put({
    quizId,
    answer,
    time_spent_seconds: timeSpent,
    answeredAt: Date.now(),
  });
}

export async function countPending(): Promise<number> {
  return offlineDb.pendingAnswers.count();
}
