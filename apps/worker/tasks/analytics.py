from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select

from apps.api.core.config import get_settings
from apps.api.core.security import decrypt_payload
from apps.api.models import AnalyticsSnapshot, IntegrationCredential, PublishResult
from apps.worker.celery_app import celery_app
from apps.worker.tasks._helpers import now_utc, session_scope
from packages.integrations.threads import ThreadsInsightsClient
from packages.shared.enums import IntegrationProvider


@celery_app.task(name="tasks.poll_threads_analytics")
def poll_threads_analytics() -> dict:
    settings = get_settings()
    fetched = 0
    with session_scope() as db:
        row = db.scalar(select(IntegrationCredential).where(
            IntegrationCredential.provider == IntegrationProvider.THREADS.value))
        if row:
            creds = json.loads(decrypt_payload(row.encrypted_payload).decode())
            token = creds.get("access_token")
        else:
            token = settings.threads_access_token
        if not token:
            return {"fetched": 0, "reason": "no threads token"}

        client = ThreadsInsightsClient(access_token=token)
        cutoff = now_utc() - timedelta(days=30)
        results = db.scalars(
            select(PublishResult)
            .where(PublishResult.channel == "thread")
            .where(PublishResult.published_at >= cutoff)
        ).all()
        for r in results:
            if not r.external_id:
                continue
            metrics = client.fetch_metrics(r.external_id)
            if not metrics:
                continue
            db.add(AnalyticsSnapshot(
                content_id=r.content_id, captured_at=now_utc(),
                views=metrics.views, likes=metrics.likes,
                comments=metrics.comments, shares=metrics.shares,
                reach=metrics.reach, raw=metrics.raw or {},
            ))
            fetched += 1
    return {"fetched": fetched}
