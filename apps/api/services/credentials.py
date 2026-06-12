"""Credential vault — stores integration secrets encrypted with Fernet."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.security import decrypt_payload, encrypt_payload
from apps.api.models import IntegrationCredential


async def get_credentials(db: AsyncSession, provider: str) -> dict[str, Any] | None:
    row = await db.scalar(select(IntegrationCredential).where(
        IntegrationCredential.provider == provider))
    if not row:
        return None
    try:
        return json.loads(decrypt_payload(row.encrypted_payload).decode())
    except (ValueError, json.JSONDecodeError):
        return None


async def upsert_credentials(
    db: AsyncSession, provider: str, credentials: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> IntegrationCredential:
    payload = encrypt_payload(json.dumps(credentials).encode())
    existing = await db.scalar(select(IntegrationCredential).where(
        IntegrationCredential.provider == provider))
    if existing:
        existing.encrypted_payload = payload
        existing.status = "ok"
        existing.meta = meta or {}
        await db.flush()
        return existing
    row = IntegrationCredential(
        provider=provider, encrypted_payload=payload,
        status="ok", meta=meta or {},
    )
    db.add(row)
    await db.flush()
    return row
