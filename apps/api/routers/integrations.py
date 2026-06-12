from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db
from apps.api.models import IntegrationCredential, User
from apps.api.schemas.integration import (
    IntegrationOut, IntegrationTestResult, IntegrationUpdate,
)
from apps.api.services.credentials import get_credentials, upsert_credentials
from packages.shared.enums import IntegrationProvider

router = APIRouter(prefix="/integrations", tags=["integrations"])

VALID_PROVIDERS = {p.value for p in IntegrationProvider}


@router.get("", response_model=list[IntegrationOut])
async def list_integrations(db: AsyncSession = Depends(get_db),
                            _: User = Depends(get_current_user)) -> list[IntegrationOut]:
    rows = (await db.scalars(select(IntegrationCredential))).all()
    by_provider = {r.provider: r for r in rows}
    return [
        IntegrationOut(
            provider=p,
            status=by_provider[p].status if p in by_provider else "missing",
            connected=p in by_provider,
            meta=by_provider[p].meta if p in by_provider else {},
        )
        for p in VALID_PROVIDERS
    ]


@router.put("/{provider}", response_model=IntegrationOut)
async def upsert_integration(provider: str, payload: IntegrationUpdate,
                             db: AsyncSession = Depends(get_db),
                             _: User = Depends(get_current_user)) -> IntegrationOut:
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown provider")
    row = await upsert_credentials(db, provider, payload.credentials)
    await db.commit()
    return IntegrationOut(provider=row.provider, status=row.status,
                          connected=True, meta=row.meta)


@router.post("/{provider}/test", response_model=IntegrationTestResult)
async def test_integration(provider: str,
                           db: AsyncSession = Depends(get_db),
                           _: User = Depends(get_current_user)) -> IntegrationTestResult:
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown provider")
    creds = await get_credentials(db, provider)
    if not creds:
        return IntegrationTestResult(ok=False, message="no credentials stored")
    # Minimal ping per provider — real implementations would hit /me endpoints.
    if provider == IntegrationProvider.THREADS.value:
        ok = all(k in creds for k in ("access_token", "user_id"))
    elif provider == IntegrationProvider.MAILY.value:
        ok = "access_token" in creds
    elif provider == IntegrationProvider.HONCHO.value:
        ok = "api_key" in creds
    elif provider == IntegrationProvider.ANTHROPIC.value:
        ok = "api_key" in creds
    else:
        ok = False
    return IntegrationTestResult(ok=ok,
                                 message="credentials present" if ok else "missing required fields")
