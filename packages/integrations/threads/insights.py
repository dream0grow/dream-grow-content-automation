"""Threads insights — minimal pure fetcher.

Replaces the file-bound legacy/threads_insights.py. Returns ThreadMetrics rows;
worker is responsible for persisting analytics_snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

INSIGHT_METRICS = ["views", "likes", "replies", "reposts", "quotes"]


@dataclass
class ThreadMetrics:
    media_id: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    reach: int = 0
    raw: dict | None = None


class ThreadsInsightsClient:
    def __init__(self, access_token: str, base_url: str = "https://graph.threads.net/v1.0",
                 client: httpx.Client | None = None):
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=30)

    def fetch_metrics(self, media_id: str) -> ThreadMetrics | None:
        try:
            resp = self.client.get(
                f"{self.base_url}/{media_id}/insights",
                params={
                    "metric": ",".join(INSIGHT_METRICS),
                    "access_token": self.access_token,
                },
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        payload = resp.json()
        values: dict[str, int] = {}
        for item in payload.get("data", []):
            name = item.get("name")
            if not name:
                continue
            vals = item.get("values") or [{}]
            values[name] = int(vals[0].get("value") or 0)
        return ThreadMetrics(
            media_id=media_id,
            views=values.get("views", 0),
            likes=values.get("likes", 0),
            comments=values.get("replies", 0),
            shares=values.get("reposts", 0) + values.get("quotes", 0),
            reach=values.get("views", 0),
            raw=payload,
        )
