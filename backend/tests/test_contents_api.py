BRAND = "아이와 부모의 꿈을 키웁니다. -Dream_Grow-"

CLEAN_BODY = (
    "교실에서 매일 보는 장면이 있습니다. 아이들의 공부 이야기를 해보려 합니다.\n---\n"
    "아이가 노력을 안 하는 게 아니라 방법을 모르는 경우가 많습니다. "
    "교실에서 보면 시작점을 못 찾는 아이가 대부분이거든요.\n---\n"
    "어디서 막혔는지 묻는 질문 하나가 공부 습관의 시작이 됩니다.\n\n"
    f"아이가 건강하게 자라길 바랍니다.\n{BRAND}"
)


def _create(client, **overrides):
    payload = {"type": "thread", "title": "테스트 주제", "body": CLEAN_BODY, "category": "학습"}
    payload.update(overrides)
    resp = client.post("/api/contents", json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_create_and_get(client):
    created = _create(client)
    assert created["status"] == "리뷰대기"

    resp = client.get(f"/api/contents/{created['id']}")
    assert resp.status_code == 200
    detail = resp.json()
    assert len(detail["posts"]) == 3
    assert all(not p["over_limit"] for p in detail["posts"])


def test_list_filter(client):
    _create(client, category="수학")
    _create(client, category="독서")
    resp = client.get("/api/contents", params={"category": "수학"})
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["category"] == "수학"


def test_status_transition_flow(client):
    c = _create(client)
    cid = c["id"]

    # 리뷰대기 → 리뷰완료 (검수 통과)
    resp = client.post(f"/api/contents/{cid}/status", json={"status": "리뷰완료"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "리뷰완료"

    # 리뷰완료 → 발행완료 직접 전이는 즉시발행용으로 허용되지만,
    # 리뷰대기 → 발행대기는 비허용
    c2 = _create(client)
    resp = client.post(f"/api/contents/{c2['id']}/status", json={"status": "발행대기"})
    assert resp.status_code == 409


def test_review_error_blocks_approval(client):
    bad_body = CLEAN_BODY + " \U0001F600"
    c = _create(client, body=bad_body)
    resp = client.post(f"/api/contents/{c['id']}/status", json={"status": "리뷰완료"})
    assert resp.status_code == 409

    # force로는 가능
    resp = client.post(
        f"/api/contents/{c['id']}/status", json={"status": "리뷰완료", "force": True}
    )
    assert resp.status_code == 200


def test_review_fix(client):
    c = _create(client, body=CLEAN_BODY + " \U0001F600")
    resp = client.post(f"/api/contents/{c['id']}/review/fix")
    assert resp.status_code == 200
    data = resp.json()
    assert "\U0001F600" not in data["body"]
    assert data["review"]["passed"]


def test_edit_blocked_after_publish(client, db):
    from app.db.models import Content

    c = _create(client)
    content = db.get(Content, c["id"])
    content.status = "발행완료"
    db.commit()

    resp = client.put(f"/api/contents/{c['id']}", json={"title": "수정"})
    assert resp.status_code == 409
    resp = client.delete(f"/api/contents/{c['id']}")
    assert resp.status_code == 409


def test_schedule_and_unschedule(client):
    c = _create(client)
    cid = c["id"]
    client.post(f"/api/contents/{cid}/status", json={"status": "리뷰완료"})

    resp = client.post(
        f"/api/contents/{cid}/schedule", json={"scheduled_at": "2026-07-01T07:10:00"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "발행대기"

    # 같은 슬롯 중복 예약은 409
    c2 = _create(client)
    client.post(f"/api/contents/{c2['id']}/status", json={"status": "리뷰완료"})
    resp = client.post(
        f"/api/contents/{c2['id']}/schedule", json={"scheduled_at": "2026-07-01T07:10:00"}
    )
    assert resp.status_code == 409

    # 예약 해제
    resp = client.post(f"/api/contents/{cid}/schedule", json={"scheduled_at": None})
    assert resp.status_code == 200
    assert resp.json()["status"] == "리뷰완료"
    assert resp.json()["scheduled_at"] is None
