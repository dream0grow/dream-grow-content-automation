"""시스템 상태 라우터"""
from fastapi import APIRouter

from app.core.config import get_settings
from app.jobs.publish_job import scheduler_status

router = APIRouter(tags=["system"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/system/status")
def system_status():
    settings = get_settings()
    sched = scheduler_status()
    return {
        "scheduler_running": sched["running"],
        "next_run_at": sched["next_run_at"],
        "threads_configured": settings.threads_configured,
        "llm_configured": settings.llm_configured,
        "mock_llm": settings.mock_llm,
        "dry_run": settings.effective_dry_run,
        "db": "postgres" if settings.database_url.startswith("postgresql") else "sqlite",
    }
