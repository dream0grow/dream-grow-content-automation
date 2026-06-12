"""Scheduler service — creates Schedule rows and enqueues publish jobs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import Content, Schedule


async def create_schedule(
    db: AsyncSession, content: Content,
    scheduled_at: datetime, timezone: str,
) -> Schedule:
    schedule = Schedule(
        content_id=content.id,
        scheduled_at=scheduled_at,
        timezone=timezone,
        status="pending",
    )
    db.add(schedule)
    if content.status not in ("published", "failed"):
        content.status = "scheduled"
    await db.flush()
    return schedule
