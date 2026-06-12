"""앱 전역 설정 - 환경변수 기반 (pydantic-settings)"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Claude (Anthropic)
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    mock_llm: bool = False

    # Meta Threads API
    threads_access_token: str = ""
    threads_user_id: str = ""
    threads_api_base: str = "https://graph.threads.net/v1.0"
    publish_dry_run: bool = True

    # DB / 서버
    database_url: str = "sqlite:///./data/dreamgrow.db"
    scheduler_enabled: bool = True
    cors_origins: str = "http://localhost:5173"

    @property
    def threads_configured(self) -> bool:
        return bool(self.threads_access_token and self.threads_user_id)

    @property
    def llm_configured(self) -> bool:
        return bool(self.anthropic_api_key) or self.mock_llm

    @property
    def effective_dry_run(self) -> bool:
        """토큰 미설정 시 강제 dry-run."""
        return self.publish_dry_run or not self.threads_configured


@lru_cache
def get_settings() -> Settings:
    return Settings()
