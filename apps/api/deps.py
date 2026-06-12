from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.security import decode_token
from apps.api.models import User


async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncSession:
    return session


def _extract_bearer(request: Request) -> str:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    token = request.cookies.get("access_token")
    if token:
        return token
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_bearer(request)
    try:
        claims = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc
    if claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "expected access token")
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing subject")
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user
