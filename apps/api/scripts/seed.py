"""Seed the admin user and a default brand profile.

Usage:
    python -m apps.api.scripts.seed
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from apps.api.core.config import get_settings
from apps.api.core.db import SessionLocal
from apps.api.core.security import hash_password
from apps.api.models import BrandProfile, User


async def main() -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == settings.admin_email))
        if not user:
            db.add(User(
                email=settings.admin_email,
                name=settings.admin_name,
                hashed_password=hash_password(settings.admin_password),
            ))
            print(f"seeded admin user: {settings.admin_email}")
        else:
            print(f"admin user exists: {settings.admin_email}")

        brand = await db.scalar(select(BrandProfile))
        if not brand:
            db.add(BrandProfile(
                brand_name="Dream_Grow",
                target_audience="초등 자녀를 둔 부모",
                tone_notes="존댓말 기반 구어체. 학자명 나열 금지. 이모지 금지.",
                banned_phrases=["과학적으로 건강하게 성장하는 법을 돕습니다",
                                "돕습니다.", "도움이 되길 바랍니다"],
                required_ending="아이와 부모의 꿈을 키웁니다.",
                brand_signature="-Dream_Grow-",
                categories=["훈육", "수학", "독서", "미디어", "놀이",
                            "감정", "학습", "학교", "크리에이터"],
            ))
            print("seeded default brand profile")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
