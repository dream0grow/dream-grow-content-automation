"""예약 발행 스케줄러 - APScheduler 인프로세스 (60초 간격)

레거시 scheduled_publisher.py의 시간별 크론을 대체한다.
발행 슬롯이 :10/:50이므로 60초 granularity가 필요.
"""
import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.constants import ContentStatus
from app.db.base import SessionLocal
from app.db.models import Content
from app.services import publisher

logger = logging.getLogger("dreamgrow.scheduler")

scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


def _publish_due_contents():
    """발행시간이 도래한 발행대기 콘텐츠를 발행한다."""
    db = SessionLocal()
    try:
        now = datetime.now()
        due = db.scalars(
            select(Content).where(
                Content.status == ContentStatus.publish_wait.value,
                Content.scheduled_at.isnot(None),
                Content.scheduled_at <= now,
            ).order_by(Content.scheduled_at)
        ).all()

        for content in due:
            try:
                log = publisher.publish_content(db, content)
                if log.success:
                    logger.info("예약 발행 완료: #%s %s (dry_run=%s)",
                                content.id, content.title, log.dry_run)
                else:
                    logger.error("예약 발행 실패: #%s %s - %s",
                                 content.id, content.title, log.error)
            except Exception:
                logger.exception("예약 발행 중 오류: #%s", content.id)
                db.rollback()
    finally:
        db.close()


async def check_and_publish_due():
    await asyncio.to_thread(_publish_due_contents)


def start_scheduler():
    scheduler.add_job(
        check_and_publish_due,
        IntervalTrigger(seconds=60),
        id="publish_due",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.start()
    logger.info("발행 스케줄러 시작 (60초 간격)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)


def scheduler_status() -> dict:
    job = scheduler.get_job("publish_due") if scheduler.running else None
    return {
        "running": scheduler.running,
        "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }
