"""3안 병렬 판정단(agent_dialogue._panel_first_draft) 단위 테스트 — LLM mock

실행: python3 -m pytest orchestrator/test_panel.py -q
"""
from orchestrator import agent_dialogue as ad

LONG = lambda tag: f"{tag} 초안 본문 " * 30  # noqa: E731 — 200자 이상 보장

JUDGE = {"scores": {"A": 7, "B": 9}, "winner": "B",
         "reason": "훅이 더 강함",
         "borrow_suggestions": ["A의 첫 문장 훅을 도입에 반영"]}


def _patch_providers(monkeypatch, openai=True, gemini=False):
    monkeypatch.setattr(ad, "PANEL_ENABLED", True)
    monkeypatch.setattr(ad.llm, "openai_available", lambda: openai)
    monkeypatch.setattr(ad.llm, "gemini_available", lambda: gemini)
    monkeypatch.setattr(ad.llm, "call", lambda *a, **k: LONG("클로드"))
    monkeypatch.setattr(ad.llm, "call_openai", lambda *a, **k: LONG("지피티"))
    monkeypatch.setattr(ad.llm, "call_gemini", lambda *a, **k: LONG("제미나이"))


def test_panel_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(ad, "PANEL_ENABLED", False)
    assert ad._panel_first_draft("p", "s", 8000, "thread", "요약") is None


def test_panel_without_thirdparty_keys_returns_none(monkeypatch):
    _patch_providers(monkeypatch, openai=False, gemini=False)
    assert ad._panel_first_draft("p", "s", 8000, "thread", "요약") is None


def test_panel_picks_judge_winner_and_borrows(monkeypatch):
    _patch_providers(monkeypatch, openai=True)
    monkeypatch.setattr(ad.llm, "call_json", lambda *a, **k: dict(JUDGE))
    draft, entries, borrow = ad._panel_first_draft("p", "s", 8000, "thread", "요약")
    assert draft.startswith("지피티")          # winner B = 두 번째 후보(GPT)
    assert borrow == "A의 첫 문장 훅을 도입에 반영"
    assert any("판정단 심사" in e for e in entries)


def test_panel_single_survivor_skips_judge(monkeypatch):
    _patch_providers(monkeypatch, openai=True)
    def openai_fail(*a, **k):
        raise RuntimeError("타임아웃")
    monkeypatch.setattr(ad.llm, "call_openai", openai_fail)
    judged = []
    monkeypatch.setattr(ad.llm, "call_json",
                        lambda *a, **k: judged.append(1) or dict(JUDGE))
    draft, entries, borrow = ad._panel_first_draft("p", "s", 8000, "thread", "요약")
    assert draft.startswith("클로드") and borrow == "" and not judged
    assert any("후보 생성 실패" in e for e in entries)


def test_panel_bad_winner_letter_falls_back_to_first(monkeypatch):
    _patch_providers(monkeypatch, openai=True)
    monkeypatch.setattr(ad.llm, "call_json",
                        lambda *a, **k: {"winner": "Z", "scores": {},
                                         "borrow_suggestions": []})
    draft, _, borrow = ad._panel_first_draft("p", "s", 8000, "thread", "요약")
    assert draft.startswith("클로드") and borrow == ""


def test_run_draft_dialogue_uses_panel_winner(monkeypatch):
    """판정단 승자가 비평가 루프의 시작 초안이 된다 (접붙임 포함)."""
    _patch_providers(monkeypatch, openai=True)
    answers = {"panel": dict(JUDGE),
               "critic": {"verdict": "pass"},
               "ethics": {"review_status": "approved", "risk_level": "low"}}
    def fake_json(prompt, **k):
        if "심사위원장" in prompt:
            return answers["panel"]
        if "비평가" in prompt:
            return answers["critic"]
        return answers["ethics"]
    monkeypatch.setattr(ad.llm, "call_json", fake_json)
    merged = LONG("접붙임")
    monkeypatch.setattr(ad.llm, "call_writing", lambda *a, **k: merged)
    result = ad.run_draft_dialogue({"core_message": "m", "cta": "c"}, "thread")
    assert result["draft"] == merged          # borrow → 접붙임 재작성본이 최종 v1
    assert "판정단 심사" in result["transcript"]
