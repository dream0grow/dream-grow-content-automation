from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from apps.api.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "dreamgrow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "apps.worker.tasks.generate",
        "apps.worker.tasks.publish",
        "apps.worker.tasks.magnet",
        "apps.worker.tasks.analytics",
        "apps.worker.tasks.learning",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "sweep-schedules": {
            "task": "tasks.scheduled_publisher_sweep",
            "schedule": 60.0,
        },
        "poll-analytics": {
            "task": "tasks.poll_threads_analytics",
            "schedule": 1800.0,
        },
        "nightly-learning": {
            "task": "tasks.run_diff_learning",
            "schedule": crontab(hour=18, minute=0),  # 03:00 KST = 18:00 UTC
        },
    },
)
