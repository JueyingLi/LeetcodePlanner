from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.user import User
from backend.schemas.review_quiz import (
    ReviewQuizAnswerRequest,
    ReviewQuizBuildRequest,
    ReviewQuizItemResponse,
    ReviewQuizStatsResponse,
)
from backend.services import review_quiz_service

router = APIRouter(prefix="/api/review-quiz", tags=["review-quiz"])


@router.post("/build", response_model=list[ReviewQuizItemResponse])
async def build_review_quiz(
    req: ReviewQuizBuildRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = req.limit if req else 15
    items = await review_quiz_service.build_review_quiz(db, user.id, limit)
    return [ReviewQuizItemResponse.model_validate(item) for item in items]


@router.get("/items", response_model=list[ReviewQuizItemResponse])
async def get_review_items(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = await review_quiz_service.get_existing_items(db, user.id)
    return [ReviewQuizItemResponse.model_validate(item) for item in items]


@router.patch("/{item_id}/answer", response_model=ReviewQuizItemResponse)
async def answer_review_item(
    item_id: int,
    req: ReviewQuizAnswerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await review_quiz_service.answer_item(
        db, user.id, item_id, req.answer, req.time_spent_seconds
    )
    if not item:
        raise HTTPException(status_code=404, detail="Review quiz item not found")
    return ReviewQuizItemResponse.model_validate(item)


@router.get("/stats", response_model=ReviewQuizStatsResponse)
async def get_review_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stats = await review_quiz_service.get_stats(db, user.id)
    return ReviewQuizStatsResponse(**stats)
