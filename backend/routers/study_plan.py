from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.progress import UserProgress
from backend.models.question import Question, Status
from backend.models.study_plan import StudyPlan, StudyPlanItem, StudyPlanSession, SubtopicReview
from backend.models.subtopic import SubtopicKnowledge
from backend.models.user import User
from backend.services import pattern_analysis_service
from backend.schemas.study_plan import (
    AddPatternDrillsRequest,
    AddTemplatesRequest,
    SourceImportRequest,
    SourceImportResponse,
    SourcePostResponse,
    SourceScrapeRequest,
    StudyPlanItemUpdate,
    StudyPlanResponse,
    TemplateDetailResponse,
    TemplateReviewRequest,
    TemplateReviewResponse,
    TemplateSummaryResponse,
)
from backend.services import source_ingestion_service, study_plan_service, template_service

router = APIRouter(prefix="/api/study-plan", tags=["study-plan"])
template_router = APIRouter(prefix="/api/templates", tags=["templates"])


def _template_summary(st, review=None) -> dict:
    return {
        "id": st.id,
        "slug": st.slug or "",
        "title": st.name,
        "topic": st.category,
        "subtopic": st.name,
        "when_to_use": st.when_to_use or "",
        "signals": st.signals or [],
        "last_reviewed": review.last_reviewed if review else None,
        "next_review": review.next_review if review else None,
    }


def _template_detail(st, review=None) -> dict:
    return {
        **_template_summary(st, review),
        "core_code": st.core_code or "",
        "breakdown": st.breakdown or "",
        "mental_model": st.mental_model or "",
        "variants": st.variants or "",
        "pitfalls": st.common_pitfalls or "",
        "recall_tasks": st.recall_tasks or [],
        "related_question_ids": st.related_question_ids or [],
    }


def _source_post(post) -> SourcePostResponse:
    return SourcePostResponse(
        id=post.id,
        source_type=post.source_type,
        uuid=post.uuid,
        topic_id=post.topic_id,
        slug=post.slug,
        title=post.title,
        url=post.url,
        summary=post.summary,
        full_text_preview=post.full_text_preview,
        created_at_from_source=post.created_at_from_source,
        updated_at_from_source=post.updated_at_from_source,
        hit_count=post.hit_count,
        comment_count=post.comment_count,
        score=post.score,
        extracted_questions=post.extracted_questions or [],
        imported_at=post.imported_at,
    )


@router.get("/today", response_model=StudyPlanResponse)
async def get_today_plan(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = await study_plan_service.get_or_generate_today_plan(db, user.id, user.interview_date)
    qids = await study_plan_service.plan_question_ids(db, plan.id, session_types=["pattern_drill"])
    background_tasks.add_task(pattern_analysis_service.generate_for_questions, qids)
    return StudyPlanResponse(**await study_plan_service.serialize_plan(db, plan, user.id))


@router.post("/today/regenerate", response_model=StudyPlanResponse)
async def regenerate_today_plan(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = await study_plan_service.regenerate_today_plan(db, user.id, user.interview_date)
    qids = await study_plan_service.plan_question_ids(db, plan.id, session_types=["pattern_drill"])
    background_tasks.add_task(pattern_analysis_service.generate_for_questions, qids)
    return StudyPlanResponse(**await study_plan_service.serialize_plan(db, plan, user.id))


@router.post("/today/pattern-drills/add", response_model=StudyPlanResponse)
async def add_pattern_drills(
    req: AddPatternDrillsRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan, added_qids = await study_plan_service.add_pattern_drills_today(
        db, user.id, user.interview_date, req.count
    )
    background_tasks.add_task(pattern_analysis_service.generate_for_questions, added_qids)
    return StudyPlanResponse(**await study_plan_service.serialize_plan(db, plan, user.id))


@router.post("/today/templates/add", response_model=StudyPlanResponse)
async def add_templates(
    req: AddTemplatesRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        plan = await study_plan_service.add_templates_today(
            db, user.id, user.interview_date, req.count, req.subtopic_id
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"Template generation failed: {e}")
    return StudyPlanResponse(**await study_plan_service.serialize_plan(db, plan, user.id))


@router.post("/items/{item_id}/skip-replace-template", response_model=StudyPlanResponse)
async def skip_replace_template(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        plan = await study_plan_service.skip_and_replace_template(db, user.id, item_id)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"Template replacement failed: {e}")
    if not plan:
        raise HTTPException(status_code=404, detail="Template study item not found")
    return StudyPlanResponse(**await study_plan_service.serialize_plan(db, plan, user.id))


@router.patch("/items/{item_id}")
async def update_plan_item(
    item_id: int,
    req: StudyPlanItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await study_plan_service.update_item(
        db,
        user.id,
        item_id,
        status=req.status,
        pinned=req.pinned,
        notes=req.notes,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Study plan item not found")
    return {"id": item.id, "status": item.status, "pinned": item.pinned, "notes": item.notes}


@router.post("/sources/import", response_model=SourceImportResponse)
async def import_source(
    req: SourceImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await source_ingestion_service.import_pasted_source(
        db, user.id, req.text, req.title, req.url
    )
    return SourceImportResponse(
        posts_added=result["posts_added"],
        posts_updated=result["posts_updated"],
        questions_added=result["questions_added"],
        questions_updated=result["questions_updated"],
        questions_skipped=result["questions_skipped"],
        posts=[_source_post(p) for p in result["posts"]],
    )


@router.post("/sources/scrape-leetcode", response_model=SourceImportResponse)
async def scrape_leetcode_sources(
    req: SourceScrapeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        result = await source_ingestion_service.scrape_leetcode_sources(
            db, user.id, req.max_results, req.max_comments
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return SourceImportResponse(
        posts_added=result["posts_added"],
        posts_updated=result["posts_updated"],
        questions_added=result["questions_added"],
        questions_updated=result["questions_updated"],
        questions_skipped=result["questions_skipped"],
        posts=[_source_post(p) for p in result["posts"]],
    )


@router.get("/sources", response_model=list[SourcePostResponse])
async def list_sources(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    posts = await source_ingestion_service.list_source_posts(db, user.id, limit)
    return [_source_post(p) for p in posts]


@router.get("/review/all")
async def get_all_completed(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return all available review items grouped by type on the frontend."""
    now = datetime.now(timezone.utc)
    items = []

    question_result = await db.execute(
        select(Question, UserProgress)
        .join(UserProgress, UserProgress.question_id == Question.id)
        .where(
            UserProgress.user_id == user.id,
            UserProgress.status.in_([Status.DONE, Status.REVIEW, Status.REWORK]),
        )
        .order_by(UserProgress.next_review.asc().nullslast())
    )
    for q, p in question_result.all():
        next_review = p.next_review or p.last_reviewed or now
        items.append({
            "id": q.id,
            "review_type": "question",
            "question_id": q.id,
            "template_id": None,
            "title": q.title,
            "number": q.number,
            "difficulty": q.difficulty.value if hasattr(q.difficulty, "value") else q.difficulty,
            "topics": q.topics or [],
            "subtopics": q.subtopics or [],
            "status": p.status.value if hasattr(p.status, "value") else p.status,
            "next_review": next_review.isoformat(),
            "last_reviewed": p.last_reviewed.isoformat() if p.last_reviewed else None,
            "repetitions": p.repetitions,
        })

    template_result = await db.execute(
        select(SubtopicKnowledge, SubtopicReview)
        .join(SubtopicReview, SubtopicReview.subtopic_id == SubtopicKnowledge.id)
        .where(SubtopicReview.user_id == user.id)
        .order_by(SubtopicReview.next_review.asc().nullslast(), SubtopicKnowledge.name)
    )
    for st, review in template_result.all():
        next_review = review.next_review or review.last_reviewed or now
        items.append({
            "id": st.id,
            "review_type": "template",
            "question_id": None,
            "template_id": st.id,
            "title": st.name,
            "number": None,
            "difficulty": "",
            "topics": [st.category],
            "subtopics": [st.name],
            "status": "review",
            "next_review": next_review.isoformat(),
            "last_reviewed": review.last_reviewed.isoformat() if review.last_reviewed else None,
            "repetitions": len(review.quality_history or []),
        })

    drill_result = await db.execute(
        select(Question, StudyPlanItem, UserProgress)
        .join(StudyPlanSession, StudyPlanItem.session_id == StudyPlanSession.id)
        .join(StudyPlan, StudyPlanSession.plan_id == StudyPlan.id)
        .join(Question, Question.id == StudyPlanItem.question_id)
        .outerjoin(
            UserProgress,
            and_(
                UserProgress.user_id == user.id,
                UserProgress.question_id == Question.id,
            ),
        )
        .where(
            StudyPlan.user_id == user.id,
            StudyPlanSession.session_type == "pattern_drill",
            StudyPlanItem.status.in_(["completed", "rework"]),
        )
        .order_by(StudyPlanItem.updated_at.desc())
    )
    seen_drills: set[int] = set()
    for q, item, progress in drill_result.all():
        if q.id in seen_drills:
            continue
        seen_drills.add(q.id)
        next_review = (progress.next_review if progress else None) or item.updated_at or now
        last_reviewed = progress.last_reviewed if progress else item.updated_at
        items.append({
            "id": item.id,
            "review_type": "pattern_drill",
            "question_id": q.id,
            "template_id": None,
            "title": q.title,
            "number": q.number,
            "difficulty": q.difficulty.value if hasattr(q.difficulty, "value") else q.difficulty,
            "topics": q.topics or [],
            "subtopics": q.subtopics or [],
            "status": item.status,
            "next_review": next_review.isoformat(),
            "last_reviewed": last_reviewed.isoformat() if last_reviewed else None,
            "repetitions": progress.repetitions if progress else 0,
        })

    return {"items": items, "total": len(items)}


@template_router.get("", response_model=list[TemplateSummaryResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = await template_service.list_templates(db, user.id)
    return [TemplateSummaryResponse(**_template_summary(st, r)) for st, r in rows]


@template_router.get("/{template_id}", response_model=TemplateDetailResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = await template_service.get_template(db, user.id, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    st, review = row
    return TemplateDetailResponse(**_template_detail(st, review))


@template_router.post("/{template_id}/start")
async def start_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ok = await template_service.start_template(db, user.id, template_id)
    return {"started": ok}


@template_router.post("/{template_id}/review", response_model=TemplateReviewResponse)
async def review_template(
    template_id: int,
    req: TemplateReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    review = await template_service.record_template_review(
        db, user.id, template_id, req.quality, req.notes
    )
    if not review:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateReviewResponse(
        template_id=review.subtopic_id,
        quality_history=review.quality_history or [],
        last_reviewed=review.last_reviewed,
        next_review=review.next_review,
        notes=review.notes,
    )
