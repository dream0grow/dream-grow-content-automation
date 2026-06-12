from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, IDMixin, TimestampMixin


class PublishResult(IDMixin, TimestampMixin, Base):
    __tablename__ = "publish_results"
    __table_args__ = (
        Index("ix_publish_results_channel_at", "channel", "published_at"),
    )

    content_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("contents.id", ondelete="CASCADE"), nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
