"""Supabase JWT authentication for FastAPI.

The frontend authenticates with Supabase (Google OAuth) and sends the
resulting access token as `Authorization: Bearer <jwt>`. We verify the token
locally, then get-or-create a local `User` row keyed by the Supabase user UUID.

Verification supports both Supabase signing modes:
- New **asymmetric signing keys** (ES256/RS256): verified against the project's
  public keys (JWKS), fetched from SUPABASE_URL. No shared secret needed.
- Legacy **HS256 shared secret**: verified with SUPABASE_JWT_SECRET if set.

The current user id is also published to a contextvar so that deeply-nested
code (e.g. the LLM client resolving a per-user API key) can read it without
threading the id through every function signature.
"""

import contextvars
import functools

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models.user import User

# Request-scoped current user id. Set in get_current_user; read by llm_client.
current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user_id", default=None
)


@functools.lru_cache(maxsize=1)
def _jwks_client() -> "jwt.PyJWKClient":
    url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    return jwt.PyJWKClient(url)


def _decode_token(token: str) -> dict:
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    try:
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise HTTPException(
                    status_code=500,
                    detail="Token is HS256 but SUPABASE_JWT_SECRET is not configured",
                )
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_aud,
            )
        # Asymmetric signing keys — verify against the project's public JWKS.
        if not settings.supabase_url:
            raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured")
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=settings.supabase_jwt_aud,
        )
    except HTTPException:
        raise
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    payload = _decode_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")
    email = payload.get("email")

    # Publish for contextvar consumers (e.g. per-user LLM key lookup).
    current_user_id.set(user_id)

    # Just-in-time provisioning: get-or-create the local user row.
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(id=user_id, email=email, interview_date=settings.interview_date)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif email and user.email != email:
        user.email = email
        await db.commit()
        await db.refresh(user)

    return user


async def get_current_user_id(user: User = Depends(get_current_user)) -> str:
    return user.id
