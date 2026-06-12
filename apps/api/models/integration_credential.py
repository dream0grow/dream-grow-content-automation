from __future__ import annotations

from sqlalchemy import LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, IDMixin, TimestampMixin


class IntegrationCredential(IDMixin, TimestampMixin, Base):
    __tablename__ = "integration_credentials"

    provider: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
