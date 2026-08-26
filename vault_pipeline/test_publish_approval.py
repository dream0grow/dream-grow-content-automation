"""텔레그램 답장 발행 승인(publish 의도) 테스트

실행: python3 -m pytest vault_pipeline/test_publish_approval.py -v
"""
import pytest

from orchestrator import llm
from orchestrator import sns_publish as sp
from orchestrator import state as store
from vault_pipeline import script_feedback as sf
from vault_pipeline import telegram_notify


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    monkeypatch.delenv("VAULT_FEEDBACK_PATH", raising=False)
    (tmp_path / sf.SCRIPT_DIR_DEFAULT).mkdir(parents=True)
    (tmp_path / sf.FEEDBACK_DIR_DEFAULT).mkdir(parents=True)
    monkeypatch.setattr(telegram_notify, "send", lambda *a, **k: True)
    return tmp_path


def _feedback(vault, target, instruction):
    p = vault / sf.FEEDBACK_DIR_DEFAULT / "fb-001.md"
    p.write_text(
        f"---\ntype: feedback\nstatus: pending\ntarget: {target}\n---\n\n"
        f"# 피드백 -- {target}\n\n{instruction}\n", encoding="utf-8")
    return p


def _script(vault, name):
    p = vault / sf.SCRIPT_DIR_DEFAULT / name
    p.write_text("---\n주제: 승인 대상\n채널: thread\n상태: 리뷰대기\n"
                 "검수상태: 통과\n---\n\n본문입니다.\n", encoding="utf-8")
    return p


def test_publish_reply_marks_script_approved(vault, monkeypatch):
    monkeypatch.setattr(llm, "call_json", lambda *a, **k: {
        "kind": "publish", "reply": "", "publish_at": "2026-08-27 21:00"})
    script = _script(vault, "스레드_승인.md")
    fb = _feedback(vault, "스레드_승인.md", "발행해줘, 내일 9시에")
    counts = sf.apply_pending_feedback(dry_run=False)
    assert counts == {"approved": 1}
    fm, _ = sp.split_frontmatter(script.read_text(encoding="utf-8"))
    meta = sp.parse_meta(fm)
    assert meta["상태"] == sp.TRIGGER_STATE       # sns_publish가 집는 승인 상태
    assert meta["발행시간"] == "2026-08-27 21:00"
    assert "status: applied" in fb.read_text(encoding="utf-8")


def test_publish_reply_on_card_id_approves_card(vault, monkeypatch):
    monkeypatch.setattr(llm, "call_json", lambda *a, **k: {
        "kind": "publish", "reply": "", "publish_at": ""})
    store.create_card("카드 승인 주제", stage="approval", status="needs_human",
                      format="thread")
    card = store.query_cards(stage="approval")[0]
    _feedback(vault, card["content_id"], "이대로 발행 진행해줘")
    counts = sf.apply_pending_feedback(dry_run=False)
    assert counts == {"approved": 1}
    updated = store.query_cards(stage="approval")[0]
    assert updated["approval_status"] == "approved"


def test_revise_reply_still_revises(vault, monkeypatch):
    # publish 의도가 아닐 때 기존 수정 흐름이 유지되는지 (사본 없는 원고 파일 수정)
    monkeypatch.setattr(llm, "call_json", lambda *a, **k: {
        "kind": "revise", "reply": "", "publish_at": ""})
    monkeypatch.setattr(llm, "call_writing",
                        lambda *a, **k: "고친 본문입니다. " * 30)
    script = _script(vault, "스레드_수정.md")
    _feedback(vault, "스레드_수정.md", "도입부 더 짧게")
    counts = sf.apply_pending_feedback(dry_run=False)
    assert counts == {"applied": 1}
    assert "고친 본문입니다." in script.read_text(encoding="utf-8")
