"""run.py의 안정성 수리(A1~A5)에 대한 단위테스트.

노션/옵시디언 백엔드 없이 orchestrator.run 이 참조하는 state 함수만 가짜로 갈아끼운다.
실행: python3 -m pytest orchestrator/test_run.py -q
"""
import types

from orchestrator import publish, run


class FakeState:
    """update_card/notify/read_latest_section/query_cards를 기록하는 가짜 백엔드."""

    def __init__(self, cards=None, sections=None):
        self.updates = []          # (page_id, fields) 누적
        self.notes = []            # (page_id, message)
        self._cards = cards or []
        self._sections = sections or {}  # (page_id, prefix) -> text

    def update_card(self, page_id, **fields):
        self.updates.append((page_id, fields))

    def notify(self, page_id, message):
        self.notes.append((page_id, message))

    def read_latest_section(self, page_id, prefix):
        return self._sections.get((page_id, prefix), "")

    def query_cards(self, stage=None, status=None, approval_status=None, page_size=20):
        out = []
        for c in self._cards:
            if stage and c.get("stage") != stage:
                continue
            if status and c.get("status") != status:
                continue
            if approval_status and c.get("approval_status") != approval_status:
                continue
            out.append(c)
        return out

    def age_minutes(self, card):
        return card.get("_age", 0.0)

    # run 이 호출할 수 있는 나머지는 no-op
    def require_backend(self):
        pass


def _patch(monkey_state):
    run.notion_state = monkey_state
    publish.notion_state = monkey_state


def _last_update(state, page_id):
    """가장 최근 update 병합 결과."""
    merged = {}
    for pid, fields in state.updates:
        if pid == page_id:
            merged.update(fields)
    return merged


# ---------- A2: 검수 미통과 승인은 조용히 막지 않고 통지 ----------

def test_final_approved_blocked_notifies():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "review_status": "revise"}
    run.handle_final_approved(card)
    merged = _last_update(st, "p1")
    assert merged.get("status") == "needs_human"
    assert merged.get("approval_status") == "blocked"
    assert st.notes and "DG-1" in st.notes[-1][1]


def test_final_approved_ok_goes_publish_ready():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "review_status": "approved"}
    run.handle_final_approved(card)
    merged = _last_update(st, "p1")
    assert merged.get("stage") == "publish_ready"
    assert merged.get("status") == "queued"


# ---------- A1: 수정 요청은 재초안 큐로 되돌린다 ----------

def test_revision_requested_reenqueues():
    st = FakeState(sections={("p1", run.REVISION_SECTION): "사례를 빼줘"})
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "approved_keyword": "스마트폰 규칙"}
    run.handle_revision_requested(card)
    merged = _last_update(st, "p1")
    assert merged.get("stage") == "keyword_approval"
    assert merged.get("approval_status") == "approved"
    assert merged.get("status") == "running"


def test_revision_requested_without_keyword_goes_keyword_gate():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "approved_keyword": ""}
    run.handle_revision_requested(card)
    merged = _last_update(st, "p1")
    assert merged.get("stage") == "keyword_approval"
    assert merged.get("approval_status") == "requested"
    assert st.notes  # 사람에게 통지


# ---------- A3: 실패는 1회 재시도 후 통지 ----------

def test_failure_retries_once_then_notifies():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "last_error": ""}
    # 1차 실패: keyword 는 재큐 대상 → status=queued + 재시도 표식, 통지 없음
    run._handle_failure(card, "keyword", RuntimeError("boom"))
    merged = _last_update(st, "p1")
    assert merged.get("status") == "queued"
    assert merged.get("last_error", "").startswith(run._RETRY_MARK)
    assert not st.notes

    # 2차 실패(표식 있음): failed + 통지
    st2 = FakeState()
    _patch(st2)
    card2 = {"page_id": "p1", "content_id": "DG-1",
             "last_error": f"{run._RETRY_MARK} boom"}
    run._handle_failure(card2, "keyword", RuntimeError("boom again"))
    merged2 = _last_update(st2, "p1")
    assert merged2.get("status") == "failed"
    assert st2.notes


def test_failure_status_agnostic_dequeues_on_final():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1",
            "last_error": f"{run._RETRY_MARK} x"}
    run._handle_failure(card, "keyword_approval", RuntimeError("boom"))
    merged = _last_update(st, "p1")
    assert merged.get("status") == "failed"
    assert merged.get("approval_status") == "failed"  # 무한 재시도 방지


# ---------- A4: 오래 멈춘 draft/brief 는 재큐 ----------

def test_sweep_stale_running_requeues():
    stale = {"page_id": "p1", "content_id": "DG-1", "stage": "draft",
             "status": "running", "approved_keyword": "kw", "_age": 120.0}
    fresh = {"page_id": "p2", "content_id": "DG-2", "stage": "draft",
             "status": "running", "approved_keyword": "kw", "_age": 5.0}
    st = FakeState(cards=[stale, fresh])
    _patch(st)
    run._sweep_stale_running(now_limit=60)
    assert _last_update(st, "p1").get("stage") == "keyword_approval"
    assert not any(pid == "p2" for pid, _ in st.updates)  # 신선한 카드는 안 건드림


# ---------- A5: split_posts 는 글을 유실하지 않는다 ----------

def test_split_posts_no_text_loss_on_long_paragraph():
    sentences = [f"이건 {i}번째 문장입니다." for i in range(60)]
    draft = " ".join(sentences)  # 500자 훨씬 초과 단일 문단
    posts = publish.split_posts(draft)
    assert len(posts) > 1
    for p in posts:
        assert len(p) <= publish.POST_CHAR_LIMIT
    joined = " ".join(posts)
    for i in range(60):
        assert f"이건 {i}번째 문장입니다." in joined


def test_split_posts_respects_separator():
    draft = "가나다\n---\n라마바"
    assert publish.split_posts(draft) == ["가나다", "라마바"]
