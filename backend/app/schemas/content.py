"""콘텐츠 관련 Pydantic 스키마"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ContentStatus, ContentType


class ContentCreate(BaseModel):
    type: ContentType
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    category: str = "학습"
    tone: str | None = None


class ContentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = None
    category: str | None = None
    tone: str | None = None


class StatusUpdate(BaseModel):
    status: ContentStatus
    force: bool = False


class ScheduleAssign(BaseModel):
    scheduled_at: datetime | None = None  # None이면 예약 해제


class PostPreview(BaseModel):
    text: str
    length: int
    over_limit: bool   # 500자 초과
    over_style: bool   # 280자 초과


class ContentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    category: str
    status: str
    scheduled_at: datetime | None
    published_at: datetime | None
    parent_content_id: int | None
    review_result: dict | None
    created_at: datetime
    updated_at: datetime


class ContentOut(ContentSummary):
    body: str
    tone: str | None
    external_id: str | None
    external_ids: list | None


class ContentDetail(ContentOut):
    posts: list[PostPreview] = []
    children: list[ContentSummary] = []


class ContentListOut(BaseModel):
    items: list[ContentSummary]
    total: int


class ReviewIssue(BaseModel):
    severity: str
    category: str
    message: str
    post_index: int | None = None


class ReviewResultOut(BaseModel):
    passed: bool
    issues: list[ReviewIssue]
    auto_fixable: bool


class ReviewFixOut(BaseModel):
    body: str
    fixes: list[str]
    review: ReviewResultOut
