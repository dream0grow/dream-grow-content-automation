"""Honcho memory wrapper — receives credentials via constructor."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MemoryContext:
    style: str = ""
    brand: str = ""
    corrections: str = ""


class HonchoMemory:
    """Optional Honcho-backed style memory. If no API key, methods are no-ops."""

    def __init__(self, api_key: str | None, app_id: str = "dream-grow"):
        self.api_key = api_key
        self.app_id = app_id
        self._client = None
        if api_key:
            try:
                from honcho import Honcho  # type: ignore
                self._client = Honcho(api_key=api_key)
            except Exception:
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def fetch_context(self, channel: str) -> MemoryContext:
        if not self.enabled:
            return MemoryContext()
        try:
            style = self._read_session(f"{channel}-style")
            brand = self._read_session("brand-identity")
            corrections = self._read_session(f"{channel}-corrections")
            return MemoryContext(style=style, brand=brand, corrections=corrections)
        except Exception:
            return MemoryContext()

    def save_correction(self, channel: str, summary: str) -> None:
        if not self.enabled:
            return
        try:
            self._append_session(f"{channel}-corrections", summary)
        except Exception:
            pass

    def _read_session(self, name: str) -> str:  # pragma: no cover - SDK-specific
        if not self._client:
            return ""
        try:
            session = self._client.apps.users.sessions.get_or_create(
                app_id=self.app_id, user_id="default", session_id=name,
            )
            msgs = self._client.apps.users.sessions.messages.list(
                app_id=self.app_id, user_id="default", session_id=session.id, reverse=True, size=10,
            )
            return "\n".join(m.content for m in msgs.items if getattr(m, "content", None))
        except Exception:
            return ""

    def _append_session(self, name: str, content: str) -> None:  # pragma: no cover
        if not self._client:
            return
        try:
            session = self._client.apps.users.sessions.get_or_create(
                app_id=self.app_id, user_id="default", session_id=name,
            )
            self._client.apps.users.sessions.messages.create(
                app_id=self.app_id, user_id="default", session_id=session.id,
                is_user=True, content=content,
            )
        except Exception:
            pass
