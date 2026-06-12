from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, IDMixin, TimestampMixin


class Schedule(IDMixin, TimestampMixin, Base):
    __tablename__ = "schedules"
    __table_args__ = (
        Index("ix_schedules_status_at", "status", "scheduled_at"),
        Index("ix_schedules_at", "scheduled_at"),
    )

    content_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("contents.id", ondelete="CASCADE"), nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Seoul")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
