"""캘린더 관련 Pydantic 스키마"""
from datetime import date, datetime

from pydantic import BaseModel


class CalendarItem(BaseModel):
    content_id: int
    time: str  # "HH:MM"
    title: str
    category: str
    type: str
    status: str


class CalendarDay(BaseModel):
    date: date
    items: list[CalendarItem]


class CalendarOut(BaseModel):
    days: list[CalendarDay]


class AutoScheduleRequest(BaseModel):
    days: int = 7
    preview: bool = False


class AutoScheduleItem(BaseModel):
    content_id: int
    title: str
    category: str
    scheduled_at: datetime


class AutoScheduleOut(BaseModel):
    committed: bool
    assignments: list[AutoScheduleItem]
