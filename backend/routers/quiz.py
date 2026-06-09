from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.quiz import QuizAttempt, QuizFocus
from backend.models.user import User
from backend.schemas.quiz import (
    QuizAttemptResponse,
    QuizGenerateRequest,
    QuizSessionResponse,
    QuizStatsResponse,
    QuizSubmitRequest,
)
from backend.services import quiz_service

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.post("/generate", response_model=QuizSessionResponse)
async def generate_quiz(
    req: QuizGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    focuses = req.quiz_focuses or ([req.quiz_focus] if req.quiz_focus else [QuizFocus.FULL_FLOW])
    try:
        attempts = await quiz_service.generate_quiz(
            db,
            user.id,
            count=req.count,
            topics=req.topics,
            subtopics=req.subtopics,
            focus=req.focus,
            quiz_focuses=focuses,
            question_ids=req.question_ids,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI quiz generation failed: {e}")

    if not attempts:
        raise HTTPException(
            status_code=400,
            detail="No quiz could be generated. Make sure your questions have AI-generated solutions first — go to a question and tap 'Generate AI Solutions'.",
        )

    return QuizSessionResponse(
        quizzes=[QuizAttemptResponse.model_validate(a) for a in attempts],
        total=len(attempts),
    )


@router.post("/submit", response_model=list[QuizAttemptResponse])
async def submit_quiz(
    req: QuizSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    results = await quiz_service.submit_quiz(
        db,
        user.id,
        [item.model_dump() for item in req.attempts],
    )
    return [QuizAttemptResponse.model_validate(r) for r in results]


@router.get("/history", response_model=list[QuizAttemptResponse])
async def get_quiz_history(
    wrong_only: bool = Query(False),
    include_unanswered: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(QuizAttempt).where(QuizAttempt.user_id == user.id)
    if not include_unanswered:
        query = query.where(QuizAttempt.is_correct.is_not(None))
    if wrong_only:
        query = query.where(QuizAttempt.is_correct.is_(False))
    query = query.order_by(QuizAttempt.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return [QuizAttemptResponse.model_validate(a) for a in result.scalars().all()]


@router.patch("/{quiz_id}/answer")
async def save_answer(
    quiz_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save a single answer immediately (no progress update)."""
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.id == quiz_id, QuizAttempt.user_id == user.id
        )
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise HTTPException(status_code=404, detail="Quiz attempt not found")
    attempt.user_answer = body.get("answer", "")
    attempt.is_correct = attempt.user_answer.strip() == attempt.correct_answer.strip()
    await db.commit()
    await db.refresh(attempt)
    return QuizAttemptResponse.model_validate(attempt)


@router.delete("/{quiz_id}")
async def delete_quiz_attempt(
    quiz_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.id == quiz_id, QuizAttempt.user_id == user.id
        )
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise HTTPException(status_code=404, detail="Quiz attempt not found")
    await db.delete(attempt)
    await db.commit()
    return {"deleted": True}


@router.delete("")
async def clear_quiz_history(
    unanswered_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Clear quiz history. unanswered_only=true clears only unanswered attempts."""
    from sqlalchemy import delete
    stmt = delete(QuizAttempt).where(QuizAttempt.user_id == user.id)
    if unanswered_only:
        stmt = stmt.where(QuizAttempt.is_correct.is_(None))
    result = await db.execute(stmt)
    await db.commit()
    return {"deleted": result.rowcount}


@router.get("/due-reviews")
async def get_due_reviews(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = await quiz_service.get_due_review_questions(db, user.id, limit)
    return {"items": items, "count": len(items)}


@router.get("/stats", response_model=QuizStatsResponse)
async def get_quiz_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stats = await quiz_service.get_quiz_stats(db, user.id)
    return QuizStatsResponse(**stats)
