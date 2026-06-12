from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.celery_client import send as send_task
from apps.api.deps import get_current_user, get_db
from apps.api.models import Content, Job, User
from apps.api.schemas.content import GenerateRequest, GenerateResponse
from packages.shared.enums import Channel, JobType, ContentStatus

router = APIRouter(prefix="/contents", tags=["generation"])

VALID_CHANNELS = {c.value for c in Channel}


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate(payload: GenerateRequest,
                   db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)) -> GenerateResponse:
    if payload.channel not in VALID_CHANNELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown channel: {payload.channel}")
    content = Content(
        channel=payload.channel,
        topic=payload.topic,
        category=payload.category,
        status=ContentStatus.DRAFT.value,
        body_md="",
        frontmatter={"주제": payload.topic, "카테고리": payload.category or "",
                     "채널": payload.channel, "출처": "AI생성"},
        created_by=user.id,
    )
    db.add(content)
    await db.flush()

    job = Job(
        type=JobType.GENERATE.value,
        status="queued",
        payload={
            "content_id": content.id,
            "channel": payload.channel,
            "topic": payload.topic,
            "category": payload.category,
            "tone": payload.tone,
            "magnet_type": payload.magnet_type,
            "reference_ids": payload.reference_ids,
        },
    )
    db.add(job)
    await db.commit()

    send_task("tasks.generate_content", job.id)
    return GenerateResponse(content_id=content.id, job_id=job.id)
