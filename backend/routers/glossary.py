from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.user import User
from backend.schemas.glossary import GlossaryTermResponse
from backend.services import glossary_service

router = APIRouter(prefix="/api/glossary", tags=["glossary"])


@router.get("", response_model=GlossaryTermResponse)
async def get_term(
    term: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return a cached glossary entry for a technique keyword, generating it on first use."""
    try:
        entry = await glossary_service.get_or_create(db, term)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not explain '{term}': {e}")
    return GlossaryTermResponse.model_validate(entry)
