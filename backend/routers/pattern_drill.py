from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.solution import Solution
from backend.models.user import User
from backend.schemas.pattern_drill import (
    DrillAskRequest,
    DrillAskResponse,
    DrillCard,
    DrillDeckResponse,
    DrillReviewRequest,
    DrillReviewResponse,
)
from backend.services import (
    pattern_analysis_service,
    pattern_drill_service,
    question_service,
)

router = APIRouter(prefix="/api/pattern-drill", tags=["pattern-drill"])


@router.get("/deck", response_model=DrillDeckResponse)
async def get_deck(
    topic: str | None = Query(None),
    difficulty: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = await pattern_drill_service.list_browse_deck(db, topic, difficulty, limit)
    qids = [r["id"] for r in rows]
    done = await pattern_drill_service.completed_question_ids(db, user.id, qids)
    items = []
    for r in rows:
        card = DrillCard(
            id=r["id"],
            number=r["number"],
            title=r["title"],
            difficulty=r["difficulty"],
            topics=r["topics"],
            subtopics=r["subtopics"],
            pattern_analysis=r["pattern_analysis"],
            completed=r["id"] in done,
        )
        items.append(card)
    return DrillDeckResponse(items=items, total=len(items))


@router.get("/{question_id}/analysis")
async def get_analysis(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get pattern analysis for a specific question (from its optimal solution)."""
    pa = await pattern_drill_service.get_pattern_analysis(db, question_id)
    if not pa:
        raise HTTPException(status_code=404, detail="No pattern analysis found")
    return pa


@router.post("/{question_id}/review", response_model=DrillReviewResponse)
async def review_drill(
    question_id: int,
    req: DrillReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    progress = await pattern_drill_service.record_review(
        db, user.id, question_id, req.quality, req.notes
    )
    return DrillReviewResponse(
        question_id=question_id,
        repetitions=progress.repetitions,
        interval=progress.interval,
        next_review=progress.next_review,
        last_reviewed=progress.last_reviewed,
    )


@router.post("/{question_id}/ask", response_model=DrillAskResponse)
async def ask_drill(
    question_id: int,
    req: DrillAskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    question = await question_service.get_question(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    try:
        clarification = await pattern_drill_service.ask(
            db, user.id, question, req.question, req.step_kind
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI tutor failed: {e}")
    return DrillAskResponse.model_validate(clarification)


@router.post("/{question_id}/generate", response_model=DrillCard)
async def generate_analysis(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate pattern analysis for a question's optimal solution."""
    question = await question_service.get_question(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    ok = await pattern_analysis_service.prepare_question(db, question)
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Could not prepare this drill. Check that an API key is configured in Settings.",
        )
    pa = await pattern_drill_service.get_pattern_analysis(db, question_id)
    return DrillCard(
        id=question.id,
        number=question.number,
        title=question.title,
        difficulty=question.difficulty,
        topics=question.topics or [],
        subtopics=question.subtopics or [],
        pattern_analysis=pa,
    )


@router.post("/{question_id}/regenerate", response_model=DrillCard)
async def regenerate_analysis(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Wipe and regenerate pattern analysis for a specific question."""
    question = await question_service.get_question(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    await db.execute(
        update(Solution)
        .where(Solution.question_id == question_id)
        .values(pattern_analysis=None)
    )
    await db.commit()
    ok = await pattern_analysis_service.ensure_analysis(db, question, force=True)
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Regeneration failed. Check that an API key is configured in Settings.",
        )
    pa = await pattern_drill_service.get_pattern_analysis(db, question_id)
    return DrillCard(
        id=question.id,
        number=question.number,
        title=question.title,
        difficulty=question.difficulty,
        topics=question.topics or [],
        subtopics=question.subtopics or [],
        pattern_analysis=pa,
    )


@router.post("/regenerate-all")
async def regenerate_all(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Wipe all pattern analyses and regenerate them in the background."""
    result = await db.execute(
        select(Solution.question_id)
        .where(Solution.pattern_analysis.is_not(None))
        .distinct()
    )
    question_ids = [r[0] for r in result.all()]

    await db.execute(
        update(Solution).where(Solution.pattern_analysis.is_not(None)).values(pattern_analysis=None)
    )
    await db.commit()

    background_tasks.add_task(
        pattern_analysis_service.generate_for_questions, question_ids
    )
    return {"status": "started", "question_count": len(question_ids)}
