from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.celery_client import send as send_task
from apps.api.deps import get_current_user, get_db
from apps.api.models import Job, LearningPattern, User
from packages.shared.enums import JobType

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("")
async def list_patterns(channel: str | None = Query(default=None),
                        db: AsyncSession = Depends(get_db),
                        _: User = Depends(get_current_user)) -> list[dict]:
    stmt = select(LearningPattern).order_by(desc(LearningPattern.created_at))
    if channel:
        stmt = stmt.where(LearningPattern.channel == channel)
    stmt = stmt.limit(100)
    rows = (await db.scalars(stmt)).all()
    return [
        {
            "id": r.id, "channel": r.channel, "pattern_type": r.pattern_type,
            "summary": r.summary, "examples": r.examples,
            "source": r.source, "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/run")
async def run_learning(channel: str | None = None,
                       db: AsyncSession = Depends(get_db),
                       _: User = Depends(get_current_user)) -> dict:
    job = Job(type=JobType.DIFF_LEARNING.value, status="queued",
              payload={"channel": channel})
    db.add(job)
    await db.commit()
    send_task("tasks.run_diff_learning", job.id)
    return {"job_id": job.id}
