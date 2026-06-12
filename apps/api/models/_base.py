from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.core.db import Base
from packages.shared.ulid import new_ulid


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


class IDMixin:
    id: Mapped[str] = mapped_column(
        String(26), primary_key=True, default=new_ulid,
    )


__all__ = ["Base", "IDMixin", "TimestampMixin"]
