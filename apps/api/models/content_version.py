from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, IDMixin, TimestampMixin


class ContentVersion(IDMixin, TimestampMixin, Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("content_id", "version_no", name="uq_content_versions"),
    )

    content_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("contents.id", ondelete="CASCADE"), nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    edit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_by: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
