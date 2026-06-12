from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                      extra="ignore", case_sensitive=False)

    # App
    app_name: str = "Dream Grow Content Studio"
    app_api_prefix: str = "/api/v1"
    app_timezone: str = "Asia/Seoul"
    app_public_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://dreamgrow:dreamgrow@localhost:5432/dreamgrow"
    database_sync_url: str = "postgresql+psycopg://dreamgrow:dreamgrow@localhost:5432/dreamgrow"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Security
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 14
    key_vault_key: str = ""  # base64 Fernet key

    # Admin bootstrap
    admin_email: str = "admin@dreamgrow.local"
    admin_password: str = "changeme"
    admin_name: str = "Dream Grow Admin"

    # LLM
    anthropic_api_key: str = ""
    claude_bin: str = ""

    # Threads / Maily / Honcho
    threads_access_token: str = ""
    threads_user_id: str = ""
    maily_access_token: str = ""
    honcho_api_key: str = ""
    honcho_app_id: str = "dream-grow"

    # PDF
    pdf_output_dir: str = "/data/pdfs"
    font_path: str = ""

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
