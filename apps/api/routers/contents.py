from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db
from apps.api.models import Content, ContentVersion, User
from apps.api.schemas.content import (
    ContentIn, ContentOut, ContentPatch, ContentSummary,
    ContentVersionOut, IssueOut, ReviewResponse,
)
from apps.api.services.validator import review_body

router = APIRouter(prefix="/contents", tags=["contents"])


@router.get("", response_model=list[ContentSummary])
async def list_contents(
    channel: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ContentSummary]:
    stmt = select(Content).order_by(desc(Content.updated_at))
    if channel:
        stmt = stmt.where(Content.channel == channel)
    if status_:
        stmt = stmt.where(Content.status == status_)
    if category:
        stmt = stmt.where(Content.category == category)
    if q:
        stmt = stmt.where(Content.topic.ilike(f"%{q}%"))
    stmt = stmt.limit(limit).offset(offset)
    rows = (await db.scalars(stmt)).all()
    return [ContentSummary.model_validate(r) for r in rows]


@router.post("", response_model=ContentOut, status_code=status.HTTP_201_CREATED)
async def create_content(payload: ContentIn,
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)) -> ContentOut:
    row = Content(
        channel=payload.channel,
        topic=payload.topic,
        category=payload.category,
        status="draft",
        body_md=payload.body_md,
        frontmatter=payload.frontmatter,
        created_by=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ContentOut.model_validate(row)


async def _get_or_404(db: AsyncSession, content_id: str) -> Content:
    row = await db.get(Content, content_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content not found")
    return row


@router.get("/{content_id}", response_model=ContentOut)
async def get_content(content_id: str, db: AsyncSession = Depends(get_db),
                      _: User = Depends(get_current_user)) -> ContentOut:
    return ContentOut.model_validate(await _get_or_404(db, content_id))


@router.patch("/{content_id}", response_model=ContentOut)
async def patch_content(content_id: str, payload: ContentPatch,
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)) -> ContentOut:
    row = await _get_or_404(db, content_id)
    body_changed = payload.body_md is not None and payload.body_md != row.body_md
    if body_changed:
        next_version = (await db.scalar(
            select(func.coalesce(func.max(ContentVersion.version_no), 0) + 1)
            .where(ContentVersion.content_id == row.id)
        )) or 1
        db.add(ContentVersion(
            content_id=row.id, version_no=int(next_version),
            body_md=row.body_md, edit_summary=payload.edit_summary,
            edited_by=user.id,
        ))
    for field in ("topic", "category", "status", "body_md", "frontmatter"):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return ContentOut.model_validate(row)


@router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response)
async def delete_content(content_id: str,
                         db: AsyncSession = Depends(get_db),
                         _: User = Depends(get_current_user)) -> Response:
    row = await _get_or_404(db, content_id)
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{content_id}/versions", response_model=list[ContentVersionOut])
async def list_versions(content_id: str,
                        db: AsyncSession = Depends(get_db),
                        _: User = Depends(get_current_user)) -> list[ContentVersionOut]:
    rows = (await db.scalars(
        select(ContentVersion).where(ContentVersion.content_id == content_id)
        .order_by(desc(ContentVersion.version_no))
    )).all()
    return [ContentVersionOut.model_validate(r) for r in rows]


@router.post("/{content_id}/review", response_model=ReviewResponse)
async def review_content(content_id: str,
                         db: AsyncSession = Depends(get_db),
                         _: User = Depends(get_current_user)) -> ReviewResponse:
    row = await _get_or_404(db, content_id)
    result = await review_body(db, row.body_md, row.channel)
    return ReviewResponse(
        passed=result.passed,
        issues=[IssueOut(severity=str(i.severity), category=i.category,
                         message=i.message, line=i.line) for i in result.issues],
    )
