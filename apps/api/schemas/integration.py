from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IntegrationOut(BaseModel):
    provider: str
    status: str
    connected: bool
    meta: dict[str, Any] = {}


class IntegrationUpdate(BaseModel):
    credentials: dict[str, Any]


class IntegrationTestResult(BaseModel):
    ok: bool
    message: str | None = None
