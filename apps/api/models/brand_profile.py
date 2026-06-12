from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, IDMixin, TimestampMixin


class BrandProfile(IDMixin, TimestampMixin, Base):
    __tablename__ = "brand_profile"

    brand_name: Mapped[str] = mapped_column(String(255), default="Dream_Grow")
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    banned_phrases: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}",
    )
    required_ending: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    categories: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
