from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.celery_client import send as send_task
from apps.api.deps import get_current_user, get_db
from apps.api.models import Content, Job, User
from packages.shared.enums import Channel, JobType

router = APIRouter(tags=["publishing"])


def _task_for_channel(channel: str) -> tuple[str, str]:
    if channel == Channel.THREAD.value:
        return ("tasks.publish_threads", JobType.PUBLISH_THREADS.value)
    if channel == Channel.NEWSLETTER.value:
        return ("tasks.publish_newsletter", JobType.PUBLISH_NEWSLETTER.value)
    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                        f"channel {channel} does not support direct publishing")


@router.post("/contents/{content_id}/publish")
async def publish_now(content_id: str,
                      db: AsyncSession = Depends(get_db),
                      _: User = Depends(get_current_user)) -> dict:
    content = await db.get(Content, content_id)
    if not content:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    task_name, job_type = _task_for_channel(content.channel)
    job = Job(type=job_type, status="queued",
              payload={"content_id": content.id})
    db.add(job)
    await db.commit()
    send_task(task_name, job.id)
    return {"job_id": job.id}
