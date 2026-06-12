from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db
from apps.api.models import Content, Schedule, User
from apps.api.schemas.schedule import (
    ScheduleIn, ScheduleListItem, ScheduleOut,
)
from apps.api.services.scheduler import create_schedule

router = APIRouter(tags=["scheduling"])


@router.post("/contents/{content_id}/schedule", response_model=ScheduleOut)
async def schedule_content(content_id: str, payload: ScheduleIn,
                           db: AsyncSession = Depends(get_db),
                           _: User = Depends(get_current_user)) -> ScheduleOut:
    content = await db.get(Content, content_id)
    if not content:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    schedule = await create_schedule(db, content, payload.scheduled_at, payload.timezone)
    await db.commit()
    await db.refresh(schedule)
    return ScheduleOut.model_validate(schedule)


@router.get("/schedule", response_model=list[ScheduleListItem])
async def list_schedule(
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ScheduleListItem]:
    stmt = select(Schedule, Content).join(Content, Content.id == Schedule.content_id)
    if start:
        stmt = stmt.where(Schedule.scheduled_at >= start)
    if end:
        stmt = stmt.where(Schedule.scheduled_at <= end)
    stmt = stmt.order_by(Schedule.scheduled_at)
    rows = (await db.execute(stmt)).all()
    return [
        ScheduleListItem(
            id=s.id, content_id=s.content_id, scheduled_at=s.scheduled_at,
            timezone=s.timezone, status=s.status, attempt_count=s.attempt_count,
            last_error=s.last_error, created_at=s.created_at,
            channel=c.channel, topic=c.topic,
        )
        for s, c in rows
    ]


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response)
async def cancel_schedule(schedule_id: str,
                          db: AsyncSession = Depends(get_db),
                          _: User = Depends(get_current_user)) -> Response:
    row = await db.get(Schedule, schedule_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "schedule not found")
    row.status = "cancelled"
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
