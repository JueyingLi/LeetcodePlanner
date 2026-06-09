from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.user import User
from backend.schemas.attempt import (
    AttemptResponse,
    AttemptUpdate,
    FeedbackRequest,
    FeedbackResponse,
)
from backend.services import attempt_service, question_service, solution_service

router = APIRouter(prefix="/api/questions/{question_id}/attempts", tags=["attempts"])


@router.get("", response_model=list[AttemptResponse])
async def list_attempts(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await attempt_service.get_attempts_for_question(db, user.id, question_id)


@router.post("", response_model=AttemptResponse, status_code=201)
async def create_attempt(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = await question_service.get_question(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    attempt = await attempt_service.create_attempt(db, user.id, question_id)
    return AttemptResponse.model_validate(attempt)


@router.put("/{attempt_id}", response_model=AttemptResponse)
async def update_attempt(
    question_id: int,
    attempt_id: int,
    data: AttemptUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    attempt = await attempt_service.update_attempt(db, user.id, attempt_id, data)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return AttemptResponse.model_validate(attempt)


@router.delete("/{attempt_id}", status_code=204)
async def delete_attempt(
    question_id: int,
    attempt_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = await attempt_service.delete_attempt(db, user.id, attempt_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Attempt not found")


@router.delete("/{attempt_id}/feedback/{step}", status_code=204)
async def delete_feedback(
    question_id: int,
    attempt_id: int,
    step: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = await attempt_service.delete_feedback(db, user.id, attempt_id, step)
    if not deleted:
        raise HTTPException(status_code=404, detail="Feedback not found")


@router.post("/{attempt_id}/feedback", response_model=FeedbackResponse)
async def get_feedback(
    question_id: int,
    attempt_id: int,
    req: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from backend.agents.feedback_agent import FeedbackAgent

    attempt = await attempt_service.get_attempt(db, user.id, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    q = await question_service.get_question(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    solutions = await solution_service.get_solutions(db, question_id)
    if not solutions:
        try:
            solutions = await solution_service.generate_solutions(db, q)
        except Exception:
            pass

    optimal = next((s for s in solutions if s.is_optimal), solutions[0] if solutions else None)
    basic = next((s for s in solutions if not s.is_optimal), None) if solutions else None

    agent = FeedbackAgent()

    try:
        if req.step and req.step != "full":
            content = getattr(attempt, req.step, None)
            if req.step == "complexity":
                content = f"Time: {attempt.time_complexity or '?'}, Space: {attempt.space_complexity or '?'}"
            if not content:
                raise HTTPException(status_code=400, detail=f"No content in '{req.step}' to review")
            result = await agent.review_step(
                db, q.title, q.description, req.step, content, optimal=optimal, basic=basic
            )
        else:
            has_any = any([
                attempt.observation, attempt.approach, attempt.code,
                attempt.time_complexity, attempt.space_complexity,
            ])
            if not has_any:
                raise HTTPException(
                    status_code=400,
                    detail="Fill in at least one step before requesting a full review.",
                )
            result = await agent.review_full(
                db, q.title, q.description,
                attempt.observation, attempt.approach,
                attempt.code, attempt.time_complexity, attempt.space_complexity,
                optimal=optimal, basic=basic,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI feedback failed: {e}")

    await attempt_service.save_feedback(
        db, user.id, attempt_id, result.step, result.model_dump()
    )

    return FeedbackResponse(
        step=result.step,
        feedback=result.feedback,
        score=result.score,
        suggestions=result.suggestions,
    )
