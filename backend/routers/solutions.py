from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.question import Question
from backend.models.solution import Solution
from backend.models.user import User
from backend.schemas.solution import SolutionGenerateRequest, SolutionResponse
from backend.services import question_service, solution_service

router = APIRouter(prefix="/api/questions/{question_id}/solutions", tags=["solutions"])


@router.get("", response_model=list[SolutionResponse])
async def get_solutions(question_id: int, db: AsyncSession = Depends(get_db)):
    question = await question_service.get_question(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    solutions = await solution_service.get_solutions(db, question_id)
    return [SolutionResponse.model_validate(s) for s in solutions]


@router.post("/generate", response_model=list[SolutionResponse])
async def generate_solutions(
    question_id: int,
    req: SolutionGenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    question = await question_service.get_question(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    try:
        solutions = await solution_service.generate_solutions(
            db,
            question,
            provider=req.provider if req else None,
            model=req.model if req else None,
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")
    return [SolutionResponse.model_validate(s) for s in solutions]


@router.delete("/{solution_id}", status_code=204)
async def delete_solution(
    question_id: int, solution_id: int, db: AsyncSession = Depends(get_db)
):
    deleted = await solution_service.delete_solution(db, solution_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Solution not found")


batch_router = APIRouter(prefix="/api/solutions", tags=["solutions"])


@batch_router.post("/generate-all")
async def generate_all_solutions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate AI solutions for all questions that don't have any yet."""
    has_solutions = select(Solution.question_id).distinct().scalar_subquery()
    result = await db.execute(
        select(Question).where(Question.id.not_in(has_solutions))
    )
    missing = list(result.scalars().all())

    if not missing:
        return {"generated": 0, "total_missing": 0, "errors": []}

    generated = 0
    errors = []
    for q in missing:
        try:
            await solution_service.generate_solutions(db, q)
            generated += 1
        except Exception as e:
            errors.append({"question_id": q.id, "title": q.title, "error": str(e)})

    return {
        "generated": generated,
        "total_missing": len(missing),
        "errors": errors[:10],
    }


@batch_router.get("/missing-count")
async def get_missing_solutions_count(db: AsyncSession = Depends(get_db)):
    has_solutions = select(Solution.question_id).distinct().scalar_subquery()
    result = await db.execute(
        select(func.count(Question.id)).where(Question.id.not_in(has_solutions))
    )
    return {"count": result.scalar() or 0}
