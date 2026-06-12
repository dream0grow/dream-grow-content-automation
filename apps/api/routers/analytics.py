from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db
from apps.api.models import AnalyticsSnapshot, Content, User
from apps.api.schemas.analytics import SnapshotOut, SummaryOut

router = APIRouter(tags=["analytics"])


@router.get("/contents/{content_id}/analytics", response_model=list[SnapshotOut])
async def content_analytics(content_id: str,
                            db: AsyncSession = Depends(get_db),
                            _: User = Depends(get_current_user)) -> list[SnapshotOut]:
    if not await db.get(Content, content_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    rows = (await db.scalars(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.content_id == content_id)
        .order_by(AnalyticsSnapshot.captured_at)
    )).all()
    return [SnapshotOut.model_validate(r) for r in rows]


@router.get("/analytics/summary", response_model=SummaryOut)
async def summary(period: str = Query(default="7d"),
                  db: AsyncSession = Depends(get_db),
                  _: User = Depends(get_current_user)) -> SummaryOut:
    days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 7)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    total_content = (await db.scalar(select(func.count(Content.id)))) or 0
    total_published = (await db.scalar(
        select(func.count(Content.id)).where(Content.status == "published")
    )) or 0
    # Latest snapshot per content within window: simple sum of latest values
    latest_subq = (
        select(
            AnalyticsSnapshot.content_id,
            func.max(AnalyticsSnapshot.captured_at).label("captured_at"),
        )
        .where(AnalyticsSnapshot.captured_at >= since)
        .group_by(AnalyticsSnapshot.content_id)
        .subquery()
    )
    latest_stmt = (
        select(AnalyticsSnapshot)
        .join(latest_subq,
              (AnalyticsSnapshot.content_id == latest_subq.c.content_id) &
              (AnalyticsSnapshot.captured_at == latest_subq.c.captured_at))
    )
    snapshots = (await db.scalars(latest_stmt)).all()
    totals = {"views": 0, "likes": 0, "comments": 0}
    for s in snapshots:
        totals["views"] += s.views
        totals["likes"] += s.likes
        totals["comments"] += s.comments

    top_stmt = (
        select(Content.id, Content.topic, Content.channel, AnalyticsSnapshot.views)
        .join(AnalyticsSnapshot, AnalyticsSnapshot.content_id == Content.id)
        .order_by(desc(AnalyticsSnapshot.views))
        .limit(5)
    )
    top = (await db.execute(top_stmt)).all()

    return SummaryOut(
        period=period, total_content=total_content,
        total_published=total_published,
        total_views=totals["views"], total_likes=totals["likes"],
        total_comments=totals["comments"],
        top_by_views=[
            {"id": r.id, "topic": r.topic, "channel": r.channel, "views": r.views}
            for r in top
        ],
    )
