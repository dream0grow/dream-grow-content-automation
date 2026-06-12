from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScheduleIn(BaseModel):
    scheduled_at: datetime
    timezone: str = "Asia/Seoul"


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content_id: str
    scheduled_at: datetime
    timezone: str
    status: str
    attempt_count: int
    last_error: str | None
    created_at: datetime


class ScheduleListItem(ScheduleOut):
    channel: str
    topic: str
