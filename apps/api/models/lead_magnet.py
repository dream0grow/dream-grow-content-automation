from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, IDMixin, TimestampMixin


class LeadMagnet(IDMixin, TimestampMixin, Base):
    __tablename__ = "lead_magnets"

    content_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("contents.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    public_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
