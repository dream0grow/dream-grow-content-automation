from __future__ import annotations

from pydantic import BaseModel, Field


class BrandProfileIn(BaseModel):
    brand_name: str = "Dream_Grow"
    target_audience: str | None = None
    tone_notes: str | None = None
    banned_phrases: list[str] = Field(default_factory=list)
    required_ending: str | None = None
    brand_signature: str | None = None
    categories: list[str] = Field(default_factory=list)


class BrandProfileOut(BrandProfileIn):
    id: str
