from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContentIn(BaseModel):
    channel: str
    topic: str
    category: str | None = None
    body_md: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)


class ContentPatch(BaseModel):
    topic: str | None = None
    category: str | None = None
    status: str | None = None
    body_md: str | None = None
    frontmatter: dict[str, Any] | None = None
    edit_summary: str | None = None


class ContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: str
    category: str | None
    topic: str
    status: str
    body_md: str
    ai_original_md: str | None
    frontmatter: dict[str, Any]
    generated_by_model: str | None
    created_at: datetime
    updated_at: datetime


class ContentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: str
    category: str | None
    topic: str
    status: str
    created_at: datetime
    updated_at: datetime


class ContentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_no: int
    body_md: str
    edit_summary: str | None
    created_at: datetime


class GenerateRequest(BaseModel):
    channel: str
    topic: str
    category: str | None = None
    tone: str | None = None
    magnet_type: str | None = None
    reference_ids: list[str] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    content_id: str
    job_id: str


class IssueOut(BaseModel):
    severity: str
    category: str
    message: str
    line: int = 0


class ReviewResponse(BaseModel):
    passed: bool
    issues: list[IssueOut]
