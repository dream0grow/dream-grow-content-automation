"""Maily.so newsletter client (stateless)."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

MAILY_API_BASE = "https://api.maily.so/v1"


@dataclass
class MailyResult:
    success: bool
    note_id: str | None = None
    note_url: str | None = None
    error: str | None = None


class MailyClient:
    def __init__(self, access_token: str, base_url: str = MAILY_API_BASE,
                 client: httpx.Client | None = None):
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=60)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"}

    def create_draft(self, title: str, body_md: str, subtitle: str = "") -> MailyResult:
        try:
            resp = self.client.post(
                f"{self.base_url}/notes",
                headers=self._headers(),
                json={"title": title, "subtitle": subtitle, "content": body_md,
                      "status": "draft"},
            )
        except httpx.HTTPError as exc:
            return MailyResult(success=False, error=f"transport: {exc}")
        if resp.status_code >= 400:
            return MailyResult(success=False, error=f"{resp.status_code}: {resp.text}")
        data = resp.json()
        return MailyResult(success=True, note_id=str(data.get("id")),
                           note_url=data.get("url"))

    def publish(self, note_id: str) -> MailyResult:
        try:
            resp = self.client.post(
                f"{self.base_url}/notes/{note_id}/publish",
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            return MailyResult(success=False, error=f"transport: {exc}")
        if resp.status_code >= 400:
            return MailyResult(success=False, error=f"{resp.status_code}: {resp.text}")
        data = resp.json()
        return MailyResult(success=True, note_id=note_id, note_url=data.get("url"))
