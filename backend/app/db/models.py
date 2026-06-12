"""DB 모델 - contents / generation_jobs / publish_logs"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Content(Base):
    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20))  # thread | reels | newsletter
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="학습")
    status: Mapped[str] = mapped_column(String(20), default="리뷰대기")
    tone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    parent_content_id: Mapped[int | None] = mapped_column(
        ForeignKey("contents.id", ondelete="SET NULL"), nullable=True
    )
    review_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    children: Mapped[list["Content"]] = relationship(
        "Content", remote_side=[parent_content_id], uselist=True, viewonly=True,
        primaryjoin="Content.id == foreign(Content.parent_content_id)",
    )

    __table_args__ = (
        Index("ix_contents_status", "status"),
        Index("ix_contents_scheduled_at", "scheduled_at"),
        Index("ix_contents_type", "type"),
    )


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20))  # thread | reels | newsletter | publish
    status: Mapped[str] = mapped_column(String(20), default="pending")
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_id: Mapped[int | None] = mapped_column(
        ForeignKey("contents.id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublishLog(Base):
    __tablename__ = "publish_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"))
    success: Mapped[bool] = mapped_column(default=False)
    dry_run: Mapped[bool] = mapped_column(default=False)
    posts_count: Mapped[int] = mapped_column(Integer, default=0)
    external_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
