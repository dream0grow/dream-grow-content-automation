from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from apps.api.core.config import get_settings
from apps.api.core.logging import configure_logging, get_logger
from apps.api.routers import (
    analytics, auth, brand, contents, generation, integrations, jobs,
    learning, magnets, publishing, schedules,
)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    configure_logging()
    get_logger("startup").info("dreamgrow api ready", api_prefix=get_settings().app_api_prefix)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url=f"{settings.app_api_prefix}/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    limiter = Limiter(key_func=get_remote_address, default_limits=["240/minute"])
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def _(_, exc: RateLimitExceeded):  # noqa: ANN001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    prefix = settings.app_api_prefix
    for router in (
        auth.router, brand.router, contents.router, generation.router,
        schedules.router, publishing.router, jobs.router, analytics.router,
        magnets.router, integrations.router, learning.router,
    ):
        app.include_router(router, prefix=prefix)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict:
        return {"ok": True}

    return app


app = create_app()
