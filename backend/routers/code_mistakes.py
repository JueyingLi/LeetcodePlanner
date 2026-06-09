from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.code_mistake import CodeMistake
from backend.models.user import User
from backend.schemas.code_mistake import CodeMistakeCreate, CodeMistakeResponse
from backend.services.code_snippet_filter import is_actual_code

router = APIRouter(prefix="/api/code-mistakes", tags=["code-mistakes"])


@router.post("")
async def record_mistake(
    body: CodeMistakeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from backend.agents.mistake_analysis_agent import MistakeAnalysisAgent

    if not is_actual_code(body.correct_code):
        return {
            "id": 0,
            "subtopic_id": body.subtopic_id,
            "subtopic_name": body.subtopic_name,
            "correct_code": body.correct_code,
            "user_code": body.user_code,
            "context_line": body.context_line,
            "analysis": None,
            "weakness_tag": "ignored_non_code",
            "created_at": None,
        }

    try:
        agent = MistakeAnalysisAgent()
        result = await agent.analyze(
            db, body.subtopic_name, body.correct_code, body.user_code, body.context_line,
        )
    except Exception:
        result = None

    if result and result.is_correct:
        return {
            "id": 0,
            "subtopic_id": body.subtopic_id,
            "subtopic_name": body.subtopic_name,
            "correct_code": body.correct_code,
            "user_code": body.user_code,
            "context_line": body.context_line,
            "analysis": None,
            "weakness_tag": "correct",
            "created_at": None,
        }

    mistake = CodeMistake(
        user_id=user.id,
        subtopic_id=body.subtopic_id,
        subtopic_name=body.subtopic_name,
        correct_code=body.correct_code,
        user_code=body.user_code,
        context_line=body.context_line,
        analysis=result.analysis if result else None,
        weakness_tag=result.weakness_tag if result else "unknown",
    )

    db.add(mistake)
    await db.commit()
    await db.refresh(mistake)
    return mistake


@router.get("", response_model=list[CodeMistakeResponse])
async def list_mistakes(
    subtopic_id: int | None = None,
    subtopic_name: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(CodeMistake).where(CodeMistake.user_id == user.id)
    if subtopic_id is not None:
        q = q.where(CodeMistake.subtopic_id == subtopic_id)
    if subtopic_name is not None:
        q = q.where(CodeMistake.subtopic_name == subtopic_name)
    q = q.order_by(CodeMistake.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/summary")
async def mistake_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Group mistakes by subtopic with counts and most common weakness."""
    from sqlalchemy import func

    q = (
        select(
            CodeMistake.subtopic_name,
            CodeMistake.subtopic_id,
            func.count().label("count"),
            func.max(CodeMistake.created_at).label("latest"),
        )
        .where(CodeMistake.user_id == user.id)
        .group_by(CodeMistake.subtopic_name, CodeMistake.subtopic_id)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "subtopic_name": r.subtopic_name,
            "subtopic_id": r.subtopic_id,
            "mistake_count": r.count,
            "latest": r.latest.isoformat() if r.latest else None,
        }
        for r in rows
    ]
