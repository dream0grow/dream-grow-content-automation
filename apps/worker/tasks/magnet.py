from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from apps.api.core.config import get_settings
from apps.api.models import Content, Job, LeadMagnet
from apps.worker.celery_app import celery_app
from apps.worker.tasks._helpers import now_utc, publish_job_event, session_scope
from packages.integrations.pdf import render_lead_magnet_pdf


@celery_app.task(name="tasks.render_magnet_pdf", bind=True, max_retries=1)
def render_magnet_pdf(self, job_id: str) -> dict:
    settings = get_settings()
    with session_scope() as db:
        job = db.get(Job, job_id)
        if not job:
            return {"ok": False}
        job.status = "running"; job.started_at = now_utc()
        publish_job_event(job_id, "running")

        magnet_id = job.payload.get("magnet_id")
        content_id = job.payload["content_id"]
        magnet = db.get(LeadMagnet, magnet_id) if magnet_id else \
            db.scalar(select(LeadMagnet).where(LeadMagnet.content_id == content_id))
        content = db.get(Content, content_id)
        if not magnet or not content:
            job.status = "failed"; job.error = "magnet or content missing"
            publish_job_event(job_id, "failed"); return {"ok": False}

        try:
            pdf_bytes = render_lead_magnet_pdf(
                content.body_md, title=content.topic,
                font_path=settings.font_path or None,
            )
        except Exception as exc:
            job.status = "failed"; job.error = str(exc)
            publish_job_event(job_id, "failed", {"error": str(exc)})
            raise

        out_dir = Path(settings.pdf_output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{magnet.public_token}.pdf"
        out_path.write_bytes(pdf_bytes)
        magnet.pdf_path = str(out_path)
        magnet.pdf_size_bytes = len(pdf_bytes)
        job.status = "done"; job.finished_at = now_utc()
        job.result = {"pdf_path": str(out_path), "size": len(pdf_bytes),
                      "public_token": magnet.public_token}
        publish_job_event(job_id, "done", job.result)
        return {"ok": True}
