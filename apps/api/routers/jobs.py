from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from apps.api.deps import get_current_user, get_db
from apps.api.events import event_stream
from apps.api.models import Job, User
from apps.api.schemas.job import JobOut

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(status_: str | None = Query(default=None, alias="status"),
                    limit: int = Query(default=50, le=200),
                    db: AsyncSession = Depends(get_db),
                    _: User = Depends(get_current_user)) -> list[JobOut]:
    stmt = select(Job).order_by(desc(Job.created_at)).limit(limit)
    if status_:
        stmt = stmt.where(Job.status == status_)
    rows = (await db.scalars(stmt)).all()
    return [JobOut.model_validate(r) for r in rows]


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db),
                  _: User = Depends(get_current_user)) -> JobOut:
    row = await db.get(Job, job_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return JobOut.model_validate(row)


@router.get("/events/stream")
async def events_stream(job_id: str,
                        _: User = Depends(get_current_user)) -> EventSourceResponse:
    return EventSourceResponse(event_stream(job_id))
