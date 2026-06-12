"""발행 라우터 - 즉시 발행 + 발행 로그"""
import asyncio
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ContentStatus, JobKind, JobStatus
from app.db.base import SessionLocal, get_db
from app.db.models import Content, GenerationJob, PublishLog
from app.schemas.generation import JobAccepted
from app.services import publisher

router = APIRouter(tags=["publish"])

PUBLISHABLE_STATUSES = {
    ContentStatus.review_done.value,
    ContentStatus.publish_wait.value,
    ContentStatus.failed.value,  # 수동 재시도 허용
}


class PublishLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content_id: int
    success: bool
    dry_run: bool
    posts_count: int
    external_ids: list | None
    error: str | None
    created_at: datetime


def _run_publish_job(job_id: int, content_id: int):
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        content = db.get(Content, content_id)
        if not job or not content:
            return
        job.status = JobStatus.running.value
        db.commit()

        log = publisher.publish_content(db, content)
        job.content_id = content_id
        job.status = JobStatus.done.value if log.success else JobStatus.failed.value
        job.error = log.error
        job.finished_at = datetime.now()
        db.commit()
    finally:
        db.close()


async def _run_publish_async(job_id: int, content_id: int):
    await asyncio.to_thread(_run_publish_job, job_id, content_id)


@router.post("/contents/{content_id}/publish", response_model=JobAccepted, status_code=202)
def publish_now(content_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(404, "콘텐츠를 찾을 수 없습니다")
    if content.status not in PUBLISHABLE_STATUSES:
        raise HTTPException(409, f"'{content.status}' 상태에서는 발행할 수 없습니다")

    job = GenerationJob(
        kind=JobKind.publish.value, status=JobStatus.pending.value,
        params={"content_id": content_id},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background.add_task(_run_publish_async, job.id, content_id)
    return JobAccepted(job_id=job.id)


@router.get("/contents/{content_id}/publish-logs", response_model=list[PublishLogOut])
def publish_logs(content_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(PublishLog)
        .where(PublishLog.content_id == content_id)
        .order_by(PublishLog.created_at.desc())
    ).all()
