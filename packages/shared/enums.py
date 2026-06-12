from __future__ import annotations

from enum import StrEnum


class Channel(StrEnum):
    THREAD = "thread"
    REELS = "reels"
    YOUTUBE = "youtube"
    NEWSLETTER = "newsletter"
    MAGNET = "magnet"


class ContentStatus(StrEnum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class ScheduleStatus(StrEnum):
    PENDING = "pending"
    FIRING = "firing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    GENERATE = "generate"
    PUBLISH_THREADS = "publish_threads"
    PUBLISH_NEWSLETTER = "publish_newsletter"
    RENDER_MAGNET = "render_magnet"
    POLL_ANALYTICS = "poll_analytics"
    DIFF_LEARNING = "diff_learning"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class IssueSeverity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class IntegrationProvider(StrEnum):
    THREADS = "threads"
    MAILY = "maily"
    HONCHO = "honcho"
    ANTHROPIC = "anthropic"


# Korean status mapping used by the Obsidian importer.
KOREAN_STATUS_MAP: dict[str, ContentStatus] = {
    "리뷰대기": ContentStatus.REVIEWING,
    "리뷰완료": ContentStatus.REVIEWING,
    "발행대기": ContentStatus.SCHEDULED,
    "발행완료": ContentStatus.PUBLISHED,
    "초안": ContentStatus.DRAFT,
}

DEFAULT_CATEGORIES = [
    "훈육", "수학", "독서", "미디어", "놀이",
    "감정", "학습", "학교", "크리에이터",
]
