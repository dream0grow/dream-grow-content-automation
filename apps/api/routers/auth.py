from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.config import get_settings
from apps.api.core.security import (
    create_access_token, create_refresh_token, decode_token, verify_password,
)
from apps.api.deps import get_current_user, get_db
from apps.api.models import User
from apps.api.schemas.auth import (
    LoginRequest, RefreshRequest, TokenResponse, UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response,
                db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user or not user.hashed_password or not verify_password(
            payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    settings = get_settings()
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    response.set_cookie(
        "access_token", access, max_age=settings.jwt_access_minutes * 60,
        httponly=True, samesite="lax",
    )
    return TokenResponse(
        access_token=access, refresh_token=refresh,
        expires_in=settings.jwt_access_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "expected refresh token")
    settings = get_settings()
    access = create_access_token(claims["sub"])
    return TokenResponse(
        access_token=access, refresh_token=payload.refresh_token,
        expires_in=settings.jwt_access_minutes * 60,
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, name=user.name)
