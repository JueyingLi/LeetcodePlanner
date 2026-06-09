import { saveQuizAnswer, submitQuiz } from "../api/quiz";
import { offlineDb, countPending } from "./db";

let running = false;

/**
 * Flush queued offline answers to the server.
 *
 * For each pending answer we PATCH the answer (idempotent — the server
 * recomputes correctness from the stored answer), then submit the batch so
 * SM2 progress updates. Items are removed on success; items the server
 * permanently rejects (e.g. the quiz no longer exists) are dropped so the
 * queue can't get stuck. Network failures stop the run and are retried later.
 */
export async function flushPendingAnswers(): Promise<number> {
  if (running || !navigator.onLine) return 0;
  running = true;
  try {
    const pending = await offlineDb.pendingAnswers.toArray();
    const submitted: { quiz_id: number; answer: string; time_spent_seconds?: number }[] = [];

    for (const item of pending) {
      try {
        await saveQuizAnswer(item.quizId, item.answer);
        await offlineDb.pendingAnswers.delete(item.quizId);
        submitted.push({
          quiz_id: item.quizId,
          answer: item.answer,
          time_spent_seconds: item.time_spent_seconds ?? undefined,
        });
      } catch {
        if (!navigator.onLine) break; // offline again — retry later
        // Server rejected it (e.g. 404/401 handled upstream). Drop to avoid a stuck queue.
        await offlineDb.pendingAnswers.delete(item.quizId);
      }
    }

    if (submitted.length > 0) {
      try {
        await submitQuiz(submitted);
      } catch {
        // Progress update failed; answers are already recorded server-side via PATCH.
      }
    }

    return submitted.length;
  } finally {
    running = false;
  }
}

/**
 * Wire up automatic syncing: flush when the connection returns and once now.
 * Returns a cleanup function. `onChange` is called with the pending count
 * after each attempt so the UI can show an indicator.
 */
export function initSync(onChange?: (pending: number) => void): () => void {
  const run = async () => {
    await flushPendingAnswers();
    if (onChange) onChange(await countPending());
  };

  const onOnline = () => void run();
  window.addEventListener("online", onOnline);
  void run();

  return () => window.removeEventListener("online", onOnline);
}
