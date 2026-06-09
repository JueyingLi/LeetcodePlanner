from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.user import User
from backend.schemas.progress import DailyPlanResponse, ProgressResponse, ReviewRequest, WeaknessResponse
from backend.services import scheduler_service

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/today", response_model=DailyPlanResponse)
async def get_daily_plan(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = await scheduler_service.get_daily_plan(db, user.id, user.interview_date)
    return DailyPlanResponse(**plan)


@router.post("/review/{question_id}", response_model=ProgressResponse)
async def record_review(
    question_id: int,
    req: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    progress = await scheduler_service.record_review(db, user.id, question_id, req.quality)
    return ProgressResponse.model_validate(progress)


@router.get("/weaknesses", response_model=list[WeaknessResponse])
async def get_weaknesses(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stats = await scheduler_service.get_weakness_stats(db, user.id)
    return [WeaknessResponse(**s) for s in stats]


@router.post("/today/generate-solutions")
async def generate_today_solutions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await scheduler_service.generate_today_solutions(db, user.id)


class RandomPickRequest(BaseModel):
    exclude_ids: list[int] = []


@router.post("/random-question")
async def get_random_question(
    req: RandomPickRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exclude = req.exclude_ids if req else []
    result = await scheduler_service.get_random_question(db, exclude or None)
    if not result:
        return {"item": None}
    return {"item": result}


class SearchPickRequest(BaseModel):
    query: str


@router.post("/search-pick")
async def search_pick_questions(
    req: SearchPickRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = await scheduler_service.search_pick_questions(db, req.query)
    return {"items": items}


class RefillRequest(BaseModel):
    exclude_ids: list[int] = []
    count: int = 5


@router.post("/refill")
async def refill_questions(
    req: RefillRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = await scheduler_service.get_refill_questions(db, user.id, req.exclude_ids or None, req.count)
    return {"items": items}
