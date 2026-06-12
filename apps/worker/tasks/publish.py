from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select

from apps.api.core.config import get_settings
from apps.api.core.security import decrypt_payload
from apps.api.models import (
    Content, IntegrationCredential, Job, PublishResult, Schedule,
)
from apps.worker.celery_app import celery_app
from apps.worker.tasks._helpers import now_utc, publish_job_event, session_scope
from packages.integrations.maily import MailyClient
from packages.integrations.threads import (
    ThreadsPublisher, split_thread_posts,
)
from packages.shared.enums import IntegrationProvider, JobType


def _load_credentials(db, provider: str) -> dict | None:
    row = db.scalar(select(IntegrationCredential).where(
        IntegrationCredential.provider == provider))
    if not row:
        return None
    try:
        return json.loads(decrypt_payload(row.encrypted_payload).decode())
    except ValueError:
        return None


@celery_app.task(name="tasks.publish_threads", bind=True, max_retries=2)
def publish_threads(self, job_id: str) -> dict:
    settings = get_settings()
    with session_scope() as db:
        job = db.get(Job, job_id)
        if not job:
            return {"ok": False}
        job.status = "running"; job.started_at = now_utc()
        publish_job_event(job_id, "running")

        content_id = job.payload["content_id"]
        content = db.get(Content, content_id)
        if not content:
            job.status = "failed"; job.error = "content missing"
            publish_job_event(job_id, "failed"); return {"ok": False}

        creds = _load_credentials(db, IntegrationProvider.THREADS.value) or {}
        access_token = creds.get("access_token") or settings.threads_access_token
        user_id = creds.get("user_id") or settings.threads_user_id
        if not access_token or not user_id:
            job.status = "failed"; job.error = "threads credentials missing"
            content.status = "failed"
            publish_job_event(job_id, "failed", {"error": job.error}); return {"ok": False}

        publisher = ThreadsPublisher(access_token=access_token, user_id=user_id)
        posts = split_thread_posts(content.body_md)
        outcome = publisher.publish_thread(posts)

        if not outcome.success:
            job.status = "failed"; job.error = outcome.error
            content.status = "failed"
            publish_job_event(job_id, "failed", {"error": outcome.error})
            return {"ok": False, "error": outcome.error}

        db.add(PublishResult(
            content_id=content.id,
            channel="thread",
            external_id=outcome.first_id,
            external_url=outcome.first_url,
            published_at=now_utc(),
            metrics={"posts": outcome.posts},
        ))
        content.status = "published"
        job.status = "done"; job.finished_at = now_utc()
        job.result = {"external_id": outcome.first_id, "url": outcome.first_url}
        publish_job_event(job_id, "done", job.result)
        return {"ok": True}


@celery_app.task(name="tasks.publish_newsletter", bind=True, max_retries=2)
def publish_newsletter(self, job_id: str) -> dict:
    settings = get_settings()
    with session_scope() as db:
        job = db.get(Job, job_id)
        if not job:
            return {"ok": False}
        job.status = "running"; job.started_at = now_utc()
        publish_job_event(job_id, "running")

        content = db.get(Content, job.payload["content_id"])
        if not content:
            job.status = "failed"; job.error = "content missing"
            publish_job_event(job_id, "failed"); return {"ok": False}

        creds = _load_credentials(db, IntegrationProvider.MAILY.value) or {}
        token = creds.get("access_token") or settings.maily_access_token
        if not token:
            job.status = "failed"; job.error = "maily credentials missing"
            content.status = "failed"
            publish_job_event(job_id, "failed", {"error": job.error}); return {"ok": False}

        client = MailyClient(access_token=token)
        draft = client.create_draft(title=content.topic, body_md=content.body_md)
        if not draft.success:
            job.status = "failed"; job.error = draft.error
            content.status = "failed"
            publish_job_event(job_id, "failed", {"error": draft.error}); return {"ok": False}
        pub = client.publish(draft.note_id)
        if not pub.success:
            job.status = "failed"; job.error = pub.error
            publish_job_event(job_id, "failed", {"error": pub.error}); return {"ok": False}

        db.add(PublishResult(
            content_id=content.id, channel="newsletter",
            external_id=pub.note_id, external_url=pub.note_url,
            published_at=now_utc(), metrics={},
        ))
        content.status = "published"
        job.status = "done"; job.finished_at = now_utc()
        job.result = {"external_id": pub.note_id, "url": pub.note_url}
        publish_job_event(job_id, "done", job.result)
        return {"ok": True}


@celery_app.task(name="tasks.scheduled_publisher_sweep")
def scheduled_publisher_sweep() -> dict:
    """Pick due pending schedules and enqueue per-channel publish tasks."""
    fired = 0
    with session_scope() as db:
        due = db.scalars(
            select(Schedule)
            .where(Schedule.status == "pending")
            .where(Schedule.scheduled_at <= datetime.now())
            .limit(20)
        ).all()
        for sched in due:
            content = db.get(Content, sched.content_id)
            if not content:
                sched.status = "failed"; sched.last_error = "content missing"; continue
            if content.channel == "thread":
                task_name = "tasks.publish_threads"
                job_type = JobType.PUBLISH_THREADS.value
            elif content.channel == "newsletter":
                task_name = "tasks.publish_newsletter"
                job_type = JobType.PUBLISH_NEWSLETTER.value
            else:
                sched.status = "failed"
                sched.last_error = f"unsupported channel: {content.channel}"; continue
            job = Job(type=job_type, status="queued",
                      payload={"content_id": content.id, "schedule_id": sched.id})
            db.add(job)
            db.flush()
            sched.status = "firing"
            sched.attempt_count = (sched.attempt_count or 0) + 1
            celery_app.send_task(task_name, args=[job.id])
            fired += 1
    return {"fired": fired}
