"""일일 발행 추천 다이제스트(daily_digest.py) 단위 테스트 — LLM/저장소 mock

실행: python3 -m pytest orchestrator/test_daily_digest.py -q
"""
from orchestrator import daily_digest as dd


class FakeStore:
    def __init__(self, cards, drafts):
        self.cards = cards
        self.drafts = drafts

    def query_cards(self, stage=None, status=None, approval_status=None,
                    page_size=20):
        return [c for c in self.cards if c.get("stage") == stage]

    def read_final_draft(self, page_id, fmt):
        return self.drafts.get(page_id, "")

    def require_backend(self):
        pass


def _card(n, **kw):
    return {"page_id": f"p{n}", "content_id": f"DG-2026-{n:04d}",
            "topic": f"주제 {n}", "stage": "approval",
            "approval_status": "requested", "format": "thread",
            "verify_verdict": "recommend", "verify_score": "45/50", **kw}


def _setup(monkeypatch, count=8):
    cards = [_card(n) for n in range(1, count + 1)]
    drafts = {f"p{n}": f"훅 문장 {n}번 — 부모가 멈추는 이야기\n\n본문" for n in
              range(1, count + 1)}
    store = FakeStore(cards, drafts)
    monkeypatch.setattr(dd, "store", store)
    return store


def test_collect_skips_blocked_and_empty(monkeypatch):
    store = _setup(monkeypatch, count=3)
    store.cards[1]["approval_status"] = "blocked"
    store.drafts["p3"] = ""  # 원고 없음
    got = dd.collect_waiting_cards()
    assert [c["content_id"] for c in got] == ["DG-2026-0001"]
    assert got[0]["hook"].startswith("훅 문장 1번")


def test_rank_uses_llm_picks(monkeypatch):
    _setup(monkeypatch, count=8)
    monkeypatch.setattr(dd.llm, "call_json", lambda *a, **k: {"picks": [
        {"content_id": "DG-2026-0007", "expected_score": 9, "reason": "훅 강함"},
        {"content_id": "DG-2026-0002", "expected_score": 8, "reason": "시의성"},
    ]})
    cards = dd.collect_waiting_cards()
    picks = dd.rank_cards(cards, count=5)
    assert [p["content_id"] for p in picks] == ["DG-2026-0007", "DG-2026-0002"]
    assert picks[0]["pick_reason"] == "훅 강함"


def test_rank_falls_back_on_llm_failure(monkeypatch):
    _setup(monkeypatch, count=8)
    def boom(*a, **k):
        raise ValueError("json 깨짐")
    monkeypatch.setattr(dd.llm, "call_json", boom)
    cards = dd.collect_waiting_cards()
    picks = dd.rank_cards(cards, count=5)
    assert len(picks) == 5


def test_digest_message_contains_ids_and_approve_howto(monkeypatch):
    _setup(monkeypatch, count=2)
    cards = dd.collect_waiting_cards()
    msg = dd.build_digest(cards, waiting_total=44, dry_run=True)
    assert "DG-2026-0001" in msg and "DG-2026-0002" in msg
    assert "대기 44건" in msg and "승인" in msg
    assert "심사 45/50" in msg  # 기존 심사 결과 표기


def test_digest_runs_verify_when_missing(monkeypatch):
    store = _setup(monkeypatch, count=1)
    store.cards[0]["verify_verdict"] = ""
    called = []
    monkeypatch.setattr(dd.verify, "verify_card",
                        lambda card: called.append(card["content_id"]) or [
                            {"total": 44, "verdict": "recommend",
                             "verdict_reason": "좋음", "ai_tell_issues": [],
                             "fact_risk_sentences": []}])
    cards = dd.collect_waiting_cards()
    msg = dd.build_digest(cards, waiting_total=1, dry_run=False)
    assert called == ["DG-2026-0001"]
    assert "44/50" in msg
