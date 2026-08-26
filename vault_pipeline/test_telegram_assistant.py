"""텔레그램 비서 단위 테스트 — LLM/텔레그램/추천 mock

실행: python3 -m pytest vault_pipeline/test_telegram_assistant.py -v
"""
import json

import pytest

from orchestrator import llm
from vault_pipeline import reels_recommend
from vault_pipeline import telegram_assistant as ta
from vault_pipeline import telegram_notify
from vault_pipeline.script_feedback import SCRIPT_DIR_DEFAULT, find_pending_feedback

SCRIPT_NAME = "원고_릴스_학교_학교+가기+싫다는+아이.md"

NOTE = (
    "---\n"
    'title: "메시지"\n'
    "author: 이한결(구술)\n"
    "verbatim: true\n"
    "status: candidate\n"
    "출처: telegram\n"
    "created: 2026-08-26\n"
    "tags: [후보, 아이디어]\n"
    "---\n\n"
    "# 메시지\n\n"
    "릴스 원고 3개 추천해줘. 그리고 학교 가기 싫다는 아이 원고는 도입부를 더 짧게 바꿔줘.\n\n"
    "## 참고 후보 (candidate 단계)\n"
    f"- SNS 콘텐츠 제작 시스템/05 리뷰/대기/{SCRIPT_NAME}\n"
)


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    monkeypatch.delenv("VAULT_FEEDBACK_PATH", raising=False)
    cand_dir = tmp_path / ta.CANDIDATE_DIR
    cand_dir.mkdir(parents=True)
    note_path = cand_dir / "2026-08-26 190000 메시지.md"
    note_path.write_text(NOTE, encoding="utf-8")
    script_dir = tmp_path / SCRIPT_DIR_DEFAULT
    script_dir.mkdir(parents=True)
    (script_dir / SCRIPT_NAME).write_text(
        "---\n주제: 학교\n채널: reels\n상태: 리뷰대기\n---\n\n본문\n", encoding="utf-8")

    sent: list[str] = []
    monkeypatch.setattr(telegram_notify, "send",
                        lambda text, html=False: sent.append(text) or True)
    monkeypatch.setattr(ta.telegram_notify, "send",
                        lambda text, html=False: sent.append(text) or True)
    recommended: list[int] = []
    monkeypatch.setattr(ta.reels_recommend, "run",
                        lambda count=3, dry_run=False:
                        recommended.append(count) or ["a.md"] * count)
    return {"root": tmp_path, "note": note_path, "sent": sent,
            "recommended": recommended}


def _set_llm(monkeypatch, actions):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return {"actions": actions}
    monkeypatch.setattr(llm, "call_json", fake)
    return calls


def test_answer_sends_reply_and_marks_processed(vault, monkeypatch):
    _set_llm(monkeypatch, [{"kind": "answer", "reply": "네, 됩니다."}])
    assert ta.run() == 1
    assert any("네, 됩니다." in s for s in vault["sent"])
    assert "status: processed" in vault["note"].read_text(encoding="utf-8")
    ledger = json.loads((vault["root"] / "_system/logs/telegram_assistant_ledger.json")
                        .read_text(encoding="utf-8"))
    assert vault["note"].name in ledger["notes"]


def test_recommend_calls_reels_recommend(vault, monkeypatch):
    _set_llm(monkeypatch, [{"kind": "recommend", "count": 3}])
    ta.run()
    assert vault["recommended"] == [3]


def test_revise_creates_pending_feedback_note(vault, monkeypatch):
    _set_llm(monkeypatch, [{"kind": "revise", "target": SCRIPT_NAME,
                            "instruction": "도입부를 더 짧게"}])
    ta.run()
    pending = find_pending_feedback()
    assert len(pending) == 1
    assert pending[0]["target"] == SCRIPT_NAME
    assert "도입부를 더 짧게" in pending[0]["instruction"]
    assert any("접수했어요" in s for s in vault["sent"])


def test_multi_action_message(vault, monkeypatch):
    _set_llm(monkeypatch, [
        {"kind": "recommend", "count": 3},
        {"kind": "revise", "target": SCRIPT_NAME, "instruction": "도입부 짧게"},
        {"kind": "answer", "reply": "처리했어요."},
    ])
    ta.run()
    assert vault["recommended"] == [3]
    assert len(find_pending_feedback()) == 1
    assert any("처리했어요." in s for s in vault["sent"])
    assert "status: processed" in vault["note"].read_text(encoding="utf-8")


def test_idea_keeps_candidate_but_ledger_marks(vault, monkeypatch):
    calls = _set_llm(monkeypatch, [{"kind": "idea"}])
    assert ta.run() == 1
    assert "status: candidate" in vault["note"].read_text(encoding="utf-8")
    assert ta.run() == 0  # 장부 덕에 재판정 없음
    assert calls["n"] == 1


def test_llm_failure_retries_next_run(vault, monkeypatch):
    monkeypatch.setattr(llm, "call_json",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    assert ta.run() == 0
    assert vault["sent"] == []
    assert not (vault["root"] / "_system/logs/telegram_assistant_ledger.json").exists()
    assert len(ta.find_pending_notes()) == 1  # 다음 실행에 다시 잡힌다


def test_invalid_revise_target_falls_back_to_question(vault, monkeypatch):
    _set_llm(monkeypatch, [{"kind": "revise", "target": "없는파일.md",
                            "instruction": "고쳐줘"}])
    ta.run()
    assert find_pending_feedback() == []
    assert any("못 찾았어요" in s for s in vault["sent"])


def test_dry_run_no_writes_no_sends(vault, monkeypatch):
    _set_llm(monkeypatch, [{"kind": "answer", "reply": "답"}])
    ta.run(dry_run=True)
    assert vault["sent"] == []
    assert "status: candidate" in vault["note"].read_text(encoding="utf-8")
    assert not (vault["root"] / "_system/logs/telegram_assistant_ledger.json").exists()
