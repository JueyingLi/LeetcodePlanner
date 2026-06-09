from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.attempt import UserAttempt
from backend.schemas.attempt import AttemptUpdate


async def get_attempt(db: AsyncSession, user_id: str, attempt_id: int) -> UserAttempt | None:
    result = await db.execute(
        select(UserAttempt).where(
            UserAttempt.id == attempt_id, UserAttempt.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def get_attempts_for_question(
    db: AsyncSession, user_id: str, question_id: int
) -> list[UserAttempt]:
    result = await db.execute(
        select(UserAttempt)
        .where(UserAttempt.user_id == user_id)
        .where(UserAttempt.question_id == question_id)
        .order_by(UserAttempt.created_at.desc())
    )
    return list(result.scalars().all())


async def create_attempt(db: AsyncSession, user_id: str, question_id: int) -> UserAttempt:
    attempt = UserAttempt(user_id=user_id, question_id=question_id)
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def update_attempt(
    db: AsyncSession, user_id: str, attempt_id: int, data: AttemptUpdate
) -> UserAttempt | None:
    attempt = await get_attempt(db, user_id, attempt_id)
    if not attempt:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(attempt, key, value)
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def save_feedback(
    db: AsyncSession, user_id: str, attempt_id: int, step: str, feedback: dict
) -> UserAttempt | None:
    attempt = await get_attempt(db, user_id, attempt_id)
    if not attempt:
        return None
    existing = attempt.ai_feedback or {}
    existing[step] = feedback
    attempt.ai_feedback = existing
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def delete_feedback(
    db: AsyncSession, user_id: str, attempt_id: int, step: str
) -> bool:
    attempt = await get_attempt(db, user_id, attempt_id)
    if not attempt:
        return False
    existing = attempt.ai_feedback or {}
    if step not in existing:
        return False
    del existing[step]
    attempt.ai_feedback = existing
    flag_modified(attempt, "ai_feedback")
    await db.commit()
    return True


async def delete_attempt(db: AsyncSession, user_id: str, attempt_id: int) -> bool:
    attempt = await get_attempt(db, user_id, attempt_id)
    if not attempt:
        return False
    await db.delete(attempt)
    await db.commit()
    return True
