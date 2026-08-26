"""발행 심사관(verify.py) 단위 테스트 — LLM/저장소 mock

실행: python3 -m pytest orchestrator/test_verify.py -q
"""
from orchestrator import verify


class FakeStore:
    def __init__(self, drafts=None, cards=None):
        self.drafts = drafts or {}          # (page_id, fmt) -> draft
        self.cards = cards or []
        self.sections = []                  # (page_id, heading, markdown)
        self.updates = []                   # (page_id, fields)

    def read_final_draft(self, page_id, fmt):
        return self.drafts.get((page_id, fmt), "")

    def read_latest_section(self, page_id, prefix):
        return "**핵심 메시지**: 아이의 수 감각이 먼저다"

    def append_formatted_section(self, page_id, heading, markdown):
        self.sections.append((page_id, heading, markdown))

    def update_card(self, page_id, **fields):
        self.updates.append((page_id, fields))

    def query_cards(self, stage=None, status=None, approval_status=None,
                    page_size=20):
        return list(self.cards)


GOOD = {
    "hook": 9, "readability": 9, "actionability": 9, "brand_fit": 9, "empathy": 9,
    "total": 45, "voice_match": 9, "ai_tell_issues": [], "fact_risk_sentences": [],
    "verdict": "recommend", "verdict_reason": "훅이 강하고 위험 없음", "fix_first": "",
}

BAD = {
    "hook": 5, "readability": 6, "actionability": 5, "brand_fit": 6, "empathy": 5,
    "total": 27, "voice_match": 5,
    "ai_tell_issues": ["~를 통해 확인할 수 있다"],
    "fact_risk_sentences": ["연구에 따르면 90%가 좋아진다 — 출처 없음"],
    "verdict": "needs_review", "verdict_reason": "출처 없는 수치", "fix_first": "",
}


def _card(page_id="p1", fmt="thread", **kw):
    return {"page_id": page_id, "content_id": "DG-2026-0001", "format": fmt,
            "topic": "초등 수 감각", "approved_keyword": "초등 수학",
            "approval_status": "requested", "verify_verdict": "", **kw}


def test_verify_card_writes_section_and_frontmatter(monkeypatch):
    store = FakeStore(drafts={("p1", "thread"): "긴 초안 본문 " * 30})
    monkeypatch.setattr(verify, "store", store)
    monkeypatch.setattr(verify.llm, "call_json", lambda *a, **k: dict(GOOD))
    results = verify.verify_card(_card())
    assert len(results) == 1 and results[0]["verdict"] == "recommend"
    assert store.sections and store.sections[0][1].startswith("🔍 발행 심사")
    fields = store.updates[-1][1]
    assert fields["verify_verdict"] == "recommend"
    assert fields["verify_score"] == "45/50"


def test_verify_card_no_draft_returns_empty(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(verify, "store", store)
    called = []
    monkeypatch.setattr(verify.llm, "call_json",
                        lambda *a, **k: called.append(1) or dict(GOOD))
    assert verify.verify_card(_card()) == []
    assert not called and not store.sections and not store.updates


def test_verify_worst_verdict_wins_across_formats(monkeypatch):
    store = FakeStore(drafts={("p1", "thread"): "글 " * 50,
                              ("p1", "newsletter"): "글 " * 50})
    monkeypatch.setattr(verify, "store", store)
    answers = iter([dict(GOOD), dict(BAD)])
    monkeypatch.setattr(verify.llm, "call_json", lambda *a, **k: next(answers))
    verify.verify_card(_card(fmt="thread, newsletter"))
    assert store.updates[-1][1]["verify_verdict"] == "needs_review"


def test_backfill_skips_already_verified(monkeypatch):
    cards = [_card(page_id="p1"),
             _card(page_id="p2", verify_verdict="recommend")]
    store = FakeStore(drafts={("p1", "thread"): "글 " * 50,
                              ("p2", "thread"): "글 " * 50}, cards=cards)
    monkeypatch.setattr(verify, "store", store)
    calls = []
    monkeypatch.setattr(verify.llm, "call_json",
                        lambda *a, **k: calls.append(1) or dict(GOOD))
    done = verify.backfill(limit=10)
    assert done == 1 and len(calls) == 1  # p2는 이미 심사됨 → 건너뜀


def test_summary_line_counts():
    line = verify.summary_line(dict(BAD))
    assert "27/50" in line and "위험 1건" in line and "AI 티 1건" in line
