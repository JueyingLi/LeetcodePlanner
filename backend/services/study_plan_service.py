from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.models.progress import UserProgress
from backend.models.question import Difficulty, Question, Status
from backend.models.question_links import QuestionSourceLink, QuestionSubtopic, QuestionTopic
from backend.models.solution import Solution
from backend.models.study_plan import (
    StudyPlan,
    StudyPlanItem,
    StudyPlanSession,
    SubtopicReview,
    UserStudyPreference,
)
from backend.models.subtopic import SubtopicKnowledge
from backend.services import scheduler_service
from backend.services.template_service import ensure_seed_templates

SESSION_SPECS = [
    ("review", "Review Session", "Due and rework questions. Focus on observations, algorithm choice, and explanation.", 55),
    ("template_review", "Popular Templates", "Core reusable code patterns without full problem context.", 65),
    ("new", "New Questions", "Recent Google-tagged questions plus harder problems where idea generation matters more than volume.", 150),
    ("pattern_drill", "Pattern Drill", "A focused weak-topic drill to improve recognition speed.", 55),
]


def parse_interview_date(value: str | None) -> datetime:
    raw = value or settings.interview_date
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime(2026, 6, 23, 10, 0, tzinfo=timezone.utc)


async def _user_study_day(db: AsyncSession, user_id: str) -> date:
    """Return the current 'study day' for the user based on their refresh hour and timezone."""
    prefs = await _get_study_preferences(db, user_id)
    tz_offset = timezone(timedelta(hours=prefs.timezone_offset))
    local_now = datetime.now(tz_offset)
    if local_now.hour < prefs.daily_refresh_hour:
        return (local_now - timedelta(days=1)).date()
    return local_now.date()


async def get_or_generate_today_plan(
    db: AsyncSession, user_id: str, interview_date_str: str | None
) -> StudyPlan:
    today = await _user_study_day(db, user_id)
    existing = await _get_plan(db, user_id, today)
    if existing:
        return existing
    yesterday = await _get_latest_plan_before(db, user_id, today)
    return await _generate_plan(db, user_id, interview_date_str, today, existing=None, carry_over_from=yesterday)


async def regenerate_today_plan(
    db: AsyncSession, user_id: str, interview_date_str: str | None
) -> StudyPlan:
    today = await _user_study_day(db, user_id)
    existing = await _get_plan(db, user_id, today)
    return await _generate_plan(db, user_id, interview_date_str, today, existing=existing)


async def add_pattern_drills_today(
    db: AsyncSession,
    user_id: str,
    interview_date_str: str | None,
    count: int = 5,
) -> tuple[StudyPlan, list[int]]:
    today = await _user_study_day(db, user_id)
    plan = await _get_plan(db, user_id, today)
    if not plan:
        plan = await _generate_plan(db, user_id, interview_date_str, today, existing=None)

    sessions = await _ensure_sessions(db, plan)
    session = sessions["pattern_drill"]
    preserved = await _preserved_targets(db, plan.id)
    rows = await _pattern_drill_questions(db, user_id, preserved["question"], count)
    existing_count = await _session_item_count(db, session.id)
    added_question_ids: list[int] = []

    for index, row in enumerate(rows):
        item_data = _question_item(row, "pattern_drill")
        item_data["reason"] = "added_pattern_drill"
        item_data["manual"] = True
        db.add(StudyPlanItem(session_id=session.id, sort_order=existing_count + index, **item_data))
        added_question_ids.append(row["question_id"])

    await db.flush()
    plan.summary = await _build_summary(db, plan, user_id)
    plan.markdown_snapshot = await _build_markdown(db, plan, user_id)
    await db.commit()
    refreshed = await _get_plan(db, user_id, today)
    return refreshed or plan, added_question_ids


async def add_templates_today(
    db: AsyncSession,
    user_id: str,
    interview_date_str: str | None,
    count: int = 3,
    subtopic_id: int | None = None,
) -> StudyPlan:
    today = await _user_study_day(db, user_id)
    plan = await _get_plan(db, user_id, today)
    if not plan:
        plan = await _generate_plan(db, user_id, interview_date_str, today, existing=None)

    sessions = await _ensure_sessions(db, plan)
    session = sessions["template_review"]
    if subtopic_id is not None:
        already_scheduled = await _scheduled_template_ids(db, plan.id, include_skipped=False)
        if subtopic_id not in already_scheduled:
            row = await _template_item_for_subtopic(db, subtopic_id, reason="manual_template_review")
            if row:
                row["manual"] = True
                existing_count = await _session_item_count(db, session.id)
                db.add(StudyPlanItem(session_id=session.id, sort_order=existing_count, **row))
    else:
        exclude = await _scheduled_template_ids(db, plan.id, include_skipped=False)
        rows = await _template_items(db, user_id, exclude, count, random_pick=True, exclude_completed=True)
        existing_count = await _session_item_count(db, session.id)
        for index, row in enumerate(rows):
            row["reason"] = "added_template_review"
            row["manual"] = True
            db.add(StudyPlanItem(session_id=session.id, sort_order=existing_count + index, **row))

    await db.flush()
    plan.summary = await _build_summary(db, plan, user_id)
    plan.markdown_snapshot = await _build_markdown(db, plan, user_id)
    await db.commit()
    refreshed = await _get_plan(db, user_id, today)
    return refreshed or plan


async def skip_and_replace_template(
    db: AsyncSession,
    user_id: str,
    item_id: int,
) -> StudyPlan | None:
    item = (await db.execute(
        select(StudyPlanItem)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .join(StudyPlan, StudyPlanSession.plan_id == StudyPlan.id)
        .where(
            StudyPlan.user_id == user_id,
            StudyPlanItem.id == item_id,
            StudyPlanItem.item_type == "template",
        )
    )).scalar_one_or_none()
    if not item:
        return None

    plan = await _get_plan_by_item(db, user_id, item_id)
    if not plan:
        return None

    item.status = "skipped"
    sessions = await _ensure_sessions(db, plan)
    session = sessions["template_review"]
    exclude = await _scheduled_template_ids(db, plan.id, include_skipped=False)
    if item.subtopic_id:
        exclude.add(item.subtopic_id)
    elif item.template_id:
        exclude.add(item.template_id)

    rows = await _template_items(db, user_id, exclude, 1, random_pick=True, exclude_completed=True)
    existing_count = await _session_item_count(db, session.id)
    for index, row in enumerate(rows):
        row["reason"] = "skip_replacement_template"
        row["manual"] = True
        db.add(StudyPlanItem(session_id=session.id, sort_order=existing_count + index, **row))

    await db.flush()
    plan.summary = await _build_summary(db, plan, user_id)
    plan.markdown_snapshot = await _build_markdown(db, plan, user_id)
    await db.commit()
    refreshed = await _get_plan(db, user_id, plan.plan_date)
    return refreshed or plan


async def update_item(
    db: AsyncSession,
    user_id: str,
    item_id: int,
    status: str | None = None,
    pinned: bool | None = None,
    notes: str | None = None,
) -> StudyPlanItem | None:
    item = (await db.execute(
        select(StudyPlanItem)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .join(StudyPlan, StudyPlanSession.plan_id == StudyPlan.id)
        .where(StudyPlan.user_id == user_id, StudyPlanItem.id == item_id)
        .options(selectinload(StudyPlanItem.subtopic))
    )).scalar_one_or_none()
    if not item:
        return None
    if status is not None:
        item.status = status
        if item.question_id is not None:
            await _sync_question_progress_status(db, user_id, item.question_id, status)
        if status in {"completed", "rework"} and item.item_type == "template" and item.subtopic_id:
            await _record_subtopic_review(db, user_id, item.subtopic_id, 4 if status == "completed" else 2)
    if pinned is not None:
        item.pinned = pinned
    if notes is not None:
        item.notes = notes
    await db.commit()
    await db.refresh(item)
    plan = await _get_plan_by_item(db, user_id, item_id)
    if plan:
        plan.markdown_snapshot = await _build_markdown(db, plan, user_id)
        plan.summary = await _build_summary(db, plan, user_id)
        await db.commit()
    return item


async def _sync_question_progress_status(
    db: AsyncSession, user_id: str, question_id: int, item_status: str
) -> None:
    status_map = {
        "completed": Status.DONE,
        "rework": Status.REWORK,
        "in_progress": Status.IN_PROGRESS,
        "skipped": Status.TODO,
        "not_started": Status.TODO,
    }
    progress_status = status_map.get(item_status)
    if progress_status is None:
        return
    progress = (await db.execute(
        select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.question_id == question_id,
        )
    )).scalar_one_or_none()
    if not progress:
        progress = UserProgress(user_id=user_id, question_id=question_id)
        db.add(progress)
    progress.status = progress_status


async def _record_subtopic_review(db: AsyncSession, user_id: str, subtopic_id: int, quality: int = 4) -> None:
    """Upsert a SubtopicReview when a template item is completed or marked rework."""
    quality = max(0, min(5, quality))
    review = (await db.execute(
        select(SubtopicReview).where(
            SubtopicReview.user_id == user_id,
            SubtopicReview.subtopic_id == subtopic_id,
        )
    )).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not review:
        review = SubtopicReview(
            user_id=user_id,
            subtopic_id=subtopic_id,
            quality_history=[quality],
            last_reviewed=now,
            next_review=now + timedelta(days=1),
        )
        db.add(review)
    else:
        if review.last_reviewed and (now - review.last_reviewed).total_seconds() < 30:
            return
        history = list(review.quality_history or [])
        history.append(quality)
        review.quality_history = history[-20:]
        review.last_reviewed = now
        interval_days = 1 if quality < 3 else 2 if quality == 3 else 4 if quality == 4 else 7
        review.next_review = now + timedelta(days=interval_days)


async def serialize_plan(db: AsyncSession, plan: StudyPlan, user_id: str) -> dict[str, Any]:
    interview = parse_interview_date(plan.interview_target)
    now = datetime.now(timezone.utc)
    delta = interview - now
    total_seconds = max(0, int(delta.total_seconds()))
    await ensure_seed_templates(db)
    await db.refresh(plan, ["sessions"])
    await _hydrate_template_related_questions(db, plan.id)
    session_rows = await _load_sessions(db, plan.id)
    return {
        "id": plan.id,
        "date": plan.plan_date,
        "interview_target": plan.interview_target,
        "status": plan.status,
        "generated_at": plan.generated_at,
        "updated_at": plan.updated_at,
        "regenerated_count": plan.regenerated_count,
        "days_until_interview": total_seconds // 86400,
        "hours_until_interview": (total_seconds % 86400) // 3600,
        "minutes_until_interview": (total_seconds % 3600) // 60,
        "summary": plan.summary or {},
        "markdown_snapshot": plan.markdown_snapshot or "",
        "sessions": [_serialize_session(session) for session in session_rows],
    }


async def plan_question_ids(
    db: AsyncSession, plan_id: int, session_types: list[str] | None = None
) -> list[int]:
    """Question ids referenced by a plan's items (for background enrichment).

    Optionally restrict to specific session types (e.g. only "pattern_drill")."""
    query = (
        select(StudyPlanItem.question_id)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .where(StudyPlanSession.plan_id == plan_id, StudyPlanItem.question_id.is_not(None))
    )
    if session_types:
        query = query.where(StudyPlanSession.session_type.in_(session_types))
    result = await db.execute(query)
    return [qid for qid in result.scalars().all() if qid]


async def _get_latest_plan_before(db: AsyncSession, user_id: str, before_date: date) -> StudyPlan | None:
    result = await db.execute(
        select(StudyPlan)
        .where(StudyPlan.user_id == user_id, StudyPlan.plan_date < before_date)
        .options(selectinload(StudyPlan.sessions).selectinload(StudyPlanSession.items).selectinload(StudyPlanItem.subtopic))
        .order_by(StudyPlan.plan_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_plan(db: AsyncSession, user_id: str, plan_date: date) -> StudyPlan | None:
    result = await db.execute(
        select(StudyPlan)
        .where(StudyPlan.user_id == user_id, StudyPlan.plan_date == plan_date)
        .options(selectinload(StudyPlan.sessions).selectinload(StudyPlanSession.items).selectinload(StudyPlanItem.subtopic))
    )
    return result.scalar_one_or_none()


async def _get_plan_by_item(db: AsyncSession, user_id: str, item_id: int) -> StudyPlan | None:
    result = await db.execute(
        select(StudyPlan)
        .join(StudyPlanSession, StudyPlanSession.plan_id == StudyPlan.id)
        .join(StudyPlanItem, StudyPlanItem.session_id == StudyPlanSession.id)
        .where(StudyPlan.user_id == user_id, StudyPlanItem.id == item_id)
    )
    return result.scalar_one_or_none()


async def _generate_plan(
    db: AsyncSession,
    user_id: str,
    interview_date_str: str | None,
    plan_date: date,
    existing: StudyPlan | None,
    carry_over_from: StudyPlan | None = None,
) -> StudyPlan:
    await ensure_seed_templates(db)
    interview = parse_interview_date(interview_date_str)
    interview_target = interview.strftime("%Y-%m-%dT%H:%M")

    if existing:
        plan = existing
        plan.interview_target = interview_target
        plan.regenerated_count += 1
        replaceable = await _replaceable_items(db, plan.id)
        for item in replaceable:
            await db.delete(item)
    else:
        plan = StudyPlan(user_id=user_id, plan_date=plan_date, interview_target=interview_target)
        db.add(plan)
        await db.flush()

    sessions = await _ensure_sessions(db, plan)

    if carry_over_from and not existing:
        await _carry_over_items(db, carry_over_from, sessions)
        await db.flush()

    preserved = await _preserved_targets(db, plan.id)
    candidates = await _build_candidate_items(db, user_id, preserved)
    for session_type, rows in candidates.items():
        session = sessions[session_type]
        existing_count = await _session_item_count(db, session.id)
        for index, row in enumerate(rows):
            db.add(StudyPlanItem(session_id=session.id, sort_order=existing_count + index, **row))

    await db.flush()
    plan.summary = await _build_summary(db, plan, user_id)
    plan.markdown_snapshot = await _build_markdown(db, plan, user_id)
    await db.commit()
    refreshed = await _get_plan(db, user_id, plan_date)
    return refreshed or plan


async def _carry_over_items(
    db: AsyncSession,
    old_plan: StudyPlan,
    new_sessions: dict[str, StudyPlanSession],
) -> None:
    """Carry items from previous plan to today's plan.

    - Unworked (not_started/in_progress) items keep their original session type.
    - Completed items move to the review session for spaced repetition.
    - Skipped items are dropped.
    """
    old_sessions = await _load_sessions(db, old_plan.id)
    for old_session in old_sessions:
        for item in old_session.items:
            if item.status == "skipped":
                continue

            if item.status == "completed":
                target_session = new_sessions["review"]
                reason = f"review (completed {old_plan.plan_date.isoformat()})"
            else:
                target_type = old_session.session_type
                if target_type not in new_sessions:
                    target_type = "new"
                target_session = new_sessions[target_type]
                reason = item.reason

            existing_count = await _session_item_count(db, target_session.id)
            db.add(StudyPlanItem(
                session_id=target_session.id,
                item_type=item.item_type,
                question_id=item.question_id,
                subtopic_id=item.subtopic_id,
                template_id=item.template_id,
                title=item.title,
                reason=reason,
                priority=item.priority,
                status="not_started" if item.status == "completed" else item.status,
                pinned=item.pinned,
                manual=False,
                estimated_minutes=item.estimated_minutes,
                sort_order=existing_count,
                notes=item.notes if item.status != "completed" else None,
                metadata_json=item.metadata_json or {},
            ))


async def _ensure_sessions(db: AsyncSession, plan: StudyPlan) -> dict[str, StudyPlanSession]:
    rows = (await db.execute(select(StudyPlanSession).where(StudyPlanSession.plan_id == plan.id))).scalars().all()
    spec_types = {spec[0] for spec in SESSION_SPECS}
    by_type = {}
    for row in rows:
        # Drop sessions whose type is no longer part of the plan (e.g. legacy
        # hard_block/reflection sessions on plans generated before they were merged/removed).
        if row.session_type not in spec_types:
            await db.delete(row)
        else:
            by_type[row.session_type] = row
    for order, (session_type, title, description, minutes) in enumerate(SESSION_SPECS):
        if session_type not in by_type:
            session = StudyPlanSession(
                plan_id=plan.id,
                session_type=session_type,
                title=title,
                description=description,
                sort_order=order,
                estimated_minutes=minutes,
            )
            db.add(session)
            by_type[session_type] = session
    await db.flush()
    return by_type


async def _replaceable_items(db: AsyncSession, plan_id: int) -> list[StudyPlanItem]:
    result = await db.execute(
        select(StudyPlanItem)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .where(
            StudyPlanSession.plan_id == plan_id,
            StudyPlanItem.status == "not_started",
            StudyPlanItem.pinned.is_(False),
            StudyPlanItem.manual.is_(False),
        )
    )
    return list(result.scalars().all())


async def _preserved_targets(db: AsyncSession, plan_id: int) -> dict[str, set[int]]:
    result = await db.execute(
        select(StudyPlanItem)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .where(StudyPlanSession.plan_id == plan_id)
    )
    targets = {"question": set(), "template": set()}
    for item in result.scalars().all():
        if item.question_id:
            targets["question"].add(item.question_id)
        if item.subtopic_id:
            targets["template"].add(item.subtopic_id)
        elif item.template_id:
            targets["template"].add(item.template_id)
    return targets


async def _session_item_count(db: AsyncSession, session_id: int) -> int:
    result = await db.execute(select(StudyPlanItem.id).where(StudyPlanItem.session_id == session_id))
    return len(result.all())


async def _scheduled_template_ids(db: AsyncSession, plan_id: int, include_skipped: bool = False) -> set[int]:
    query = (
        select(StudyPlanItem)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .where(
            StudyPlanSession.plan_id == plan_id,
            StudyPlanItem.item_type == "template",
        )
    )
    if not include_skipped:
        query = query.where(StudyPlanItem.status != "skipped")
    result = await db.execute(query)
    ids: set[int] = set()
    for item in result.scalars().all():
        if item.subtopic_id:
            ids.add(item.subtopic_id)
        elif item.template_id:
            ids.add(item.template_id)
    return ids


async def _completed_template_ids(db: AsyncSession, user_id: str) -> set[int]:
    result = await db.execute(
        select(StudyPlanItem.subtopic_id)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .join(StudyPlan, StudyPlanSession.plan_id == StudyPlan.id)
        .where(
            StudyPlan.user_id == user_id,
            StudyPlanItem.item_type == "template",
            StudyPlanItem.status == "completed",
            StudyPlanItem.subtopic_id.is_not(None),
        )
        .distinct()
    )
    return {subtopic_id for subtopic_id in result.scalars().all() if subtopic_id}


async def _build_candidate_items(
    db: AsyncSession, user_id: str, preserved: dict[str, set[int]]
) -> dict[str, list[dict[str, Any]]]:
    prefs = await _get_study_preferences(db, user_id)
    due = await _review_questions(db, user_id, preserved["question"], prefs.review_count)
    templates = await _template_items(db, user_id, preserved["template"], prefs.template_count, random_pick=True, exclude_completed=True)
    google = await _google_questions(db, user_id, preserved["question"] | {q["question_id"] for q in due}, prefs.google_count)
    hard = await _hard_questions(db, user_id, preserved["question"] | {q["question_id"] for q in due + google}, prefs.hard_count)
    drill = await _pattern_drill_questions(db, user_id, preserved["question"] | {q["question_id"] for q in due + google + hard}, prefs.pattern_count)
    return {
        "review": [_question_item(q, "review") for q in due],
        "template_review": templates,
        "new": [_question_item(q, "new") for q in google] + [_question_item(q, "hard_block") for q in hard],
        "pattern_drill": [_question_item(q, "pattern_drill") for q in drill],
    }


async def _get_study_preferences(db: AsyncSession, user_id: str) -> UserStudyPreference:
    pref = (await db.execute(
        select(UserStudyPreference).where(UserStudyPreference.user_id == user_id)
    )).scalar_one_or_none()
    if pref:
        return pref
    pref = UserStudyPreference(user_id=user_id)
    db.add(pref)
    await db.flush()
    return pref


async def _review_questions(db: AsyncSession, user_id: str, exclude: set[int], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    now = datetime.now(timezone.utc)
    used = set(exclude)
    result = await db.execute(
        select(Question, UserProgress)
        .join(UserProgress, UserProgress.question_id == Question.id)
        .where(UserProgress.user_id == user_id)
        .where(or_(UserProgress.status == Status.REWORK, UserProgress.next_review <= now))
        .where(Question.id.not_in(exclude) if exclude else True)
        .order_by(UserProgress.status.desc(), UserProgress.next_review)
        .limit(limit)
    )
    rows = []
    for q, p in result.all():
        rows.append(_question_row(q, "rework" if p.status == Status.REWORK else "review_due", 95))
        used.add(q.id)

    remaining = limit - len(rows)
    if remaining <= 0:
        return rows

    solution_question_ids = select(Solution.question_id).distinct().scalar_subquery()
    fallback = await db.execute(
        select(Question, UserProgress)
        .join(UserProgress, and_(
            UserProgress.question_id == Question.id,
            UserProgress.user_id == user_id,
        ))
        .where(Question.id.in_(solution_question_ids))
        .where(UserProgress.status.in_([Status.DONE, Status.REWORK, Status.REVIEW]))
        .where(Question.id.not_in(used) if used else True)
        .order_by(func.random())
        .limit(remaining)
    )
    for q, p in fallback.all():
        status_value = p.status.value if hasattr(p.status, "value") else p.status
        reason = "solution_review"
        if status_value == Status.REWORK.value:
            reason = "rework_with_solution"
        elif status_value == Status.REVIEW.value:
            reason = "scheduled_review"
        rows.append(_question_row(q, reason, 85))
    return rows


def _template_needs_generation(st: SubtopicKnowledge) -> bool:
    return (
        not (st.core_code or "").strip()
        or not (st.breakdown or "").strip()
        or not (st.mental_model or "").strip()
        or not (st.signals or [])
        or not (st.recall_tasks or [])
    )


def _apply_generated_subtopic_fields(st: SubtopicKnowledge, desc: dict[str, Any]) -> None:
    st.description = desc.get("description", st.description or "")
    st.when_to_use = desc.get("when_to_use", st.when_to_use or "")
    st.key_signals = desc.get("key_signals", st.key_signals or "")
    st.variants = desc.get("variants", st.variants or "")
    st.implementation_keys = desc.get("implementation_keys", st.implementation_keys or "")
    st.common_pitfalls = desc.get("common_pitfalls", st.common_pitfalls or "")
    st.core_code = desc.get("core_code", st.core_code or "")
    st.breakdown = desc.get("breakdown", st.breakdown or "")
    st.mental_model = desc.get("mental_model", st.mental_model or "")
    st.signals = desc.get("signals", st.signals or [])
    st.recall_tasks = desc.get("recall_tasks", st.recall_tasks or [])


async def _ensure_template_content(db: AsyncSession, st: SubtopicKnowledge) -> None:
    if not _template_needs_generation(st):
        return
    from backend.agents.subtopic_agent import SubtopicAgent

    agent = SubtopicAgent()
    descriptions = await agent.generate(db, [st.name])
    desc = None
    for item in descriptions:
        if item["name"].lower().strip() == st.name.lower().strip():
            desc = item
            break
    if not desc and descriptions:
        desc = descriptions[0]
    if not desc:
        raise ValueError(f"Could not generate template content for {st.name}")
    _apply_generated_subtopic_fields(st, desc)
    await db.flush()


async def _template_item_from_subtopic(db: AsyncSession, st: SubtopicKnowledge, priority: int, reason: str) -> dict[str, Any]:
    await _ensure_template_content(db, st)
    related = await _related_subtopic_questions(db, st)
    return {
        "item_type": "template",
        "subtopic_id": st.id,
        "title": st.name,
        "reason": reason,
        "priority": priority,
        "estimated_minutes": 20,
        "metadata_json": {
            "topic": st.category,
            "subtopic": st.name,
            "signals": st.signals,
            "related_questions": related,
        },
    }


async def _template_item_for_subtopic(db: AsyncSession, subtopic_id: int, reason: str) -> dict[str, Any] | None:
    st = (await db.execute(select(SubtopicKnowledge).where(SubtopicKnowledge.id == subtopic_id))).scalar_one_or_none()
    if not st:
        return None
    return await _template_item_from_subtopic(db, st, 100, reason)


async def _template_items(
    db: AsyncSession,
    user_id: str,
    exclude: set[int],
    limit: int,
    *,
    random_pick: bool = False,
    exclude_completed: bool = False,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    blocked = set(exclude)
    if exclude_completed:
        blocked |= await _completed_template_ids(db, user_id)
    if random_pick:
        result = await db.execute(
            select(SubtopicKnowledge, SubtopicReview)
            .outerjoin(
                SubtopicReview,
                and_(
                    SubtopicReview.subtopic_id == SubtopicKnowledge.id,
                    SubtopicReview.user_id == user_id,
                ),
            )
            .where(SubtopicKnowledge.id.not_in(blocked) if blocked else True)
            .order_by(func.random())
            .limit(limit)
        )
        scored = [(70, st) for st, _review in result.all()]
        return [
            await _template_item_from_subtopic(
                db,
                st,
                score,
                f"Template review: {st.when_to_use or st.name}",
            )
            for score, st in scored
        ]

    weak_subtopics = await _weak_subtopics(db, user_id)
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(SubtopicKnowledge, SubtopicReview)
        .outerjoin(
            SubtopicReview,
            and_(
                SubtopicReview.subtopic_id == SubtopicKnowledge.id,
                SubtopicReview.user_id == user_id,
            ),
        )
        .where(SubtopicKnowledge.id.not_in(blocked) if blocked else True)
    )
    scored = []
    priority_slugs = {"segment-tree", "union-find", "iterator-generator"}
    for st, review in result.all():
        score = 70
        text = f"{st.slug or ''} {st.name} {st.category}".lower()
        if st.slug in priority_slugs:
            score += 20
        if any(w.lower() in text for w in weak_subtopics):
            score += 25
        if review and review.next_review and review.next_review <= now:
            score += 20
        if not review:
            score += 10
        scored.append((score, st))
    scored.sort(key=lambda row: row[0], reverse=True)
    items = []
    for score, st in scored[:limit]:
        items.append(await _template_item_from_subtopic(
            db,
            st,
            score,
            f"Template review: {st.when_to_use or st.name}",
        ))
    return items


async def _related_subtopic_questions(db: AsyncSession, st: SubtopicKnowledge) -> list[dict[str, Any]]:
    # Primary: questions linked to this subtopic via join table
    subtopic_qids = (
        select(QuestionSubtopic.question_id)
        .where(QuestionSubtopic.subtopic_id == st.id)
        .scalar_subquery()
    )
    filters = [Question.id.in_(subtopic_qids)]

    for signal in (st.signals or [])[:5]:
        if len(signal) >= 4:
            signal_st_qids = (
                select(QuestionSubtopic.question_id)
                .join(SubtopicKnowledge, SubtopicKnowledge.id == QuestionSubtopic.subtopic_id)
                .where(SubtopicKnowledge.name.ilike(f"%{signal}%"))
                .scalar_subquery()
            )
            signal_topic_qids = (
                select(QuestionTopic.question_id)
                .where(QuestionTopic.topic_name.ilike(f"%{signal}%"))
                .scalar_subquery()
            )
            filters.append(Question.id.in_(signal_st_qids))
            filters.append(Question.id.in_(signal_topic_qids))
            filters.append(Question.title.ilike(f"%{signal}%"))

    if len(filters) == 1 and not (st.signals or []):
        category_qids = (
            select(QuestionTopic.question_id)
            .where(QuestionTopic.topic_name.ilike(f"%{st.category}%"))
            .scalar_subquery()
        )
        filters.append(Question.id.in_(category_qids))

    # Order by Google source presence
    has_google = (
        select(QuestionSourceLink.question_id)
        .where(QuestionSourceLink.source_name.ilike("%Google%"))
        .scalar_subquery()
    )
    result = await db.execute(
        select(Question)
        .where(or_(*filters))
        .order_by(Question.id.in_(has_google).desc(), Question.frequency.desc())
        .limit(4)
    )
    rows = []
    for q in result.scalars().all():
        rows.append({
            "id": q.id,
            "number": q.number,
            "title": q.title,
            "difficulty": q.difficulty.value if hasattr(q.difficulty, "value") else q.difficulty,
            "topics": q.topics or [],
            "subtopics": q.subtopics or [],
        })
    return rows


async def _hydrate_template_related_questions(db: AsyncSession, plan_id: int) -> None:
    result = await db.execute(
        select(StudyPlanItem)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .where(
            StudyPlanSession.plan_id == plan_id,
            StudyPlanItem.item_type == "template",
        )
        .options(selectinload(StudyPlanItem.subtopic))
    )
    changed = False
    for item in result.scalars().all():
        st = item.subtopic
        if not st:
            continue
        metadata = dict(item.metadata_json or {})
        related = metadata.get("related_questions")
        if isinstance(related, list) and len(related) > 0:
            continue
        metadata["related_questions"] = await _related_subtopic_questions(db, st)
        item.metadata_json = metadata
        changed = True
    if changed:
        await db.commit()


async def _google_questions(db: AsyncSession, user_id: str, exclude: set[int], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    google_qids = (
        select(QuestionSourceLink.question_id)
        .where(QuestionSourceLink.source_name.ilike("%Google%"))
        .scalar_subquery()
    )
    result = await db.execute(
        select(Question)
        .outerjoin(UserProgress, and_(UserProgress.question_id == Question.id, UserProgress.user_id == user_id))
        .where(Question.id.in_(google_qids))
        .where(or_(UserProgress.id.is_(None), UserProgress.status.in_([Status.TODO, Status.REWORK])))
        .where(Question.id.not_in(exclude) if exclude else True)
        .order_by(Question.frequency.desc(), Question.updated_at.desc())
        .limit(limit)
    )
    return [_question_row(q, "google_recent", 85) for q in result.scalars().all()]


async def _hard_questions(db: AsyncSession, user_id: str, exclude: set[int], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    google_qids = (
        select(QuestionSourceLink.question_id)
        .where(QuestionSourceLink.source_name.ilike("%Google%"))
        .scalar_subquery()
    )
    result = await db.execute(
        select(Question)
        .outerjoin(UserProgress, and_(UserProgress.question_id == Question.id, UserProgress.user_id == user_id))
        .where(Question.difficulty == Difficulty.HARD)
        .where(or_(UserProgress.id.is_(None), UserProgress.status.in_([Status.TODO, Status.REWORK])))
        .where(Question.id.not_in(exclude) if exclude else True)
        .order_by(Question.id.in_(google_qids).desc(), Question.frequency.desc())
        .limit(limit)
    )
    return [_question_row(q, "hard_idea_generation", 80) for q in result.scalars().all()]


async def _pattern_drill_questions(db: AsyncSession, user_id: str, exclude: set[int], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    weaknesses = await scheduler_service.get_weakness_stats(db, user_id)
    weak_topics = [w["topic"] for w in weaknesses[:3]]
    base_filters = [
        or_(UserProgress.id.is_(None), UserProgress.status.in_([Status.TODO, Status.REWORK])),
        Question.id.not_in(exclude) if exclude else True,
    ]
    query = (
        select(Question)
        .outerjoin(UserProgress, and_(UserProgress.question_id == Question.id, UserProgress.user_id == user_id))
        .where(*base_filters)
    )
    if weak_topics:
        weak_topic_qids = (
            select(QuestionTopic.question_id)
            .where(QuestionTopic.topic_name.in_(weak_topics))
            .scalar_subquery()
        )
        query = query.where(Question.id.in_(weak_topic_qids))
    else:
        seg_tree_qids = (
            select(QuestionSubtopic.question_id)
            .join(SubtopicKnowledge, SubtopicKnowledge.id == QuestionSubtopic.subtopic_id)
            .where(SubtopicKnowledge.name.ilike("%segment tree%"))
            .scalar_subquery()
        )
        query = query.where(Question.id.in_(seg_tree_qids))
    result = await db.execute(query.order_by(Question.frequency.desc()).limit(limit))
    rows = [_question_row(q, "weak_pattern_drill", 75) for q in result.scalars().all()]
    if len(rows) >= limit:
        return rows

    used = exclude | {row["question_id"] for row in rows}
    has_subtopics = (
        select(QuestionSubtopic.question_id).distinct().scalar_subquery()
    )
    fallback = await db.execute(
        select(Question)
        .outerjoin(UserProgress, and_(UserProgress.question_id == Question.id, UserProgress.user_id == user_id))
        .where(or_(UserProgress.id.is_(None), UserProgress.status.in_([Status.TODO, Status.REWORK])))
        .where(Question.id.not_in(used) if used else True)
        .where(Question.id.in_(has_subtopics))
        .order_by(
            Question.frequency.desc(),
            Question.updated_at.desc(),
        )
        .limit(limit - len(rows))
    )
    rows.extend(_question_row(q, "extra_pattern_drill", 70) for q in fallback.scalars().all())
    return rows


async def _weak_subtopics(db: AsyncSession, user_id: str) -> list[str]:
    weaknesses = await scheduler_service.get_weakness_stats(db, user_id)
    values = []
    for item in weaknesses:
        if item.get("topic"):
            values.append(item["topic"])
        if item.get("subtopic"):
            values.append(item["subtopic"])
    return values + ["segment tree"]


def _question_row(q: Question, reason: str, priority: int) -> dict[str, Any]:
    difficulty = q.difficulty.value if hasattr(q.difficulty, "value") else q.difficulty
    return {
        "question_id": q.id,
        "title": q.title,
        "reason": reason,
        "priority": priority,
        "difficulty": difficulty,
        "topics": q.topics or [],
        "subtopics": q.subtopics or [],
        "number": q.number,
    }


def _question_item(row: dict[str, Any], session_type: str) -> dict[str, Any]:
    minutes = 35
    if session_type == "hard_block":
        minutes = 45
    elif session_type == "review":
        minutes = 25
    return {
        "item_type": "question",
        "question_id": row["question_id"],
        "title": row["title"],
        "reason": row["reason"],
        "priority": row["priority"],
        "estimated_minutes": minutes,
        "metadata_json": {
            "difficulty": row.get("difficulty"),
            "topics": row.get("topics", []),
            "subtopics": row.get("subtopics", []),
            "number": row.get("number"),
        },
    }


async def _build_summary(db: AsyncSession, plan: StudyPlan, user_id: str) -> dict[str, Any]:
    sessions = await _load_sessions(db, plan.id)
    counts: dict[str, int] = {}
    total_minutes = 0
    completed = 0
    for session in sessions:
        counts[session.session_type] = len(session.items)
        for item in session.items:
            total_minutes += item.estimated_minutes
            if item.status == "completed":
                completed += 1
    return {
        "session_counts": counts,
        "total_estimated_minutes": total_minutes,
        "completed_items": completed,
        "total_items": sum(counts.values()),
    }


async def _build_markdown(db: AsyncSession, plan: StudyPlan, user_id: str) -> str:
    sessions = await _load_sessions(db, plan.id)
    lines = [
        f"# Daily Google Study Plan - {plan.plan_date.isoformat()}",
        "",
        f"Interview target: {plan.interview_target}",
        f"Regenerated count: {plan.regenerated_count}",
        "",
    ]
    for session in sessions:
        lines.append(f"## {session.title} ({session.estimated_minutes} min)")
        if session.description:
            lines.append(session.description)
            lines.append("")
        if not session.items:
            lines.append("- No items scheduled.")
        for item in session.items:
            status = item.status.replace("_", " ")
            lines.append(f"- [{status}] {item.title} ({item.estimated_minutes} min)")
            lines.append(f"  - Reason: {item.reason}")
            if item.item_type == "template" and item.subtopic:
                lines.append(f"  - Signals: {', '.join(item.subtopic.signals or [])}")
                if item.subtopic.core_code:
                    lines.append("  - Core code:")
                    lines.append("```python")
                    lines.append(item.subtopic.core_code)
                    lines.append("```")
            if item.notes:
                lines.append(f"  - Notes: {item.notes}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


async def _load_sessions(db: AsyncSession, plan_id: int) -> list[StudyPlanSession]:
    result = await db.execute(
        select(StudyPlanSession)
        .where(StudyPlanSession.plan_id == plan_id)
        .options(selectinload(StudyPlanSession.items).selectinload(StudyPlanItem.subtopic))
        .order_by(StudyPlanSession.sort_order)
    )
    return list(result.scalars().all())


def _serialize_session(session: StudyPlanSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "session_type": session.session_type,
        "title": session.title,
        "description": session.description,
        "sort_order": session.sort_order,
        "estimated_minutes": session.estimated_minutes,
        "items": [_serialize_item(item) for item in session.items],
    }


def _serialize_item(item: StudyPlanItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "question_id": item.question_id,
        "template_id": item.subtopic_id or item.template_id,
        "title": item.title,
        "reason": item.reason,
        "priority": item.priority,
        "status": item.status,
        "pinned": item.pinned,
        "manual": item.manual,
        "estimated_minutes": item.estimated_minutes,
        "sort_order": item.sort_order,
        "notes": item.notes,
        "metadata": item.metadata_json or {},
        "template": _serialize_subtopic_as_template(item.subtopic) if item.subtopic else None,
    }


def _serialize_subtopic_as_template(st: "SubtopicKnowledge") -> dict[str, Any]:
    return {
        "id": st.id,
        "slug": st.slug or "",
        "title": st.name,
        "topic": st.category,
        "subtopic": st.name,
        "when_to_use": st.when_to_use or "",
        "signals": st.signals or [],
        "last_reviewed": None,
        "next_review": None,
        "core_code": st.core_code or "",
        "breakdown": st.breakdown or "",
        "mental_model": st.mental_model or "",
        "variants": st.variants or "",
        "pitfalls": st.common_pitfalls or "",
        "recall_tasks": st.recall_tasks or [],
        "related_question_ids": st.related_question_ids or [],
    }
