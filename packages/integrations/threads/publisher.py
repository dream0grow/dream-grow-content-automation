"""Threads publisher — ported from legacy/threads_publisher.py.

The legacy version parsed Obsidian markdown files in place and rewrote
frontmatter on disk. This refactor:
- accepts a raw body string (no file I/O)
- takes credentials via the constructor (no env reads)
- returns structured PublishOutcome objects for the worker to persist
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Iterable

import httpx

THREADS_API_BASE = "https://graph.threads.net/v1.0"
POST_DELAY_SECONDS = 2
MAX_POST_LENGTH = 500


@dataclass
class PublishOutcome:
    success: bool
    posts: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def first_id(self) -> str | None:
        return self.posts[0]["id"] if self.posts else None

    @property
    def first_url(self) -> str | None:
        return self.posts[0].get("url") if self.posts else None


def split_thread_posts(body: str) -> list[str]:
    """Split a thread markdown body into individual posts.

    Honors both '---' separators and bare numbered prefixes like '1/'.
    """
    body = body.strip()
    if "\n---\n" in body or body.startswith("---\n") or body.endswith("\n---"):
        parts = re.split(r"\n---\n", body)
    else:
        parts = body.split("\n\n")
    posts: list[str] = []
    for part in parts:
        text = re.sub(r"^\[?\d+/\d*\]?\s*", "", part.strip())
        if text:
            posts.append(text)
    return posts


class ThreadsPublisher:
    """Stateless HTTP client wrapping the Meta Threads Graph API."""

    def __init__(self, access_token: str, user_id: str,
                 client: httpx.Client | None = None,
                 base_url: str = THREADS_API_BASE,
                 post_delay: float = POST_DELAY_SECONDS):
        self.access_token = access_token
        self.user_id = user_id
        self.client = client or httpx.Client(timeout=30)
        self.base_url = base_url.rstrip("/")
        self.post_delay = post_delay

    def publish_thread(self, posts: Iterable[str]) -> PublishOutcome:
        posts = [p for p in posts if p]
        if not posts:
            return PublishOutcome(success=False, error="empty thread")
        published: list[dict] = []
        parent_id: str | None = None
        for i, post_text in enumerate(posts):
            container = self._create_container(post_text, reply_to=parent_id)
            if container.get("error"):
                return PublishOutcome(success=False, posts=published, error=container["error"])
            container_id = container["id"]
            pub = self._publish_container(container_id)
            if pub.get("error"):
                return PublishOutcome(success=False, posts=published, error=pub["error"])
            media_id = pub["id"]
            published.append({
                "id": media_id,
                "text": post_text[:80],
                "url": f"https://www.threads.net/@{self.user_id}/post/{media_id}",
            })
            if i == 0:
                parent_id = media_id
            if i < len(posts) - 1 and self.post_delay > 0:
                time.sleep(self.post_delay)
        return PublishOutcome(success=True, posts=published)

    def _create_container(self, text: str, reply_to: str | None = None) -> dict:
        params = {
            "media_type": "TEXT",
            "text": text[:MAX_POST_LENGTH],
            "access_token": self.access_token,
        }
        if reply_to:
            params["reply_to_id"] = reply_to
        try:
            resp = self.client.post(f"{self.base_url}/{self.user_id}/threads", params=params)
        except httpx.HTTPError as exc:
            return {"error": f"transport error: {exc}"}
        if resp.status_code != 200:
            return {"error": f"container failed [{resp.status_code}]: {resp.text}"}
        return {"id": resp.json().get("id")}

    def _publish_container(self, container_id: str) -> dict:
        try:
            resp = self.client.post(
                f"{self.base_url}/{self.user_id}/threads_publish",
                params={"creation_id": container_id, "access_token": self.access_token},
            )
        except httpx.HTTPError as exc:
            return {"error": f"transport error: {exc}"}
        if resp.status_code != 200:
            return {"error": f"publish failed [{resp.status_code}]: {resp.text}"}
        return {"id": resp.json().get("id")}
