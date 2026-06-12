"""AI 생성/파생 라우터 - 비동기 잡 패턴 (202 + 폴링)"""
import asyncio
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ContentStatus, ContentType, JobKind, JobStatus
from app.db.base import SessionLocal, get_db
from app.db.models import Content, GenerationJob
from app.schemas.generation import (
    DeriveNewsletterRequest,
    GenerateThreadRequest,
    JobAccepted,
    JobOut,
)
from app.services import generator, reviewer
from app.services.llm import LLMClient, get_llm

router = APIRouter(tags=["generation"])


def _run_generation_job(job_id: int, llm: LLMClient):
    """백그라운드에서 생성 잡 실행. 자체 DB 세션 사용."""
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return
        job.status = JobStatus.running.value
        db.commit()

        params = job.params or {}
        try:
            if job.kind == JobKind.thread.value:
                body = generator.generate_thread(
                    llm, params["topic"], params.get("tone", "전문적이면서 친근한"),
                    params.get("category", ""),
                )
                title = params["topic"]
                category = params.get("category", "학습")
                ctype = ContentType.thread.value
                parent_id = None
                tone = params.get("tone")
            elif job.kind == JobKind.reels.value:
                source = db.get(Content, params["source_content_id"])
                body = generator.derive_reels(llm, source.body, source.category)
                title = f"릴스: {source.title}"
                category = source.category
                ctype = ContentType.reels.value
                parent_id = source.id
                tone = None
            elif job.kind == JobKind.newsletter.value:
                source = db.get(Content, params["source_content_id"])
                reference_bodies = [source.body]
                for extra_id in params.get("extra_thread_ids", []):
                    extra = db.get(Content, extra_id)
                    if extra:
                        reference_bodies.append(extra.body)
                prev_topics = [
                    n.title for n in db.scalars(
                        select(Content)
                        .where(Content.type == ContentType.newsletter.value)
                        .order_by(Content.created_at.desc()).limit(3)
                    ).all()
                ]
                body = generator.derive_newsletter(
                    llm, source.title, source.category, reference_bodies, prev_topics,
                )
                title = f"뉴스레터: {source.title}"
                category = source.category
                ctype = ContentType.newsletter.value
                parent_id = source.id
                tone = None
            else:
                raise ValueError(f"알 수 없는 잡 종류: {job.kind}")

            content = Content(
                type=ctype, title=title, body=body, category=category,
                tone=tone, parent_content_id=parent_id,
                status=ContentStatus.review_wait.value,
                review_result=reviewer.review(body, ctype),
            )
            db.add(content)
            db.flush()
            job.content_id = content.id
            job.status = JobStatus.done.value
        except Exception as e:
            job.status = JobStatus.failed.value
            job.error = str(e)[:1000]
        job.finished_at = datetime.now()
        db.commit()
    finally:
        db.close()


async def _run_job_async(job_id: int, llm: LLMClient):
    await asyncio.to_thread(_run_generation_job, job_id, llm)


def _create_job(db: Session, kind: str, params: dict) -> GenerationJob:
    job = GenerationJob(kind=kind, status=JobStatus.pending.value, params=params)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/generate/thread", response_model=JobAccepted, status_code=202)
def generate_thread(
    payload: GenerateThreadRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    job = _create_job(db, JobKind.thread.value, payload.model_dump())
    background.add_task(_run_job_async, job.id, llm)
    return JobAccepted(job_id=job.id)


@router.post("/contents/{content_id}/derive/reels", response_model=JobAccepted, status_code=202)
def derive_reels(
    content_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    source = db.get(Content, content_id)
    if not source:
        raise HTTPException(404, "콘텐츠를 찾을 수 없습니다")
    if source.type != ContentType.thread.value:
        raise HTTPException(409, "스레드에서만 릴스를 파생할 수 있습니다")
    job = _create_job(db, JobKind.reels.value, {"source_content_id": content_id})
    background.add_task(_run_job_async, job.id, llm)
    return JobAccepted(job_id=job.id)


@router.post("/contents/{content_id}/derive/newsletter", response_model=JobAccepted, status_code=202)
def derive_newsletter(
    content_id: int,
    background: BackgroundTasks,
    payload: DeriveNewsletterRequest | None = None,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    source = db.get(Content, content_id)
    if not source:
        raise HTTPException(404, "콘텐츠를 찾을 수 없습니다")
    if source.type != ContentType.thread.value:
        raise HTTPException(409, "스레드에서만 뉴스레터를 파생할 수 있습니다")
    params = {"source_content_id": content_id}
    if payload:
        params["extra_thread_ids"] = payload.extra_thread_ids
    job = _create_job(db, JobKind.newsletter.value, params)
    background.add_task(_run_job_async, job.id, llm)
    return JobAccepted(job_id=job.id)


@router.get("/generate/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(GenerationJob, job_id)
    if not job:
        raise HTTPException(404, "잡을 찾을 수 없습니다")
    return job


@router.get("/generate/jobs", response_model=list[JobOut])
def list_jobs(active: bool = False, db: Session = Depends(get_db)):
    stmt = select(GenerationJob).order_by(GenerationJob.created_at.desc()).limit(50)
    if active:
        stmt = stmt.where(GenerationJob.status.in_([
            JobStatus.pending.value, JobStatus.running.value,
        ]))
    return db.scalars(stmt).all()
