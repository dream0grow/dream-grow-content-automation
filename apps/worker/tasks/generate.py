from __future__ import annotations

from sqlalchemy import select

from apps.api.models import BrandProfile, Content, Job
from apps.api.services.llm import llm_call
from apps.worker.celery_app import celery_app
from apps.worker.tasks._helpers import now_utc, publish_job_event, session_scope
from packages.generators import REGISTRY, GeneratorContext
from packages.generators.base import BrandProfile as GenBrandProfile
from packages.integrations.honcho import HonchoMemory


def _build_brand(db_brand: BrandProfile | None) -> GenBrandProfile:
    if not db_brand:
        return GenBrandProfile()
    return GenBrandProfile(
        name=db_brand.brand_name or "Dream_Grow",
        audience=db_brand.target_audience or "초등 자녀를 둔 부모",
        tone=db_brand.tone_notes or "전문적이면서 친근한",
        required_ending=db_brand.required_ending or "아이와 부모의 꿈을 키웁니다.",
        brand_signature=db_brand.brand_signature or "-Dream_Grow-",
        banned_phrases=list(db_brand.banned_phrases or []),
        categories=list(db_brand.categories or []),
    )


@celery_app.task(name="tasks.generate_content", bind=True, max_retries=2)
def generate_content(self, job_id: str) -> dict:
    from apps.api.core.config import get_settings
    settings = get_settings()
    with session_scope() as db:
        job = db.get(Job, job_id)
        if not job:
            return {"ok": False, "error": "job missing"}
        job.status = "running"
        job.started_at = now_utc()
        db.flush()
        publish_job_event(job_id, "running")

        payload = job.payload or {}
        content_id = payload["content_id"]
        channel = payload["channel"]
        content = db.get(Content, content_id)
        if not content:
            job.status = "failed"; job.error = "content not found"
            publish_job_event(job_id, "failed", {"error": "content not found"})
            return {"ok": False}

        generator = REGISTRY.get(channel)
        if generator is None:
            job.status = "failed"; job.error = f"no generator for {channel}"
            publish_job_event(job_id, "failed", {"error": job.error})
            return {"ok": False}

        brand_row = db.scalar(select(BrandProfile))
        brand = _build_brand(brand_row)

        memory = HonchoMemory(settings.honcho_api_key or None, settings.honcho_app_id)
        mem = memory.fetch_context(channel)

        ctx = GeneratorContext(
            topic=payload["topic"],
            channel=channel,
            category=payload.get("category"),
            tone=payload.get("tone"),
            brand=brand,
            style_context=mem.style,
            brand_context=mem.brand,
            correction_context=mem.corrections,
            magnet_type=payload.get("magnet_type"),
        )
        try:
            result = generator(ctx, llm_call)
        except Exception as exc:
            job.status = "failed"; job.error = str(exc)
            content.status = "failed"
            publish_job_event(job_id, "failed", {"error": str(exc)})
            raise

        content.body_md = result.body_md
        content.ai_original_md = result.body_md
        content.generated_by_model = result.model
        content.status = "reviewing"
        job.status = "done"
        job.finished_at = now_utc()
        job.result = {"content_id": content.id, "model": result.model,
                      "tokens_in": result.tokens_in, "tokens_out": result.tokens_out}
        publish_job_event(job_id, "done", {"content_id": content.id})
        return {"ok": True, "content_id": content.id}
