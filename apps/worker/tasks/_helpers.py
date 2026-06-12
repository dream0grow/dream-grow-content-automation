"""Sync DB session + Redis pub/sub for worker tasks.

Workers run in sync Celery contexts; we use the sync SQLAlchemy engine instead
of pulling asyncio in.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.core.config import get_settings

_settings = get_settings()
_engine = create_engine(_settings.database_sync_url, pool_pre_ping=True, future=True)
SyncSessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)
_redis = redis.from_url(_settings.redis_url, decode_responses=True)


@contextmanager
def session_scope():
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def publish_job_event(job_id: str, status: str, payload: dict[str, Any] | None = None) -> None:
    msg = {"job_id": job_id, "status": status, "ts": datetime.now(timezone.utc).isoformat()}
    if payload:
        msg.update(payload)
    _redis.publish(f"job:{job_id}", json.dumps(msg))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
