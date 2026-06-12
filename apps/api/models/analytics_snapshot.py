from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, IDMixin, TimestampMixin


class AnalyticsSnapshot(IDMixin, TimestampMixin, Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        Index("ix_analytics_content_at", "content_id", "captured_at"),
    )

    content_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("contents.id", ondelete="CASCADE"), nullable=False,
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
