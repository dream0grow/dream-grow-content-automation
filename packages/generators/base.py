from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class BrandProfile:
    name: str = "Dream_Grow"
    audience: str = "초등 자녀를 둔 부모"
    tone: str = "전문적이면서 친근한"
    required_ending: str = "아이와 부모의 꿈을 키웁니다."
    brand_signature: str = "-Dream_Grow-"
    banned_phrases: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)


@dataclass
class GeneratorContext:
    topic: str
    channel: str
    category: str | None = None
    tone: str | None = None
    brand: BrandProfile = field(default_factory=BrandProfile)
    # Memory pulled from Honcho or learning_patterns
    style_context: str = ""
    brand_context: str = ""
    correction_context: str = ""
    # Optional inputs
    magnet_type: str | None = None
    reference_bodies: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class GeneratedContent:
    body_md: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    meta: dict = field(default_factory=dict)


class LLMCallable(Protocol):
    def __call__(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str = "sonnet",
        max_tokens: int = 4096,
    ) -> GeneratedContent: ...
