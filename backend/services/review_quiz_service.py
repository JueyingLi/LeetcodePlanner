import json
import logging
import random
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import Integer, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.code_mistake import CodeMistake
from backend.models.progress import UserProgress
from backend.models.question import Question, Status
from backend.models.quiz import QuizAttempt
from backend.models.review_quiz import ReviewQuizFormat, ReviewQuizItem, ReviewQuizSourceType
from backend.models.solution import Solution
from backend.models.subtopic import SubtopicKnowledge
from backend.models.study_plan import StudyPlan, StudyPlanItem, StudyPlanSession, SubtopicReview
from backend.services.code_snippet_filter import is_actual_code
from backend.services.llm_client import llm_client

logger = logging.getLogger(__name__)


async def build_review_quiz(
    db: AsyncSession,
    user_id: str,
    limit: int = 15,
) -> list[ReviewQuizItem]:
    """Build a personalized review quiz from existing data. No LLM calls."""
    # Clear unanswered items from any previous session
    await db.execute(
        delete(ReviewQuizItem).where(
            ReviewQuizItem.user_id == user_id,
            ReviewQuizItem.user_answer.is_(None),
        )
    )
    # Clean up stale code_repair items that used old free-text format (no options)
    await db.execute(
        delete(ReviewQuizItem).where(
            ReviewQuizItem.user_id == user_id,
            ReviewQuizItem.quiz_format == ReviewQuizFormat.CODE_REPAIR,
            ReviewQuizItem.options.is_(None),
        )
    )
    await _cleanup_non_code_mistakes(db, user_id)
    await _contextualize_existing_drill_recall(db, user_id)
    await db.flush()

    items: list[ReviewQuizItem] = []
    now = datetime.now(timezone.utc)
    all_subtopics = (await db.execute(
        select(SubtopicKnowledge).where(
            SubtopicKnowledge.description.is_not(None),
        )
    )).scalars().all()

    if len(all_subtopics) < 3:
        await db.commit()
        return items

    subtopic_names = [st.name for st in all_subtopics]
    due_question_ids = await _due_question_ids(db, user_id, now)
    due_template_subtopics = await _due_template_subtopics(db, user_id, now)
    due_template_ids = {st.id for st in due_template_subtopics}
    due_pattern_question_ids = await _due_pattern_drill_question_ids(db, user_id, now)
    due_regular_question_ids = due_question_ids - due_pattern_question_ids

    if not due_question_ids and not due_template_ids and not due_pattern_question_ids:
        await db.commit()
        return items

    items.extend(await _build_scenario_match(db, user_id, due_regular_question_ids, subtopic_names))
    items.extend(await _build_signal_recognition(db, user_id, due_template_subtopics, subtopic_names))
    items.extend(await _build_code_repair(db, user_id, due_template_ids))
    items.extend(await _build_drill_recall(db, user_id, due_pattern_question_ids))
    items.extend(await _build_when_to_use(db, user_id, due_template_subtopics, subtopic_names))
    items.extend(await _build_approach_select(db, user_id, due_regular_question_ids))
    items.extend(await _build_mistake_retry(db, user_id, due_regular_question_ids))

    random.shuffle(items)

    weak_sources = await _get_weak_sources(db, user_id)
    items.sort(key=lambda i: (0 if (i.source_type.value, i.source_id) in weak_sources else 1))

    items = items[:limit]

    for item in items:
        db.add(item)
    await db.commit()
    for item in items:
        await db.refresh(item)
    return items


async def get_existing_items(db: AsyncSession, user_id: str) -> list[ReviewQuizItem]:
    await _cleanup_non_code_mistakes(db, user_id)
    await _contextualize_existing_drill_recall(db, user_id)
    await _delete_unready_unanswered_items(db, user_id)
    await db.commit()
    result = await db.execute(
        select(ReviewQuizItem)
        .where(ReviewQuizItem.user_id == user_id)
        .order_by(ReviewQuizItem.created_at.desc())
        .limit(30)
    )
    return list(result.scalars().all())


async def answer_item(
    db: AsyncSession,
    user_id: str,
    item_id: int,
    user_answer: str,
    time_spent: int | None = None,
) -> ReviewQuizItem | None:
    item = (await db.execute(
        select(ReviewQuizItem).where(
            ReviewQuizItem.id == item_id,
            ReviewQuizItem.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not item:
        return None
    item.user_answer = user_answer
    item.time_spent_seconds = time_spent
    normalized_user = user_answer.strip().lower()
    normalized_correct = item.correct_answer.strip().lower()
    if item.quiz_format == ReviewQuizFormat.CODE_REPAIR:
        item.is_correct = _normalize_code(user_answer) == _normalize_code(item.correct_answer)
    else:
        item.is_correct = normalized_user == normalized_correct
    await db.commit()
    await db.refresh(item)
    return item


async def get_stats(db: AsyncSession, user_id: str) -> dict:
    answered = (await db.execute(
        select(func.count(ReviewQuizItem.id)).where(
            ReviewQuizItem.user_id == user_id,
            ReviewQuizItem.is_correct.is_not(None),
        )
    )).scalar() or 0
    correct = (await db.execute(
        select(func.count(ReviewQuizItem.id)).where(
            ReviewQuizItem.user_id == user_id,
            ReviewQuizItem.is_correct.is_(True),
        )
    )).scalar() or 0
    by_format_rows = (await db.execute(
        select(
            ReviewQuizItem.quiz_format,
            func.count(ReviewQuizItem.id),
            func.sum(func.cast(ReviewQuizItem.is_correct, Integer)),
        )
        .where(ReviewQuizItem.user_id == user_id, ReviewQuizItem.is_correct.is_not(None))
        .group_by(ReviewQuizItem.quiz_format)
    )).all()
    by_format = {}
    for fmt, total, corr in by_format_rows:
        by_format[fmt.value if hasattr(fmt, "value") else fmt] = {
            "total": total,
            "correct": corr or 0,
            "accuracy": round((corr or 0) / total * 100, 1) if total else 0,
        }
    return {
        "total": answered,
        "correct": correct,
        "accuracy": round(correct / answered * 100, 1) if answered else 0,
        "by_format": by_format,
    }


def _normalize_code(code: str) -> str:
    return " ".join(code.split()).strip()


def _pick_distractors(correct: str, pool: list[str], count: int = 3) -> list[str]:
    candidates = [n for n in pool if n.lower() != correct.lower()]
    return random.sample(candidates, min(count, len(candidates)))


def _shuffle_options(correct: str, distractors: list[str]) -> list[str]:
    opts = [correct] + distractors
    random.shuffle(opts)
    return opts


async def _get_weak_sources(db: AsyncSession, user_id: str) -> set[tuple[str, int]]:
    wrong = (await db.execute(
        select(ReviewQuizItem.source_type, ReviewQuizItem.source_id)
        .where(
            ReviewQuizItem.user_id == user_id,
            ReviewQuizItem.is_correct.is_(False),
        )
    )).all()
    return {(r[0].value if hasattr(r[0], "value") else r[0], r[1]) for r in wrong}


async def _due_question_ids(db: AsyncSession, user_id: str, now: datetime) -> set[int]:
    rows = (await db.execute(
        select(UserProgress.question_id)
        .where(
            UserProgress.user_id == user_id,
            UserProgress.status.in_([Status.DONE, Status.REVIEW, Status.REWORK]),
            or_(UserProgress.next_review <= now, UserProgress.next_review.is_(None)),
        )
    )).scalars().all()
    return set(rows)


async def _due_template_subtopics(db: AsyncSession, user_id: str, now: datetime) -> list[SubtopicKnowledge]:
    rows = (await db.execute(
        select(SubtopicKnowledge)
        .join(SubtopicReview, SubtopicReview.subtopic_id == SubtopicKnowledge.id)
        .where(
            SubtopicReview.user_id == user_id,
            or_(SubtopicReview.next_review <= now, SubtopicReview.next_review.is_(None)),
        )
        .order_by(SubtopicReview.next_review.asc().nullslast(), SubtopicKnowledge.name)
    )).scalars().all()
    return list(rows)


async def _due_pattern_drill_question_ids(db: AsyncSession, user_id: str, now: datetime) -> set[int]:
    rows = (await db.execute(
        select(StudyPlanItem.question_id, UserProgress.next_review)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .join(StudyPlan, StudyPlanSession.plan_id == StudyPlan.id)
        .outerjoin(
            UserProgress,
            and_(
                UserProgress.user_id == user_id,
                UserProgress.question_id == StudyPlanItem.question_id,
            ),
        )
        .where(
            StudyPlan.user_id == user_id,
            StudyPlanSession.session_type == "pattern_drill",
            StudyPlanItem.question_id.is_not(None),
            StudyPlanItem.status.in_(["completed", "rework"]),
            or_(UserProgress.next_review <= now, UserProgress.next_review.is_(None)),
        )
    )).all()
    return {qid for qid, _next_review in rows if qid is not None}


async def _delete_unready_unanswered_items(db: AsyncSession, user_id: str) -> int:
    now = datetime.now(timezone.utc)
    due_question_ids = await _due_question_ids(db, user_id, now)
    due_template_ids = {st.id for st in await _due_template_subtopics(db, user_id, now)}
    due_pattern_question_ids = await _due_pattern_drill_question_ids(db, user_id, now)

    rows = list((await db.execute(
        select(ReviewQuizItem)
        .where(
            ReviewQuizItem.user_id == user_id,
            ReviewQuizItem.user_answer.is_(None),
        )
        .limit(200)
    )).scalars().all())

    deleted = 0
    for item in rows:
        source_type = item.source_type.value if hasattr(item.source_type, "value") else item.source_type
        keep = (
            (source_type == ReviewQuizSourceType.QUESTION.value and item.source_id in due_question_ids)
            or (source_type == ReviewQuizSourceType.TEMPLATE.value and item.source_id in due_template_ids)
            or (source_type == ReviewQuizSourceType.PATTERN_DRILL.value and item.source_id in due_pattern_question_ids)
        )
        if not keep:
            await db.delete(item)
            deleted += 1
    return deleted


async def _build_scenario_match(
    db: AsyncSession,
    user_id: str,
    due_question_ids: set[int],
    subtopic_names: list[str],
) -> list[ReviewQuizItem]:
    items = []
    if not due_question_ids:
        return items
    solutions = (await db.execute(
        select(Solution)
        .where(
            Solution.question_id.in_(due_question_ids),
            Solution.pattern_analysis.is_not(None),
        )
        .order_by(Solution.is_optimal.desc(), Solution.sort_order.asc())
        .limit(20)
    )).scalars().all()

    for sol in solutions:
        pa = sol.pattern_analysis
        if not pa or not isinstance(pa, dict):
            continue
        scenario = pa.get("scenario")
        approaches = pa.get("approaches", [])
        if not scenario or not approaches:
            continue
        correct_label = approaches[0].get("label", "")
        if not correct_label:
            continue
        distractors = _pick_distractors(correct_label, subtopic_names)
        if len(distractors) < 2:
            continue
        options = _shuffle_options(correct_label, distractors[:3])
        items.append(ReviewQuizItem(
            user_id=user_id,
            quiz_format=ReviewQuizFormat.SCENARIO_MATCH,
            source_type=ReviewQuizSourceType.QUESTION,
            source_id=sol.question_id,
            prompt=f"Which pattern best solves this?\n\n{scenario}",
            options=options,
            correct_answer=correct_label,
            explanation=approaches[0].get("why", ""),
            metadata_json={
                "question_id": sol.question_id,
                "example": pa.get("example"),
                "link_type": "question",
                "link_id": sol.question_id,
            },
        ))
        if len(items) >= 4:
            break
    return items


async def _build_signal_recognition(
    db: AsyncSession,
    user_id: str,
    due_subtopics: list[SubtopicKnowledge],
    subtopic_names: list[str],
) -> list[ReviewQuizItem]:
    items = []
    candidates = [st for st in due_subtopics if st.signals and len(st.signals) >= 2]
    random.shuffle(candidates)

    for st in candidates[:4]:
        signals_to_show = random.sample(st.signals, min(3, len(st.signals)))
        distractors = _pick_distractors(st.name, subtopic_names)
        if len(distractors) < 2:
            continue
        options = _shuffle_options(st.name, distractors[:3])
        items.append(ReviewQuizItem(
            user_id=user_id,
            quiz_format=ReviewQuizFormat.SIGNAL_RECOGNITION,
            source_type=ReviewQuizSourceType.TEMPLATE,
            source_id=st.id,
            prompt=f"Which pattern do these signals suggest?\n\n" + "\n".join(f"- {s}" for s in signals_to_show),
            options=options,
            correct_answer=st.name,
            explanation=st.when_to_use or "",
            metadata_json={
                "subtopic_id": st.id,
                "all_signals": st.signals,
                "link_type": "subtopic",
                "link_id": st.id,
            },
        ))
    return items


class _CodeRepairQuiz(BaseModel):
    question: str = Field(description="A short question asking what code fills the ___BLANK___. Mention what the blank section should accomplish in the algorithm.")
    code_context: str = Field(description="The full function code with EXACTLY the correct_snippet replaced by ___BLANK___. Every other line stays unchanged. Preserve indentation and newlines.")
    correct_option: str = Field(description="The correct code that fills ___BLANK___. Must be actual Python code, not a description.")
    wrong_option_1: str = Field(description="A plausible but incorrect Python code snippet. Same structure as correct_option but with a subtle bug (off-by-one, wrong operator, wrong variable, etc).")
    wrong_option_2: str = Field(description="Another plausible but incorrect Python code snippet with a different kind of bug.")
    wrong_option_3: str = Field(description="A third plausible but incorrect Python code snippet with yet another kind of bug.")
    explanation: str = Field(description="Teach why the correct answer works and what specific bug each wrong option has.")


async def _cleanup_non_code_mistakes(db: AsyncSession, user_id: str) -> None:
    mistakes = (await db.execute(
        select(CodeMistake.id, CodeMistake.correct_code)
        .where(CodeMistake.user_id == user_id)
    )).all()
    bad_ids = [mistake_id for mistake_id, correct_code in mistakes if not is_actual_code(correct_code)]
    repair_items = (await db.execute(
        select(ReviewQuizItem.id, ReviewQuizItem.source_id, ReviewQuizItem.correct_answer)
        .where(
            ReviewQuizItem.user_id == user_id,
            ReviewQuizItem.quiz_format == ReviewQuizFormat.CODE_REPAIR,
        )
    )).all()
    bad_source_ids = set(bad_ids)
    bad_item_ids = [
        item_id
        for item_id, source_id, correct_answer in repair_items
        if source_id in bad_source_ids or not is_actual_code(correct_answer)
    ]
    if bad_item_ids:
        await db.execute(
            delete(ReviewQuizItem).where(
                ReviewQuizItem.user_id == user_id,
                ReviewQuizItem.id.in_(bad_item_ids),
            )
        )
    if not bad_ids:
        return
    await db.execute(
        delete(ReviewQuizItem).where(
            ReviewQuizItem.user_id == user_id,
            ReviewQuizItem.source_type == ReviewQuizSourceType.CODE_MISTAKE,
            ReviewQuizItem.source_id.in_(bad_ids),
        )
    )
    await db.execute(
        delete(CodeMistake).where(
            CodeMistake.user_id == user_id,
            CodeMistake.id.in_(bad_ids),
        )
    )


async def _build_code_repair(db: AsyncSession, user_id: str, due_template_ids: set[int]) -> list[ReviewQuizItem]:
    items = []
    if not due_template_ids:
        return items
    mistakes = (await db.execute(
        select(CodeMistake)
        .where(CodeMistake.user_id == user_id)
        .where(CodeMistake.subtopic_id.in_(due_template_ids))
        .order_by(CodeMistake.created_at.desc())
        .limit(15)
    )).scalars().all()

    if not mistakes:
        return items

    code_mistakes = [m for m in mistakes if is_actual_code(m.correct_code)]
    if not code_mistakes:
        return items

    subtopic_ids = {m.subtopic_id for m in code_mistakes if m.subtopic_id}
    subtopics_by_id: dict[int, SubtopicKnowledge] = {}
    if subtopic_ids:
        rows = (await db.execute(
            select(SubtopicKnowledge).where(SubtopicKnowledge.id.in_(subtopic_ids))
        )).scalars().all()
        subtopics_by_id = {st.id: st for st in rows}

    for m in code_mistakes[:3]:
        st = subtopics_by_id.get(m.subtopic_id) if m.subtopic_id else None
        core_code = st.core_code if st else None

        llm_prompt = (
            f"Build a code quiz for the **{m.subtopic_name}** pattern.\n\n"
            f"CORRECT CODE SNIPPET (this is what should fill the blank):\n"
            f"```python\n{m.correct_code}\n```\n\n"
            f"STUDENT'S WRONG CODE (what they typed instead):\n"
            f"```python\n{m.user_code}\n```\n\n"
        )
        if core_code:
            llm_prompt += (
                f"FULL TEMPLATE CODE for this pattern:\n"
                f"```python\n{core_code}\n```\n\n"
            )
        if m.context_line:
            llm_prompt += f"CONTEXT: {m.context_line}\n\n"
        if m.weakness_tag:
            llm_prompt += f"WEAKNESS: {m.weakness_tag}\n\n"

        llm_prompt += (
            "INSTRUCTIONS:\n"
            "1. code_context: Take the FULL TEMPLATE CODE above. Find where the CORRECT CODE SNIPPET "
            "appears in it and replace ONLY that part with ___BLANK___. "
            "Every other line must remain exactly as-is. Do NOT put ___BLANK___ at the end.\n"
            "2. question: Ask what code fills ___BLANK___. Describe what that section should DO in the algorithm.\n"
            "3. correct_option: The CORRECT CODE SNIPPET verbatim.\n"
            "4. wrong_option_1/2/3: Generate 3 WRONG Python code snippets that look like they could "
            "fill the blank but have subtle bugs. Examples of good distractors:\n"
            "   - Off-by-one: `right - left` instead of `right - left + 1`\n"
            "   - Wrong comparison: `<=` instead of `<`, `>=` instead of `>`\n"
            "   - Wrong variable: `left` instead of `right`, `s` instead of `t`\n"
            "   - Missing step: omitting an increment or a check\n"
            "   - Wrong method: `.add()` instead of `.append()`\n"
            "   CRITICAL: All options must be PYTHON CODE, never English descriptions.\n"
            "5. explanation: Explain why the correct code works and what specific bug each wrong option has."
        )

        try:
            result = await llm_client.complete_structured(
                [{"role": "user", "content": llm_prompt}],
                _CodeRepairQuiz,
                db,
            )
        except Exception:
            logger.warning("LLM call failed for code_repair quiz (mistake %s), skipping", m.id, exc_info=True)
            continue

        if not is_actual_code(result.correct_option):
            continue

        options = _shuffle_options(result.correct_option, [
            result.wrong_option_1, result.wrong_option_2, result.wrong_option_3,
        ])

        items.append(ReviewQuizItem(
            user_id=user_id,
            quiz_format=ReviewQuizFormat.CODE_REPAIR,
            source_type=ReviewQuizSourceType.TEMPLATE,
            source_id=m.subtopic_id,
            prompt=result.question,
            options=options,
            correct_answer=result.correct_option,
            explanation=result.explanation,
            metadata_json={
                "code_mistake_id": m.id,
                "subtopic_id": m.subtopic_id,
                "subtopic_name": m.subtopic_name,
                "code_context": result.code_context,
                "weakness_tag": m.weakness_tag,
                "user_wrong_code": m.user_code,
                "link_type": "subtopic",
                "link_id": m.subtopic_id,
            },
        ))
    return items


async def _build_drill_recall(db: AsyncSession, user_id: str, due_question_ids: set[int]) -> list[ReviewQuizItem]:
    items = []
    if not due_question_ids:
        return items
    solutions = (await db.execute(
        select(Solution)
        .where(
            Solution.question_id.in_(due_question_ids),
            Solution.pattern_analysis.is_not(None),
        )
        .order_by(Solution.is_optimal.desc(), Solution.sort_order.asc())
        .limit(30)
    )).scalars().all()

    random.shuffle(solutions)
    for sol in solutions:
        pa = sol.pattern_analysis
        if not pa or not isinstance(pa, dict):
            continue
        questions = pa.get("questions", [])
        if not questions:
            continue
        usable_questions = [
            dq for dq in questions
            if not _is_weak_drill_question(
                str(dq.get("question", "")),
                str(dq.get("answer", "")),
                dq.get("wrong_options") or [],
            )
        ]
        if not usable_questions:
            continue
        dq = random.choice(usable_questions)
        question_text = dq.get("question", "")
        answer_text = dq.get("answer", "")
        if not question_text or not answer_text:
            continue
        q = (await db.execute(
            select(Question).where(Question.id == sol.question_id)
        )).scalar_one_or_none()
        prompt = _contextualized_drill_prompt(q, pa, question_text)
        wrong_options = dq.get("wrong_options", [])
        if wrong_options and len(wrong_options) >= 2:
            options = _shuffle_options(answer_text, wrong_options[:3])
        else:
            options = None
        items.append(ReviewQuizItem(
            user_id=user_id,
            quiz_format=ReviewQuizFormat.DRILL_RECALL,
            source_type=ReviewQuizSourceType.PATTERN_DRILL,
            source_id=sol.question_id,
            prompt=prompt,
            options=options,
            correct_answer=answer_text,
            explanation="",
            metadata_json={
                "question_id": sol.question_id,
                "approach_label": dq.get("approach_label"),
                "raw_drill_prompt": question_text,
                "contextualized": True,
                "link_type": "question",
                "link_id": sol.question_id,
            },
        ))
        if len(items) >= 3:
            break
    return items


def _shorten(text: str | None, limit: int = 260) -> str:
    if not text:
        return ""
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _contextualized_drill_prompt(
    question: Question | None,
    pattern_analysis: dict | None,
    drill_prompt: str,
) -> str:
    """Make stored Pattern Drill questions usable as standalone review quiz prompts."""
    pa = pattern_analysis if isinstance(pattern_analysis, dict) else {}
    context_parts = []
    if question:
        label = f"Question {f'#{question.number} ' if question.number else ''}{question.title}".strip()
        context_parts.append(label)
    if pa.get("scenario"):
        context_parts.append(_shorten(pa.get("scenario"), 220))
    if pa.get("goal"):
        context_parts.append(f"Goal: {_shorten(pa.get('goal'), 180)}")
    if pa.get("data_characteristics"):
        context_parts.append(f"Key data cue: {_shorten(pa.get('data_characteristics'), 240)}")

    if not context_parts:
        return drill_prompt
    return f"Context: {' '.join(context_parts)}\n\n{drill_prompt}"


def _is_weak_drill_question(prompt: str, answer: str = "", wrong_options: list | None = None) -> bool:
    """Reject drill prompts that test generic failure modes instead of a concrete invariant."""
    p = " ".join((prompt or "").lower().split())
    a = " ".join((answer or "").lower().split())
    options_text = " ".join(str(o).lower() for o in (wrong_options or []))

    vague_failure = (
        ("what would happen" in p or "what happens" in p or "would go wrong" in p)
        and (
            "not initialized correctly" in p
            or "initialized incorrectly" in p
            or "not initialized properly" in p
            or "incorrect initialization" in a
            or "not initialized" in a
        )
    )
    if vague_failure:
        return True

    generic_outcome = (
        "incorrect query results" in a
        or "incorrect results" in a
        or "not accurately reflect" in a
        or "default values" in options_text
        or "automatically corrected" in options_text
    )
    if generic_outcome and ("initialized" in p or "initialization" in p):
        return True

    return False


def _repair_weak_drill_question(
    question: Question | None,
    pattern_analysis: dict | None,
    prompt: str,
    answer: str,
    options: list | None,
) -> tuple[str, str, list | None] | None:
    pa = pattern_analysis if isinstance(pattern_analysis, dict) else {}
    haystack = " ".join([
        prompt or "",
        answer or "",
        pa.get("data_characteristics", "") or "",
        " ".join(str(s) for s in (pa.get("constraint_signals") or [])),
        " ".join(str((a or {}).get("label", "")) for a in (pa.get("approaches") or [])),
    ]).lower()

    if "segment tree" not in haystack:
        return None

    repaired_prompt = _contextualized_drill_prompt(
        question,
        pa,
        (
            "In this segment tree solution, each node must store the exact aggregate/invariant "
            "that queryRange or range queries rely on for that interval. Which initialization "
            "mistake specifically breaks correctness?"
        ),
    )
    repaired_answer = (
        "Initializing an untouched node to the wrong identity changes the meaning of every interval "
        "that has not been explicitly updated. For a coverage-style segment tree, an untouched range "
        "should not be treated as covered; otherwise queryRange can return true for intervals that "
        "were never added."
    )
    repaired_options = _shuffle_options(repaired_answer, [
        "The only issue is slower updates, because later updates will always repair every node before any query reads it.",
        "It only affects leaf nodes; parent nodes still combine children correctly no matter what identity value was used.",
        "The tree remains correct because default values are ignored whenever lazy propagation is used.",
    ])
    return repaired_prompt, repaired_answer, repaired_options


def _drill_prompt_needs_context(prompt: str, metadata: dict | None = None) -> bool:
    if (metadata or {}).get("contextualized"):
        return False
    stripped = (prompt or "").strip()
    if stripped.lower().startswith("context:"):
        return False
    # Short "why this technique" prompts are usually unusable after being separated
    # from the original question page.
    context_markers = ("problem", "input", "goal", "given", "return", "you are", "question")
    return len(stripped) < 180 or not any(marker in stripped.lower() for marker in context_markers)


async def _contextualize_existing_drill_recall(db: AsyncSession, user_id: str) -> int:
    """Patch older Drill Recall rows that were created before prompts included context."""
    rows = list((await db.execute(
        select(ReviewQuizItem)
        .where(
            ReviewQuizItem.user_id == user_id,
            ReviewQuizItem.quiz_format == ReviewQuizFormat.DRILL_RECALL,
            ReviewQuizItem.source_type == ReviewQuizSourceType.PATTERN_DRILL,
        )
        .limit(100)
    )).scalars().all())
    if not rows:
        return 0

    question_ids = {item.source_id for item in rows if item.source_id}
    if not question_ids:
        return 0

    questions = {
        q.id: q
        for q in (await db.execute(
            select(Question).where(Question.id.in_(question_ids))
        )).scalars().all()
    }
    solutions_by_qid: dict[int, Solution] = {}
    for sol in (await db.execute(
        select(Solution)
        .where(Solution.question_id.in_(question_ids), Solution.pattern_analysis.is_not(None))
        .order_by(Solution.is_optimal.desc(), Solution.sort_order.asc())
    )).scalars().all():
        solutions_by_qid.setdefault(sol.question_id, sol)

    updated = 0
    for item in rows:
        metadata = item.metadata_json or {}
        raw_prompt = metadata.get("raw_drill_prompt") or item.prompt
        sol = solutions_by_qid.get(item.source_id)
        if _is_weak_drill_question(raw_prompt, item.correct_answer, item.options):
            repaired = _repair_weak_drill_question(
                questions.get(item.source_id),
                sol.pattern_analysis if sol else None,
                raw_prompt,
                item.correct_answer,
                item.options,
            )
            if repaired:
                item.prompt, item.correct_answer, item.options = repaired
                item.metadata_json = {
                    **metadata,
                    "raw_drill_prompt": raw_prompt,
                    "contextualized": True,
                    "repaired_weak_prompt": True,
                }
                updated += 1
            else:
                await db.delete(item)
                updated += 1
            continue

        if not _drill_prompt_needs_context(item.prompt, metadata):
            continue
        item.prompt = _contextualized_drill_prompt(
            questions.get(item.source_id),
            sol.pattern_analysis if sol else None,
            raw_prompt,
        )
        item.metadata_json = {
            **metadata,
            "raw_drill_prompt": raw_prompt,
            "contextualized": True,
        }
        updated += 1
    return updated


async def _build_when_to_use(
    db: AsyncSession,
    user_id: str,
    due_subtopics: list[SubtopicKnowledge],
    subtopic_names: list[str],
) -> list[ReviewQuizItem]:
    items = []
    candidates = [st for st in due_subtopics if st.when_to_use and len(st.when_to_use) > 20]
    random.shuffle(candidates)

    for st in candidates[:3]:
        snippet = st.when_to_use
        if len(snippet) > 300:
            snippet = snippet[:300] + "..."
        distractors = _pick_distractors(st.name, subtopic_names)
        if len(distractors) < 2:
            continue
        options = _shuffle_options(st.name, distractors[:3])
        items.append(ReviewQuizItem(
            user_id=user_id,
            quiz_format=ReviewQuizFormat.WHEN_TO_USE,
            source_type=ReviewQuizSourceType.TEMPLATE,
            source_id=st.id,
            prompt=f"Which pattern matches this use case?\n\n{snippet}",
            options=options,
            correct_answer=st.name,
            explanation=f"This describes **{st.name}** — {(st.description or '')[:200]}",
            metadata_json={
                "subtopic_id": st.id,
                "link_type": "subtopic",
                "link_id": st.id,
            },
        ))
    return items


async def _build_approach_select(db: AsyncSession, user_id: str, due_question_ids: set[int]) -> list[ReviewQuizItem]:
    items = []
    if not due_question_ids:
        return items
    solutions = (await db.execute(
        select(Solution)
        .where(
            Solution.question_id.in_(due_question_ids),
            Solution.pattern_analysis.is_not(None),
        )
        .order_by(Solution.is_optimal.desc(), Solution.sort_order.asc())
        .limit(20)
    )).scalars().all()

    random.shuffle(solutions)
    for sol in solutions:
        pa = sol.pattern_analysis
        if not pa or not isinstance(pa, dict):
            continue
        scenario = pa.get("scenario", "")
        approaches = pa.get("approaches", [])
        if not scenario or len(approaches) < 2:
            continue
        correct = approaches[0]
        correct_text = f"{correct.get('label', '')}: {correct.get('why', '')[:100]}"
        wrong_texts = [
            f"{a.get('label', '')}: {a.get('why', '')[:100]}"
            for a in approaches[1:]
        ]
        if len(wrong_texts) < 1:
            continue
        all_subtopics = (await db.execute(
            select(SubtopicKnowledge.name).where(SubtopicKnowledge.parent_id.is_(None)).limit(50)
        )).scalars().all()
        extra_distractors = [
            f"{name}: Common approach"
            for name in random.sample(list(all_subtopics), min(2, len(all_subtopics)))
            if name != correct.get("label")
        ]
        distractors = (wrong_texts + extra_distractors)[:3]
        options = _shuffle_options(correct_text, distractors)
        items.append(ReviewQuizItem(
            user_id=user_id,
            quiz_format=ReviewQuizFormat.APPROACH_SELECT,
            source_type=ReviewQuizSourceType.QUESTION,
            source_id=sol.question_id,
            prompt=f"What is the **best primary approach** for this problem?\n\n{scenario}",
            options=options,
            correct_answer=correct_text,
            explanation=correct.get("why", ""),
            metadata_json={
                "question_id": sol.question_id,
                "link_type": "question",
                "link_id": sol.question_id,
            },
        ))
        if len(items) >= 2:
            break
    return items


async def _build_mistake_retry(db: AsyncSession, user_id: str, due_question_ids: set[int]) -> list[ReviewQuizItem]:
    items = []
    if not due_question_ids:
        return items
    wrong_quizzes = (await db.execute(
        select(QuizAttempt)
        .where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.is_correct.is_(False),
            QuizAttempt.question_id.in_(due_question_ids),
        )
        .order_by(QuizAttempt.created_at.desc())
        .limit(10)
    )).scalars().all()

    for qa in wrong_quizzes[:3]:
        quiz_data = qa.quiz_data or {}
        prompt = quiz_data.get("prompt", "")
        if not prompt:
            continue
        options_raw = quiz_data.get("options")
        items.append(ReviewQuizItem(
            user_id=user_id,
            quiz_format=ReviewQuizFormat.MISTAKE_RETRY,
            source_type=ReviewQuizSourceType.QUESTION,
            source_id=qa.question_id,
            replaces_quiz_id=qa.id,
            prompt=f"(Retry) {prompt}",
            options=options_raw if isinstance(options_raw, list) else None,
            correct_answer=qa.correct_answer,
            explanation=quiz_data.get("explanation", ""),
            metadata_json={
                "original_quiz_id": qa.id,
                "original_user_answer": qa.user_answer,
                "question_id": qa.question_id,
                "link_type": "question",
                "link_id": qa.question_id,
            },
        ))
    return items
