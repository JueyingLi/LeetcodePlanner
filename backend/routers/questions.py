from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.question import Question
from backend.models.user import User
from backend.schemas.question import (
    ExampleItem,
    QuestionCreate,
    QuestionListResponse,
    QuestionResponse,
    QuestionUpdate,
    SourceTag,
    StatusUpdate,
)
from backend.services import question_service

router = APIRouter(prefix="/api/questions", tags=["questions"])


def _to_response(q, status: str = "todo", has_progress: bool = False) -> QuestionResponse:
    from sqlalchemy.orm import attributes
    examples = None
    if q.examples:
        examples = [ExampleItem(**e) if isinstance(e, dict) else e for e in q.examples]

    state = attributes.instance_state(q)
    solutions_loaded = "solutions" in state.dict

    return QuestionResponse(
        id=q.id,
        number=q.number,
        title=q.title,
        difficulty=q.difficulty,
        topics=q.topics or [],
        subtopics=q.subtopics or [],
        frequency=q.frequency,
        sources=[SourceTag(**s) if isinstance(s, dict) else s for s in (q.sources or [])],
        url=q.url,
        description=q.description,
        examples=examples,
        notes=q.notes,
        status=status,
        created_at=q.created_at,
        updated_at=q.updated_at,
        solution_count=len(q.solutions) if solutions_loaded and q.solutions else 0,
        has_progress=has_progress,
    )


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    topic: str | None = None,
    difficulty: str | None = None,
    status: str | None = None,
    source: str | None = None,
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    questions, total = await question_service.list_questions(
        db, user.id, topic, difficulty, status, source, search, skip, limit
    )
    status_map = await question_service.get_status_map(db, user.id, [q.id for q in questions])
    return QuestionListResponse(
        items=[
            _to_response(q, status_map.get(q.id, "todo"), q.id in status_map)
            for q in questions
        ],
        total=total,
    )


@router.get("/topics", response_model=list[str])
async def get_topics(db: AsyncSession = Depends(get_db)):
    return await question_service.get_topics(db)


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await question_service.get_stats(db, user.id)


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = await question_service.get_question(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    status_map = await question_service.get_status_map(db, user.id, [q.id])
    return _to_response(q, status_map.get(q.id, "todo"), q.id in status_map)


@router.post("", response_model=QuestionResponse, status_code=201)
async def create_question(
    data: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = await question_service.create_question(db, data)
    return _to_response(q)


@router.put("/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: int,
    data: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = await question_service.update_question(db, question_id, data)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    status_map = await question_service.get_status_map(db, user.id, [q.id])
    return _to_response(q, status_map.get(q.id, "todo"), q.id in status_map)


@router.put("/{question_id}/status", response_model=QuestionResponse)
async def set_question_status(
    question_id: int,
    data: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = await question_service.get_question(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    progress = await question_service.set_status(db, user.id, question_id, data.status)
    status_value = progress.status.value if hasattr(progress.status, "value") else progress.status
    return _to_response(q, status_value, True)


@router.post("/generate-descriptions")
async def generate_descriptions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Batch-generate descriptions for questions that don't have them."""
    from backend.agents.description_agent import DescriptionAgent

    result = await db.execute(
        select(Question).where(
            (Question.description.is_(None)) | (Question.description == "")
        )
    )
    questions = list(result.scalars().all())
    if not questions:
        return {"updated": 0, "message": "All questions already have descriptions"}

    batch_input = [{"id": q.id, "number": q.number, "title": q.title} for q in questions]

    agent = DescriptionAgent()
    batch_size = 5
    total_updated = 0

    for i in range(0, len(batch_input), batch_size):
        batch = batch_input[i : i + batch_size]

        try:
            descriptions = await agent.generate_batch(db, batch)
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"AI generation failed on batch {i // batch_size + 1}: {e}",
            )

        for desc in descriptions:
            matched_id = None
            for item in batch:
                if (desc.number and item["number"] == desc.number) or (
                    desc.title.lower() in item["title"].lower()
                    or item["title"].lower() in desc.title.lower()
                ):
                    matched_id = item["id"]
                    break

            if matched_id:
                await db.execute(
                    Question.__table__.update()
                    .where(Question.id == matched_id)
                    .values(
                        description=desc.description,
                        examples=[e.model_dump() for e in desc.examples],
                    )
                )
                total_updated += 1

        await db.commit()

    return {"updated": total_updated, "total_missing": len(batch_input)}


@router.delete("/{question_id}", status_code=204)
async def delete_question(question_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await question_service.delete_question(db, question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Question not found")
