"""Pydantic model that mirrors the legacy Obsidian frontmatter keys.

Preserved verbatim so Obsidian import/export remains lossless.
"""
from __future__ import annotations

import re
from datetime import date, time
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

_FM_RE = re.compile(r"^---\s*\n(?P<fm>.*?)\n---\s*\n?", re.DOTALL)


class Frontmatter(BaseModel):
    """Obsidian-compatible YAML frontmatter."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    topic: str | None = Field(default=None, alias="주제")
    category: str | None = Field(default=None, alias="카테고리")
    channel: str | None = Field(default=None, alias="채널")
    status: str | None = Field(default=None, alias="상태")
    created_on: date | None = Field(default=None, alias="생성일")
    published_on: date | None = Field(default=None, alias="발행일")
    publish_time: time | str | None = Field(default=None, alias="발행시간")
    source: str | None = Field(default=None, alias="출처")
    review_status: str | None = Field(default=None, alias="검수상태")

    def to_yaml(self) -> str:
        data = self.model_dump(by_alias=True, exclude_none=True, mode="json")
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()

    def to_block(self) -> str:
        return f"---\n{self.to_yaml()}\n---\n"


def split_frontmatter(text: str) -> tuple[Frontmatter, str]:
    """Split a markdown document into (frontmatter, body).

    Returns an empty Frontmatter if no YAML block is found.
    """
    match = _FM_RE.match(text)
    if not match:
        return Frontmatter(), text
    raw = match.group("fm")
    body = text[match.end():]
    try:
        data: dict[str, Any] = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return Frontmatter(**data), body


def merge_frontmatter(text: str, **updates: Any) -> str:
    """Update frontmatter fields in-place and return the new document."""
    fm, body = split_frontmatter(text)
    payload = fm.model_dump(by_alias=True, exclude_none=True)
    payload.update(updates)
    new_fm = Frontmatter(**payload)
    return new_fm.to_block() + body
