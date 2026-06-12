from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content_id: str
    captured_at: datetime
    views: int
    likes: int
    comments: int
    shares: int
    reach: int


class SummaryOut(BaseModel):
    period: str
    total_content: int
    total_published: int
    total_views: int
    total_likes: int
    total_comments: int
    top_by_views: list[dict]
