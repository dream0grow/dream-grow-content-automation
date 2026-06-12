import httpx
import pytest

from app.db.models import Content, PublishLog
from app.services import publisher
from app.services.publisher import publish_content

BRAND = "아이와 부모의 꿈을 키웁니다. -Dream_Grow-"
BODY = f"첫 글입니다.\n---\n두 번째 글입니다.\n\n{BRAND}"


def _make_content(db, body=BODY, status="발행대기", ctype="thread"):
    c = Content(type=ctype, title="발행 테스트", body=body, category="학습", status=status)
    db.add(c)
    db.commit()
    return c


def test_dry_run_publish(db):
    c = _make_content(db)
    log = publish_content(db, c)
    assert log.success
    assert log.dry_run
    assert log.posts_count == 2
    db.refresh(c)
    assert c.status == "발행완료"
    assert c.external_id == "dry-run-0"
    assert c.published_at is not None


def test_publish_rejects_over_limit(db):
    c = _make_content(db, body="가" * 501)
    log = publish_content(db, c)
    assert not log.success
    assert "500" in log.error
    db.refresh(c)
    assert c.status == "실패"


def test_publish_empty_body_fails(db):
    c = _make_content(db, body="")
    log = publish_content(db, c)
    assert not log.success
    db.refresh(c)
    assert c.status == "실패"


def test_reels_publish_is_status_only(db):
    c = _make_content(db, body="릴스 대본입니다", ctype="reels")
    log = publish_content(db, c)
    assert log.success
    db.refresh(c)
    assert c.status == "발행완료"
    assert c.external_id is None


def test_real_publish_chains_reply_to_id(db, monkeypatch):
    """httpx 모킹: reply_to_id 체이닝과 external_ids 기록 검증."""
    from app.core.config import Settings, get_settings

    settings = Settings(
        threads_access_token="tok", threads_user_id="uid",
        publish_dry_run=False, database_url="sqlite://",
    )
    monkeypatch.setattr(publisher, "get_settings", lambda: settings)
    monkeypatch.setattr(publisher.time, "sleep", lambda s: None)

    calls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, params=None):
            calls.append((url, dict(params or {})))
            if url.endswith("/threads"):
                return FakeResponse({"id": f"container-{len(calls)}"})
            return FakeResponse({"id": f"media-{len(calls)}"})

    monkeypatch.setattr(publisher.httpx, "Client", FakeClient)

    c = _make_content(db)
    log = publish_content(db, c)
    assert log.success
    assert not log.dry_run

    # 두 번째 글의 컨테이너 생성 요청에 reply_to_id가 첫 글 media id로 설정됐는지
    container_calls = [(u, p) for u, p in calls if u.endswith("/threads")]
    assert "reply_to_id" not in container_calls[0][1]
    assert container_calls[1][1]["reply_to_id"] == "media-2"

    db.refresh(c)
    assert c.status == "발행완료"
    assert len(c.external_ids) == 2


def test_mid_thread_failure_records_partial(db, monkeypatch):
    from app.core.config import Settings

    settings = Settings(
        threads_access_token="tok", threads_user_id="uid",
        publish_dry_run=False, database_url="sqlite://",
    )
    monkeypatch.setattr(publisher, "get_settings", lambda: settings)
    monkeypatch.setattr(publisher.time, "sleep", lambda s: None)

    call_count = {"n": 0}

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, params=None):
            call_count["n"] += 1
            if call_count["n"] >= 3:  # 두 번째 글 컨테이너 생성에서 실패
                return FakeResponse(400, {"error": "rate limit"})
            if url.endswith("/threads"):
                return FakeResponse(200, {"id": "container-1"})
            return FakeResponse(200, {"id": "media-1"})

    monkeypatch.setattr(publisher.httpx, "Client", FakeClient)

    c = _make_content(db)
    log = publish_content(db, c)
    assert not log.success
    assert "media-1" in log.error  # 부분 발행된 ID가 에러에 기록됨
    db.refresh(c)
    assert c.status == "실패"
