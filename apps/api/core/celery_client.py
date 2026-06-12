"""Thin Celery client used from the API to dispatch worker tasks by name.

Avoids importing the worker package (which has its own dependencies) so the
API container stays slim.
"""
from __future__ import annotations

from celery import Celery

from .config import get_settings

_settings = get_settings()
celery_client = Celery(
    "api",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
)
celery_client.conf.update(task_default_queue="default")


def send(task_name: str, *args, **kwargs) -> str:
    result = celery_client.send_task(task_name, args=args, kwargs=kwargs)
    return result.id
