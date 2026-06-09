import asyncio
import random
import re
from datetime import datetime, timezone

from sqlalchemy import Integer as SAInteger, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.quiz_agent import QuizAgent
from backend.models.progress import UserProgress
from backend.models.question import Question
from backend.models.question_links import QuestionSubtopic, QuestionTopic
from backend.models.quiz import QuizAttempt, QuizFocus, QuizType
from backend.models.solution import Solution
from backend.models.subtopic import SubtopicKnowledge
from backend.services import scheduler_service
from backend.services.llm_client import llm_client


OPTION_LABEL_RE = re.compile(r"^\s*([A-Da-d])[\).:]\s+")
OPTION_LETTER_RE = re.compile(r"^\s*([A-Da-d])[\).:]?\s*$")


def _strip_option_label(value: str) -> str:
    return OPTION_LABEL_RE.sub("", value).strip()


def _shuffle_quiz_options(quiz_data: dict) -> dict:
    """Randomize answer position while keeping correct_answer as exact option text."""
    options = quiz_data.get("options")
    if not options:
        return quiz_data

    cleaned_options = [_strip_option_label(str(option)) for option in options]
    correct = str(quiz_data.get("correct_answer") or "").strip()

    letter_match = OPTION_LETTER_RE.match(correct)
    if letter_match:
        index = ord(letter_match.group(1).upper()) - ord("A")
        if 0 <= index < len(cleaned_options):
            correct = cleaned_options[index]
    else:
        stripped_correct = _strip_option_label(correct)
        for option in cleaned_options:
            if option == correct or option == stripped_correct:
                correct = option
                break

    if correct not in cleaned_options:
        return {**quiz_data, "options": cleaned_options, "correct_answer": correct}

    shuffled = list(cleaned_options)
    random.shuffle(shuffled)
    return {**quiz_data, "options": shuffled, "correct_answer": correct}


async def generate_quiz(
    db: AsyncSession,
    user_id: str,
    count: int = 5,
    topics: list[str] | None = None,
    subtopics: list[str] | None = None,
    focus: str | None = None,
    quiz_focuses: list[QuizFocus] | None = None,
    question_ids: list[int] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> list[QuizAttempt]:
    if not quiz_focuses:
        quiz_focuses = [QuizFocus.FULL_FLOW]

    questions_with_solutions = (
        select(Solution.question_id).distinct().scalar_subquery()
    )

    if question_ids:
        result = await db.execute(
            select(Question).where(
                Question.id.in_(question_ids),
                Question.id.in_(questions_with_solutions),
            )
        )
        questions = list(result.scalars().all())
    else:
        query = select(Question).where(Question.id.in_(questions_with_solutions))
        if topics:
            topic_qids = select(QuestionTopic.question_id).where(QuestionTopic.topic_name.in_(topics)).scalar_subquery()
            query = query.where(Question.id.in_(topic_qids))
        if subtopics:
            st_qids = (
                select(QuestionSubtopic.question_id)
                .join(SubtopicKnowledge, SubtopicKnowledge.id == QuestionSubtopic.subtopic_id)
                .where(SubtopicKnowledge.name.in_(subtopics))
                .scalar_subquery()
            )
            query = query.where(Question.id.in_(st_qids))
        if focus == "weak":
            weak_stats = await scheduler_service.get_weakness_stats(db, user_id)
            weak_topics = [s["topic"] for s in weak_stats if s["accuracy"] < 0.6]
            if weak_topics:
                weak_qids = (
                    select(QuestionTopic.question_id)
                    .where(QuestionTopic.topic_name.in_(weak_topics))
                    .scalar_subquery()
                )
                query = query.where(Question.id.in_(weak_qids))

        query = query.order_by(func.random()).limit(count)
        result = await db.execute(query)
        questions = list(result.scalars().all())

    if not questions:
        return []

    # Pre-fetch all solutions in one query
    q_ids = [q.id for q in questions]
    sol_result = await db.execute(
        select(Solution)
        .where(Solution.question_id.in_(q_ids))
        .order_by(Solution.sort_order)
    )
    all_solutions = list(sol_result.scalars().all())
    solutions_by_q: dict[int, list[Solution]] = {}
    for s in all_solutions:
        solutions_by_q.setdefault(s.question_id, []).append(s)

    # Recent wrong answers per question — used to re-test pattern recognition.
    wrong_by_q: dict[int, list[dict]] = {}
    if QuizFocus.PATTERN_RECOGNITION in quiz_focuses:
        wrong_result = await db.execute(
            select(QuizAttempt)
            .where(QuizAttempt.user_id == user_id)
            .where(QuizAttempt.question_id.in_(q_ids))
            .where(QuizAttempt.is_correct.is_(False))
            .order_by(QuizAttempt.created_at.desc())
        )
        for a in wrong_result.scalars().all():
            lst = wrong_by_q.setdefault(a.question_id, [])
            if len(lst) < 5:
                lst.append({
                    "prompt": (a.quiz_data or {}).get("prompt", ""),
                    "user_answer": a.user_answer,
                    "correct_answer": a.correct_answer,
                })

    # Pre-resolve LLM config once so concurrent calls skip DB
    llm_cfg = await llm_client.resolve_config(db, provider, model)

    # Build all LLM tasks
    agent = QuizAgent()
    tasks: list[tuple[Question, QuizFocus, int, asyncio.Task]] = []

    for question in questions:
        solutions = solutions_by_q.get(question.id, [])
        if not solutions:
            continue
        per_question = max(1, count // len(questions))
        for qf in quiz_focuses:
            n = max(1, per_question // len(quiz_focuses))
            wrong = wrong_by_q.get(question.id) if qf == QuizFocus.PATTERN_RECOGNITION else None
            tasks.append((
                question,
                qf,
                n,
                agent.generate(
                    None, question, solutions, n, qf, llm_config=llm_cfg, wrong_answers=wrong,
                ),
            ))

    # Run all LLM calls concurrently
    coros = [t[3] for t in tasks]
    results = await asyncio.gather(*coros, return_exceptions=True)

    all_attempts = []
    for (question, qf, n, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            continue
        for qd in result:
            qd = _shuffle_quiz_options(qd)
            attempt = QuizAttempt(
                user_id=user_id,
                question_id=qd["question_id"],
                quiz_type=qd["quiz_type"],
                quiz_focus=qd["quiz_focus"],
                quiz_data={
                    "prompt": qd["prompt"],
                    "options": qd["options"],
                    "explanation": qd.get("explanation", ""),
                    "prior_steps_summary": qd.get("prior_steps_summary"),
                    "question_title": question.title,
                    "question_number": question.number,
                    "question_description": question.description,
                },
                correct_answer=qd["correct_answer"],
            )
            db.add(attempt)
            all_attempts.append(attempt)

    await db.commit()
    for a in all_attempts:
        await db.refresh(a)
    return all_attempts


async def submit_quiz(
    db: AsyncSession,
    user_id: str,
    attempts: list[dict],
) -> list[QuizAttempt]:
    results = []
    question_scores: dict[int, list[bool]] = {}

    for item in attempts:
        result = await db.execute(
            select(QuizAttempt).where(
                QuizAttempt.id == item["quiz_id"],
                QuizAttempt.user_id == user_id,
            )
        )
        attempt = result.scalar_one_or_none()
        if not attempt:
            continue

        attempt.user_answer = item["answer"]
        attempt.is_correct = item["answer"].strip() == attempt.correct_answer.strip()
        attempt.time_spent_seconds = item.get("time_spent_seconds")
        results.append(attempt)

        if attempt.question_id not in question_scores:
            question_scores[attempt.question_id] = []
        question_scores[attempt.question_id].append(attempt.is_correct)

    for question_id, scores in question_scores.items():
        progress_result = await db.execute(
            select(UserProgress).where(
                UserProgress.user_id == user_id,
                UserProgress.question_id == question_id,
            )
        )
        progress = progress_result.scalar_one_or_none()
        if progress:
            progress.quiz_total_count += len(scores)
            progress.quiz_correct_count += sum(scores)

    await db.commit()
    for r in results:
        await db.refresh(r)
    return results


async def get_due_review_questions(db: AsyncSession, user_id: str, limit: int = 10) -> list[dict]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Question, UserProgress)
        .join(UserProgress, UserProgress.question_id == Question.id)
        .where(UserProgress.user_id == user_id)
        .where(UserProgress.next_review <= now)
        .order_by(UserProgress.next_review)
        .limit(limit)
    )
    items = []
    for q, prog in result.all():
        accuracy = prog.quiz_correct_count / prog.quiz_total_count if prog.quiz_total_count > 0 else None
        items.append({
            "question_id": q.id,
            "title": q.title,
            "number": q.number,
            "difficulty": q.difficulty.value if hasattr(q.difficulty, "value") else q.difficulty,
            "topics": q.topics or [],
            "last_reviewed": prog.last_reviewed.isoformat() if prog.last_reviewed else None,
            "next_review": prog.next_review.isoformat() if prog.next_review else None,
            "quiz_accuracy": round(accuracy, 3) if accuracy is not None else None,
            "repetitions": prog.repetitions,
        })
    return items


async def get_quiz_stats(db: AsyncSession, user_id: str) -> dict:
    total = (await db.execute(
        select(func.count(QuizAttempt.id)).where(
            QuizAttempt.user_id == user_id, QuizAttempt.is_correct.is_not(None)
        )
    )).scalar() or 0

    correct = (await db.execute(
        select(func.count(QuizAttempt.id)).where(
            QuizAttempt.user_id == user_id, QuizAttempt.is_correct.is_(True)
        )
    )).scalar() or 0

    accuracy = correct / total if total > 0 else 0.0

    by_topic: dict[str, dict] = {}
    topic_result = await db.execute(
        select(
            Question.topics,
            QuizAttempt.is_correct,
        )
        .join(QuizAttempt, QuizAttempt.question_id == Question.id)
        .where(QuizAttempt.user_id == user_id)
        .where(QuizAttempt.is_correct.is_not(None))
    )
    for topics, is_correct in topic_result.all():
        topics_list = topics or ["Unknown"]
        for topic in topics_list:
            if topic not in by_topic:
                by_topic[topic] = {"attempts": 0, "correct": 0}
            by_topic[topic]["attempts"] += 1
            by_topic[topic]["correct"] += 1 if is_correct else 0
    for topic in by_topic:
        a = by_topic[topic]["attempts"]
        by_topic[topic]["accuracy"] = round(by_topic[topic]["correct"] / a, 3) if a > 0 else 0

    by_focus: dict[str, dict] = {}
    focus_result = await db.execute(
        select(
            QuizAttempt.quiz_focus,
            func.count(QuizAttempt.id).label("attempts"),
            func.sum(func.cast(QuizAttempt.is_correct, SAInteger)).label("correct"),
        )
        .where(QuizAttempt.user_id == user_id)
        .where(QuizAttempt.is_correct.is_not(None))
        .group_by(QuizAttempt.quiz_focus)
    )
    for row in focus_result.all():
        focus_name = row.quiz_focus.value if hasattr(row.quiz_focus, "value") else str(row.quiz_focus)
        by_focus[focus_name] = {
            "attempts": row.attempts or 0,
            "correct": row.correct or 0,
            "accuracy": round((row.correct or 0) / (row.attempts or 1), 3),
        }

    weak_stats = await scheduler_service.get_weakness_stats(db, user_id)
    weak_topics = [s["topic"] for s in weak_stats if s["accuracy"] < 0.6]

    return {
        "total_attempts": total,
        "correct_count": correct,
        "accuracy": round(accuracy, 3),
        "by_topic": by_topic,
        "by_focus": by_focus,
        "weak_topics": weak_topics,
    }
