from __future__ import annotations

from pydantic import BaseModel


class Message(BaseModel):
    message: str


class IdResponse(BaseModel):
    id: str
