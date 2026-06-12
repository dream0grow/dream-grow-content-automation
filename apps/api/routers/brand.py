from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db
from apps.api.models import BrandProfile, User
from apps.api.schemas.brand import BrandProfileIn, BrandProfileOut

router = APIRouter(prefix="/brand", tags=["brand"])


async def _ensure_brand(db: AsyncSession) -> BrandProfile:
    row = await db.scalar(select(BrandProfile))
    if row:
        return row
    row = BrandProfile()
    db.add(row)
    await db.flush()
    return row


@router.get("", response_model=BrandProfileOut)
async def get_brand(db: AsyncSession = Depends(get_db),
                    _: User = Depends(get_current_user)) -> BrandProfileOut:
    row = await _ensure_brand(db)
    return BrandProfileOut(
        id=row.id, brand_name=row.brand_name,
        target_audience=row.target_audience, tone_notes=row.tone_notes,
        banned_phrases=list(row.banned_phrases or []),
        required_ending=row.required_ending,
        brand_signature=row.brand_signature,
        categories=list(row.categories or []),
    )


@router.put("", response_model=BrandProfileOut)
async def put_brand(payload: BrandProfileIn,
                    db: AsyncSession = Depends(get_db),
                    _: User = Depends(get_current_user)) -> BrandProfileOut:
    row = await _ensure_brand(db)
    row.brand_name = payload.brand_name
    row.target_audience = payload.target_audience
    row.tone_notes = payload.tone_notes
    row.banned_phrases = payload.banned_phrases
    row.required_ending = payload.required_ending
    row.brand_signature = payload.brand_signature
    row.categories = payload.categories
    await db.commit()
    return BrandProfileOut(id=row.id, **payload.model_dump())
