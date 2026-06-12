"""발행 캘린더 라우터"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ContentStatus
from app.db.base import get_db
from app.db.models import Content
from app.schemas.calendar import (
    AutoScheduleItem,
    AutoScheduleOut,
    AutoScheduleRequest,
    CalendarDay,
    CalendarItem,
    CalendarOut,
)
from app.services import scheduler_svc

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("", response_model=CalendarOut)
def get_calendar(start: date, end: date, db: Session = Depends(get_db)):
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    rows = db.scalars(
        select(Content).where(
            Content.scheduled_at.isnot(None),
            Content.scheduled_at >= start_dt,
            Content.scheduled_at <= end_dt,
            Content.status.in_([
                ContentStatus.publish_wait.value,
                ContentStatus.published.value,
                ContentStatus.failed.value,
            ]),
        ).order_by(Content.scheduled_at)
    ).all()

    by_date: dict[str, list[CalendarItem]] = defaultdict(list)
    for c in rows:
        by_date[c.scheduled_at.strftime("%Y-%m-%d")].append(CalendarItem(
            content_id=c.id,
            time=c.scheduled_at.strftime("%H:%M"),
            title=c.title,
            category=c.category,
            type=c.type,
            status=c.status,
        ))

    days = []
    current = start
    while current <= end:
        key = current.strftime("%Y-%m-%d")
        days.append(CalendarDay(date=current, items=by_date.get(key, [])))
        current += timedelta(days=1)

    return CalendarOut(days=days)


@router.post("/auto-schedule", response_model=AutoScheduleOut)
def auto_schedule(payload: AutoScheduleRequest, db: Session = Depends(get_db)):
    assignments = scheduler_svc.auto_schedule(db, days=payload.days)
    items = [
        AutoScheduleItem(
            content_id=c.id, title=c.title, category=c.category, scheduled_at=dt,
        )
        for c, dt in assignments
    ]
    if not payload.preview and assignments:
        scheduler_svc.commit_assignments(db, assignments)
    return AutoScheduleOut(committed=not payload.preview, assignments=items)
