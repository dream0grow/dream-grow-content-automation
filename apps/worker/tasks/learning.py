"""Diff learning task — compares ai_original_md vs current body_md.

For each content with a meaningful diff, asks the LLM to summarize the editing
pattern and stores it as a LearningPattern. Optionally forwards summary to
Honcho if integration credentials present.
"""
from __future__ import annotations

import difflib

from sqlalchemy import select

from apps.api.core.config import get_settings
from apps.api.models import Content, Job, LearningPattern
from apps.api.services.llm import llm_call
from apps.worker.celery_app import celery_app
from apps.worker.tasks._helpers import now_utc, publish_job_event, session_scope
from packages.integrations.honcho import HonchoMemory

SUMMARY_PROMPT = """다음은 같은 콘텐츠의 AI 초안과 사용자 편집본입니다.
사용자가 어떤 패턴으로 수정했는지 한국어 한 문단으로 요약하세요.
구체적 사례 1~2개를 인용해도 좋습니다.

[AI 초안]
{original}

[사용자 편집본]
{edited}
"""


def _has_diff(original: str | None, current: str) -> bool:
    if not original:
        return False
    return original.strip() != current.strip()


@celery_app.task(name="tasks.run_diff_learning")
def run_diff_learning(job_id: str | None = None) -> dict:
    settings = get_settings()
    summarized = 0
    with session_scope() as db:
        job = db.get(Job, job_id) if job_id else None
        if job:
            job.status = "running"; job.started_at = now_utc()
            publish_job_event(job_id, "running")
        contents = db.scalars(
            select(Content).where(Content.status.in_(["reviewing", "scheduled", "published"]))
        ).all()
        memory = HonchoMemory(settings.honcho_api_key or None, settings.honcho_app_id)
        for content in contents:
            if not _has_diff(content.ai_original_md, content.body_md):
                continue
            diff = "\n".join(difflib.unified_diff(
                (content.ai_original_md or "").splitlines(),
                content.body_md.splitlines(),
                lineterm="", n=2,
            ))
            if len(diff) < 60:
                continue
            try:
                result = llm_call(
                    SUMMARY_PROMPT.format(
                        original=(content.ai_original_md or "")[:4000],
                        edited=content.body_md[:4000],
                    ),
                    model="sonnet", max_tokens=600,
                )
            except Exception:
                continue
            summary = result.body_md.strip()
            if not summary:
                continue
            db.add(LearningPattern(
                channel=content.channel,
                pattern_type="user_edits",
                summary=summary,
                examples=[{"content_id": content.id, "topic": content.topic}],
                source="local",
            ))
            memory.save_correction(content.channel, summary)
            summarized += 1
        if job:
            job.status = "done"; job.finished_at = now_utc()
            job.result = {"summarized": summarized}
            publish_job_event(job_id, "done", job.result)
    return {"summarized": summarized}
