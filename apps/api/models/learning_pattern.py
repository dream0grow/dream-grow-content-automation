from __future__ import annotations

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, IDMixin, TimestampMixin


class LearningPattern(IDMixin, TimestampMixin, Base):
    __tablename__ = "learning_patterns"
    __table_args__ = (
        Index("ix_learning_channel_at", "channel", "created_at"),
    )

    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    pattern_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    examples: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
