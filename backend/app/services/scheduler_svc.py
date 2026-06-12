"""발행 슬롯 자동 배정 - 레거시 calendar_scheduler.py 알고리즘 포팅 (DB 기반)

배정 규칙:
1. 내일부터 SCHEDULE_DAYS일 동안의 슬롯을 채운다
2. 하루 최대 MAX_PER_DAY개
3. 같은 카테고리를 연일 배치하지 않는다 (1차 우선)
4. 같은 날에 같은 카테고리를 배치하지 않는다 (2차, 엄격)
5. 당일에 배치 가능한 카테고리가 없으면 다음 날로 넘긴다
"""
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    MAX_PER_DAY,
    PUBLISH_HOURS,
    SCHEDULE_DAYS,
    ContentStatus,
    ContentType,
    normalize_category,
)
from app.db.models import Content


def _build_occupied_slots(db: Session, now: datetime) -> dict:
    """이미 점유된 슬롯을 날짜별로 정리. {'YYYY-MM-DD': [{'hour','minute','category'}]}"""
    window_start = now - timedelta(days=2)  # 전날 카테고리 회피용으로 과거 포함
    rows = db.scalars(
        select(Content).where(
            Content.scheduled_at.isnot(None),
            Content.scheduled_at >= window_start,
            Content.status.in_([
                ContentStatus.publish_wait.value,
                ContentStatus.published.value,
            ]),
        )
    ).all()

    slots = defaultdict(list)
    for c in rows:
        dt = c.scheduled_at
        slots[dt.strftime("%Y-%m-%d")].append({
            "hour": dt.hour,
            "minute": dt.minute,
            "category": normalize_category(c.category),
        })
    return slots


def auto_schedule(db: Session, days: int = SCHEDULE_DAYS,
                  now: datetime | None = None) -> list[tuple[Content, datetime]]:
    """미배정 리뷰완료 스레드에 발행시간을 배정한다. [(content, datetime), ...] 반환.
    커밋은 호출 측 책임 (preview 지원).
    """
    now = now or datetime.now()
    unscheduled = list(db.scalars(
        select(Content).where(
            Content.status == ContentStatus.review_done.value,
            Content.scheduled_at.is_(None),
            Content.type == ContentType.thread.value,
        ).order_by(Content.created_at)
    ).all())

    if not unscheduled:
        return []

    slots = _build_occupied_slots(db, now)
    assignments: list[tuple[Content, datetime]] = []
    start_date = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    remaining = list(unscheduled)

    for day_offset in range(days):
        target_date = start_date + timedelta(days=day_offset)
        date_key = target_date.strftime("%Y-%m-%d")
        prev_key = (target_date - timedelta(days=1)).strftime("%Y-%m-%d")

        used_hm = {(s["hour"], s.get("minute", 0)) for s in slots.get(date_key, [])}
        available_hours = [hm for hm in PUBLISH_HOURS if hm not in used_hm]
        day_count = len(slots.get(date_key, []))

        if day_count >= MAX_PER_DAY or not available_hours:
            continue

        prev_cats = {s["category"] for s in slots.get(prev_key, [])}
        day_cats = {s["category"] for s in slots.get(date_key, [])}
        slots_to_fill = min(MAX_PER_DAY - day_count, len(available_hours))

        for _ in range(slots_to_fill):
            if not remaining or not available_hours:
                break

            best, best_idx = None, -1
            # 1차: 전날+당일 카테고리와 모두 겹치지 않는 콘텐츠
            for i, c in enumerate(remaining):
                cat = normalize_category(c.category)
                if cat not in prev_cats and cat not in day_cats:
                    best, best_idx = c, i
                    break
            # 2차: 당일 카테고리와만 겹치지 않는 콘텐츠
            if best is None:
                for i, c in enumerate(remaining):
                    cat = normalize_category(c.category)
                    if cat not in day_cats:
                        best, best_idx = c, i
                        break
            # 당일 카테고리와 겹치지 않는 콘텐츠가 없으면 다음 날로
            if best is None:
                break

            hour, minute = available_hours.pop(0)
            assigned_dt = target_date.replace(hour=hour, minute=minute)
            assignments.append((best, assigned_dt))

            cat = normalize_category(best.category)
            slots[date_key].append({"hour": hour, "minute": minute, "category": cat})
            day_cats.add(cat)
            remaining.pop(best_idx)

    return assignments


def commit_assignments(db: Session, assignments: list[tuple[Content, datetime]]) -> None:
    for content, dt in assignments:
        content.scheduled_at = dt
        content.status = ContentStatus.publish_wait.value
    db.commit()
