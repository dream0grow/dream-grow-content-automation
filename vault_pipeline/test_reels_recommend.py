"""릴스 원고 자동 추천 단위 테스트 — LLM/텔레그램 mock

실행: python3 -m pytest vault_pipeline/test_reels_recommend.py -v
"""
import json

import pytest

from orchestrator import llm
from vault_pipeline import reels_recommend as rr
from vault_pipeline import telegram_notify
from vault_pipeline.script_feedback import SCRIPT_DIR_DEFAULT

REELS_BODY = (
    "# 릴스 스크립트 (45초)\n\n"
    "**[0~3초] 후킹**\n"
    "\"스마트폰을 뺏으면 달라질 거라 생각하십니까.\"\n"
    "(화면: 아이 손 클로즈업)\n\n"
    "**[3~10초] 문제 공감**\n본문입니다.\n"
)


def _fm(topic: str, status: str = "리뷰대기", channel: str = "reels") -> str:
    return (f"---\n주제: {topic}\n카테고리: 미디어\n채널: {channel}\n"
            f"상태: {status}\n생성일: 2026-04-14\n검수상태: 통과\n---\n\n")


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    script_dir = tmp_path / SCRIPT_DIR_DEFAULT
    script_dir.mkdir(parents=True)
    for i in range(4):
        (script_dir / f"원고_릴스_미디어_주제{i}.md").write_text(
            _fm(f"주제{i}") + REELS_BODY, encoding="utf-8")
    sent: list[str] = []
    monkeypatch.setattr(telegram_notify, "send",
                        lambda text, html=False: sent.append(text) or True)
    monkeypatch.setattr(rr.telegram_notify, "send",
                        lambda text, html=False: sent.append(text) or True)
    monkeypatch.setattr(llm, "call_json", lambda *a, **k: {"picks": [
        {"index": 0, "reason": "훅이 강함"},
        {"index": 1, "reason": "공감 폭이 넓음"},
        {"index": 2, "reason": "시의성"},
    ]})
    return {"root": tmp_path, "script_dir": script_dir, "sent": sent}


def test_find_candidates_reels_only(vault):
    (vault["script_dir"] / "원고_YT롱폼_수학_다른형식.md").write_text(
        _fm("유튜브 원고", channel="youtube").replace("원고_릴스", "") + REELS_BODY,
        encoding="utf-8")
    names = [c["name"] for c in rr.find_candidates()]
    assert "원고_YT롱폼_수학_다른형식.md" not in names
    assert len(names) == 4


def test_find_candidates_excludes_done_states(vault):
    (vault["script_dir"] / "원고_릴스_미디어_주제0.md").write_text(
        _fm("주제0", status="발행완료") + REELS_BODY, encoding="utf-8")
    names = [c["name"] for c in rr.find_candidates()]
    assert "원고_릴스_미디어_주제0.md" not in names
    assert len(names) == 3


def test_extract_hook_from_section():
    hook = rr.extract_hook(REELS_BODY)
    assert hook == '"스마트폰을 뺏으면 달라질 거라 생각하십니까."'


def test_run_sends_and_updates_ledger(vault):
    picked = rr.run(count=3)
    assert len(picked) == 3
    assert len(vault["sent"]) == 1
    msg = vault["sent"][0]
    assert "릴스 추천 TOP 3" in msg
    assert "훅이 강함" in msg
    assert "https://github.com/" in msg
    ledger = json.loads(
        (vault["root"] / "_system/logs/reels_recommend_ledger.json")
        .read_text(encoding="utf-8"))
    assert set(picked) == set(ledger["recommended"].keys())


def test_rotation_prefers_unrecommended(vault):
    rr.run(count=3)  # 주제0~2 추천됨
    pool = rr.build_pool(rr.find_candidates(), rr._load_ledger(), count=3)
    assert pool[0]["name"] == "원고_릴스_미디어_주제3.md"  # 미추천이 맨 앞
    # 부족분은 가장 오래전 추천분으로 채워 순환한다
    assert len(pool) == 4


def test_dry_run_no_send_no_ledger(vault):
    picked = rr.run(count=3, dry_run=True)
    assert len(picked) == 3
    assert vault["sent"] == []
    assert not (vault["root"] / "_system/logs/reels_recommend_ledger.json").exists()


def test_llm_failure_skips_quietly(vault, monkeypatch):
    monkeypatch.setattr(llm, "call_json",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    assert rr.run(count=3) == []
    assert vault["sent"] == []


def test_send_failure_keeps_ledger_empty(vault, monkeypatch):
    monkeypatch.setattr(rr.telegram_notify, "send", lambda *a, **k: False)
    assert rr.run(count=3) == []
    assert not (vault["root"] / "_system/logs/reels_recommend_ledger.json").exists()
