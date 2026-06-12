"""Dream Grow 콘텐츠 자동화 API 서버"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.base import Base, engine
from app.jobs.publish_job import start_scheduler, stop_scheduler
from app.routers import calendar, contents, generation, publish, system

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    if settings.scheduler_enabled:
        start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Dream Grow Content Automation", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(contents.router, prefix="/api")
    app.include_router(generation.router, prefix="/api")
    app.include_router(calendar.router, prefix="/api")
    app.include_router(publish.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    return app


app = create_app()
