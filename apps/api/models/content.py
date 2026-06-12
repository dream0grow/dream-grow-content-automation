from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, IDMixin, TimestampMixin


class Content(IDMixin, TimestampMixin, Base):
    __tablename__ = "contents"
    __table_args__ = (
        Index("ix_contents_status_channel", "status", "channel"),
        Index("ix_contents_category", "category"),
        Index("ix_contents_created_at", "created_at"),
    )

    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_original_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    frontmatter: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    generated_by_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
