from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.config import settings
from backend.database import get_db
from backend.models.api_config import ApiConfig
from backend.models.study_plan import UserStudyPreference
from backend.models.user import User
from backend.schemas.api_config import (
    ApiKeyCreate,
    ApiKeyResponse,
    ApiKeyTestRequest,
    ApiKeyTestResponse,
    InterviewDateUpdate,
    StudyPreferenceResponse,
    StudyPreferenceUpdate,
)
from backend.services.llm_client import llm_client

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _clamp_count(value: int | None, default: int) -> int:
    if value is None:
        return default
    return max(0, min(20, value))


async def _get_or_create_study_preferences(db: AsyncSession, user_id: str) -> UserStudyPreference:
    pref = (await db.execute(
        select(UserStudyPreference).where(UserStudyPreference.user_id == user_id)
    )).scalar_one_or_none()
    if pref:
        return pref
    pref = UserStudyPreference(user_id=user_id)
    db.add(pref)
    await db.commit()
    await db.refresh(pref)
    return pref


def _encrypt_key(key: str) -> str:
    if not settings.fernet_key:
        return key
    from cryptography.fernet import Fernet
    f = Fernet(settings.fernet_key.encode())
    return f.encrypt(key.encode()).decode()


def _mask_key(encrypted_key: str) -> str:
    try:
        if settings.fernet_key:
            from cryptography.fernet import Fernet
            f = Fernet(settings.fernet_key.encode())
            key = f.decrypt(encrypted_key.encode()).decode()
        else:
            key = encrypted_key
        return f"{key[:7]}...{key[-4:]}" if len(key) > 11 else "***"
    except Exception:
        return "***"


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ApiConfig).where(ApiConfig.user_id == user.id))
    configs = result.scalars().all()
    return [
        ApiKeyResponse(
            provider=c.provider,
            model=c.model,
            is_active=c.is_active,
            api_key_masked=_mask_key(c.api_key_encrypted),
        )
        for c in configs
    ]


@router.post("/api-keys", response_model=ApiKeyResponse)
async def upsert_api_key(
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiConfig).where(
            ApiConfig.user_id == user.id, ApiConfig.provider == data.provider
        )
    )
    config = result.scalar_one_or_none()

    default_models = {"openai": "gpt-4o", "anthropic": "claude-sonnet-4-20250514"}

    if config:
        config.api_key_encrypted = _encrypt_key(data.api_key)
        config.model = data.model or config.model
        config.is_active = data.is_active
    else:
        config = ApiConfig(
            user_id=user.id,
            provider=data.provider,
            api_key_encrypted=_encrypt_key(data.api_key),
            model=data.model or default_models.get(data.provider, "gpt-4o"),
            is_active=data.is_active,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)
    return ApiKeyResponse(
        provider=config.provider,
        model=config.model,
        is_active=config.is_active,
        api_key_masked=_mask_key(config.api_key_encrypted),
    )


@router.delete("/api-keys/{provider}", status_code=204)
async def delete_api_key(
    provider: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiConfig).where(
            ApiConfig.user_id == user.id, ApiConfig.provider == provider
        )
    )
    config = result.scalar_one_or_none()
    if config:
        await db.delete(config)
        await db.commit()


@router.post("/api-keys/test", response_model=ApiKeyTestResponse)
async def test_api_key(
    req: ApiKeyTestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if req.api_key:
        success, message = await llm_client.test_key(req.provider, req.api_key)
    else:
        config = await llm_client._get_config(db, req.provider)
        if not config:
            return ApiKeyTestResponse(success=False, message="No API key configured")
        key = llm_client._decrypt_key(config.api_key_encrypted)
        success, message = await llm_client.test_key(req.provider, key)
    return ApiKeyTestResponse(success=success, message=message)


@router.get("/interview-date")
async def get_interview_date(user: User = Depends(get_current_user)):
    return {"date": user.interview_date or settings.interview_date}


@router.put("/interview-date")
async def update_interview_date(
    data: InterviewDateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user.interview_date = data.date
    await db.commit()
    return {"date": user.interview_date}


@router.get("/study-preferences", response_model=StudyPreferenceResponse)
async def get_study_preferences(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pref = await _get_or_create_study_preferences(db, user.id)
    return StudyPreferenceResponse(
        review_count=pref.review_count,
        template_count=pref.template_count,
        google_count=pref.google_count,
        hard_count=pref.hard_count,
        pattern_count=pref.pattern_count,
        daily_refresh_hour=pref.daily_refresh_hour,
        timezone_offset=pref.timezone_offset,
    )


@router.put("/study-preferences", response_model=StudyPreferenceResponse)
async def update_study_preferences(
    data: StudyPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pref = await _get_or_create_study_preferences(db, user.id)
    pref.review_count = _clamp_count(data.review_count, pref.review_count)
    pref.template_count = _clamp_count(data.template_count, pref.template_count)
    pref.google_count = _clamp_count(data.google_count, pref.google_count)
    pref.hard_count = _clamp_count(data.hard_count, pref.hard_count)
    pref.pattern_count = _clamp_count(data.pattern_count, pref.pattern_count)
    if data.daily_refresh_hour is not None:
        pref.daily_refresh_hour = max(0, min(23, data.daily_refresh_hour))
    if data.timezone_offset is not None:
        pref.timezone_offset = max(-12, min(14, data.timezone_offset))
    await db.commit()
    await db.refresh(pref)
    return StudyPreferenceResponse(
        review_count=pref.review_count,
        template_count=pref.template_count,
        google_count=pref.google_count,
        hard_count=pref.hard_count,
        pattern_count=pref.pattern_count,
        daily_refresh_hour=pref.daily_refresh_hour,
        timezone_offset=pref.timezone_offset,
    )
