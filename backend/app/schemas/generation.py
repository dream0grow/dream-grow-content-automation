"""생성 잡 관련 Pydantic 스키마"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GenerateThreadRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    tone: str = "전문적이면서 친근한"
    category: str = "학습"


class DeriveNewsletterRequest(BaseModel):
    extra_thread_ids: list[int] = []


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    status: str
    content_id: int | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class JobAccepted(BaseModel):
    job_id: int
