from datetime import datetime, timedelta

from app.core.constants import PUBLISH_HOURS
from app.db.models import Content
from app.services.scheduler_svc import auto_schedule, commit_assignments


def _seed(db, n: int, category: str, status: str = "리뷰완료"):
    rows = []
    for i in range(n):
        c = Content(
            type="thread", title=f"{category} 콘텐츠 {i}", body="본문",
            category=category, status=status,
        )
        db.add(c)
        rows.append(c)
    db.commit()
    return rows


def test_slots_match_publish_hours(db):
    _seed(db, 3, "수학")
    now = datetime(2026, 6, 12, 10, 0)
    assignments = auto_schedule(db, now=now)
    assert len(assignments) == 3
    for _, dt in assignments:
        assert (dt.hour, dt.minute) in PUBLISH_HOURS
        # 내일부터 시작
        assert dt.date() >= (now + timedelta(days=1)).date()


def test_no_same_category_same_day(db):
    _seed(db, 4, "수학")
    _seed(db, 3, "독서")
    now = datetime(2026, 6, 12, 10, 0)
    assignments = auto_schedule(db, now=now)

    by_day: dict[str, list[str]] = {}
    for c, dt in assignments:
        by_day.setdefault(dt.strftime("%Y-%m-%d"), []).append(c.category)
    for day, cats in by_day.items():
        assert len(cats) == len(set(cats)), f"{day}에 동일 카테고리 중복: {cats}"


def test_max_per_day_cap(db):
    _seed(db, 10, "수학")
    _seed(db, 10, "독서")
    _seed(db, 10, "훈육")
    now = datetime(2026, 6, 12, 10, 0)
    assignments = auto_schedule(db, now=now)

    by_day: dict[str, int] = {}
    for _, dt in assignments:
        key = dt.strftime("%Y-%m-%d")
        by_day[key] = by_day.get(key, 0) + 1
    assert all(count <= 3 for count in by_day.values())


def test_commit_assignments_updates_status(db):
    _seed(db, 2, "감정")
    now = datetime(2026, 6, 12, 10, 0)
    assignments = auto_schedule(db, now=now)
    commit_assignments(db, assignments)

    for c, dt in assignments:
        db.refresh(c)
        assert c.status == "발행대기"
        assert c.scheduled_at == dt


def test_only_threads_scheduled(db):
    _seed(db, 1, "수학")
    reels = Content(type="reels", title="릴스", body="대본", category="수학", status="리뷰완료")
    db.add(reels)
    db.commit()

    assignments = auto_schedule(db, now=datetime(2026, 6, 12, 10, 0))
    assert all(c.type == "thread" for c, _ in assignments)
