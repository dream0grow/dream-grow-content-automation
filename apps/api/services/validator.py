"""Validator service — runs brand rules from packages/shared/rules.py."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import BrandProfile
from packages.shared.rules import BrandRules, ValidationResult, validate


async def load_brand_rules(db: AsyncSession) -> BrandRules:
    profile = await db.scalar(select(BrandProfile))
    if not profile:
        return BrandRules()
    return BrandRules(
        banned_phrases=tuple(profile.banned_phrases or ()),
        required_ending=profile.required_ending or BrandRules().required_ending,
        brand_signature=profile.brand_signature or BrandRules().brand_signature,
    )


async def review_body(db: AsyncSession, body: str, channel: str | None) -> ValidationResult:
    rules = await load_brand_rules(db)
    return validate(body, channel=channel, rules=rules)
