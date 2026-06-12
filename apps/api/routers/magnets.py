from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.celery_client import send as send_task
from apps.api.core.db import get_session
from apps.api.deps import get_current_user, get_db
from apps.api.models import Content, Job, LeadMagnet, User
from packages.shared.enums import JobType

router = APIRouter(tags=["magnets"])


@router.post("/contents/{content_id}/magnet/render")
async def render_magnet(content_id: str,
                        db: AsyncSession = Depends(get_db),
                        _: User = Depends(get_current_user)) -> dict:
    content = await db.get(Content, content_id)
    if not content:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    magnet = await db.scalar(select(LeadMagnet).where(LeadMagnet.content_id == content_id))
    if not magnet:
        magnet = LeadMagnet(content_id=content_id,
                            public_token=secrets.token_urlsafe(16))
        db.add(magnet)
        await db.flush()
    job = Job(type=JobType.RENDER_MAGNET.value, status="queued",
              payload={"content_id": content.id, "magnet_id": magnet.id})
    db.add(job)
    await db.commit()
    send_task("tasks.render_magnet_pdf", job.id)
    return {"job_id": job.id, "public_token": magnet.public_token}


@router.get("/magnets/{public_token}")
async def download_magnet(public_token: str,
                          db: AsyncSession = Depends(get_session)) -> FileResponse:
    magnet = await db.scalar(select(LeadMagnet).where(LeadMagnet.public_token == public_token))
    if not magnet or not magnet.pdf_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    path = Path(magnet.pdf_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file missing")
    magnet.download_count = (magnet.download_count or 0) + 1
    await db.commit()
    return FileResponse(path, media_type="application/pdf",
                        filename=f"{magnet.public_token}.pdf")
