from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.agents.parser_agent import ParserAgent
from backend.models.user import User
from backend.routers.questions import _to_response
from backend.schemas.question import QuestionImportRequest, QuestionImportResponse
from backend.services import question_service, subtopic_service

router = APIRouter(prefix="/api/questions", tags=["import"])


@router.post("/import", response_model=QuestionImportResponse)
async def import_questions(
    req: QuestionImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = ParserAgent()
    try:
        parsed = await agent.parse(db, req.text, req.default_source)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI parsing failed: {e}")

    added = 0
    updated = 0
    skipped = 0
    result_questions = []

    for q_data in parsed:
        existing = None
        if q_data.number:
            existing = await question_service.get_question_by_number(db, q_data.number)

        if existing:
            existing_sources = [s["name"] if isinstance(s, dict) else s.name for s in (existing.sources or [])]
            new_sources = [s.model_dump() for s in q_data.sources if s.name not in existing_sources]
            if new_sources:
                merged = list(existing.sources or []) + new_sources
                from backend.schemas.question import QuestionUpdate
                await question_service.update_question(
                    db, existing.id, QuestionUpdate(sources=merged)
                )
                updated += 1
            else:
                skipped += 1
            q = await question_service.get_question(db, existing.id)
        else:
            q = await question_service.create_question(db, q_data)
            added += 1

        if q:
            if q_data.subtopics:
                primary_topic = q_data.topics[0] if q_data.topics else "Uncategorized"
                await subtopic_service.ensure_subtopics_exist(
                    db, q_data.subtopics, primary_topic
                )
            result_questions.append(_to_response(q))

    return QuestionImportResponse(
        added=added,
        updated=updated,
        skipped=skipped,
        questions=result_questions,
    )
