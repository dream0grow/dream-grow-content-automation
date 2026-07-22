"""릴스/숏폼 대본 자동 생성(reels_script) 단위테스트.

실행: python3 -m pytest orchestrator/test_reels_script.py -q
"""
import pytest

from orchestrator import reels_script, run, source_ingest
from orchestrator.test_run import FakeState


# ---------- format 파싱 ----------

def test_wants_reels_variants():
    assert reels_script.wants_reels("reels")
    assert reels_script.wants_reels("thread, reels")
    assert reels_script.wants_reels("릴스")
    assert reels_script.wants_reels("숏폼")
    assert reels_script.wants_reels("Shorts")
    assert not reels_script.wants_reels("thread")
    assert not reels_script.wants_reels("youtube")
    assert not reels_script.wants_reels("")


def test_build_filename_rules():
    assert reels_script.build_filename("아침 등교 전쟁", "등교 준비") == \
        "원고_릴스_아침등교전쟁_등교준비.md"
    assert reels_script.build_filename("", "") == "원고_릴스_기타.md"


CARD = {
    "page_id": "vault/파이프라인/활성/DG-2026-0009 테스트.md",
    "content_id": "DG-2026-0009",
    "topic": "아침 등교 전쟁",
    "audience": "초등 학부모",
    "approved_keyword": "등교 준비",
    "format": "reels",
    "review_status": "",
}

BRIEF = {"core_message": "잔소리보다 순서", "outline": ["장면", "반전", "방법"]}

SCRIPT = "# 릴스 원고 -- 아침 등교 전쟁\n\n## 🎬 대본 (약 45초)\n" + "가나다라 " * 100


# ---------- 저장 (05 리뷰/대기) + script_feedback 감지 ----------

def test_save_to_review_and_feedback_pickup(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    name = reels_script.save_to_review(CARD, SCRIPT)
    p = tmp_path / "SNS 콘텐츠 제작 시스템" / "05 리뷰" / "대기" / name
    assert p.exists()

    from vault_pipeline.vault_io import parse_frontmatter
    meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
    assert meta.get("type") == "reels-script"
    assert str(meta.get("검수상태")) == "대기"
    assert meta.get("채널") == "reels"
    assert "릴스 원고" in body

    # script_feedback의 새 원고 감지에 잡힌다 (생성일이 오늘이라 최근 필터 통과)
    from vault_pipeline import script_feedback
    assert name in [s["name"] for s in script_feedback.find_new_scripts()]

    # 같은 이름 재저장 시 덮지 않고 새 파일
    assert reels_script.save_to_review(CARD, SCRIPT) != name


def test_generate_rejects_too_short(monkeypatch):
    monkeypatch.setattr(reels_script.llm, "call_writing", lambda *a, **k: "짧음")
    monkeypatch.setattr(reels_script.agent_dialogue, "load_hooks", lambda *a, **k: "")
    with pytest.raises(RuntimeError):
        reels_script.generate(CARD, BRIEF)


# ---------- run.handle_keyword_approved 원고 전용/혼합 경로 ----------

def _mk_state():
    state = FakeState()
    state.sections = []
    state.append_section = lambda pid, h, b: state.sections.append((h, b))
    state.append_formatted_section = state.append_section
    state.read_sections_by_prefix = lambda pid, *prefixes: ""
    return state


def test_keyword_approved_reels_only_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    state = _mk_state()
    run.store = state
    source_ingest.store = state
    monkeypatch.setattr(run.llm, "call_json", lambda *a, **k: dict(BRIEF))
    monkeypatch.setattr(run.reels_script, "generate", lambda *a, **k: SCRIPT)

    run.handle_keyword_approved(dict(CARD))

    merged = {}
    for _pid, fields in state.updates:
        merged.update(fields)
    assert merged.get("stage") == "published"
    assert merged.get("status") == "done"
    saved = list((tmp_path / "SNS 콘텐츠 제작 시스템" / "05 리뷰" / "대기").glob("원고_릴스_*.md"))
    assert len(saved) == 1
    assert any("릴스 원고" in h for h, _ in state.sections)
    assert any("릴스" in m and "완성" in m for _, m in state.notes)


def test_keyword_approved_youtube_and_reels_partial_failure(tmp_path, monkeypatch):
    """youtube+reels 전용 카드에서 유튜브가 실패해도 릴스가 성공하면 완료된다."""
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    state = _mk_state()
    run.store = state
    source_ingest.store = state
    monkeypatch.setattr(run.llm, "call_json", lambda *a, **k: dict(BRIEF))
    monkeypatch.setattr(
        run.youtube_script, "deliver",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("생성 실패")),
    )
    monkeypatch.setattr(run.reels_script, "generate", lambda *a, **k: SCRIPT)

    card = dict(CARD, format="youtube, reels")
    run.handle_keyword_approved(card)

    merged = {}
    for _pid, fields in state.updates:
        merged.update(fields)
    assert any("유튜브 원고 생성에 실패" in m for _, m in state.notes)
    assert merged.get("stage") == "published"
    assert merged.get("status") == "done"
