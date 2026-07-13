"""유튜브 롱폼 원고 자동 생성(youtube_script) 단위테스트.

실행: python3 -m pytest orchestrator/test_youtube_script.py -q
"""
import types

import pytest

from orchestrator import run, youtube_script
from orchestrator.test_run import FakeState


# ---------- format 파싱 ----------

def test_wants_youtube_variants():
    assert youtube_script.wants_youtube("youtube")
    assert youtube_script.wants_youtube("thread, youtube")
    assert youtube_script.wants_youtube("유튜브")
    assert youtube_script.wants_youtube("YT")
    assert not youtube_script.wants_youtube("thread")
    assert not youtube_script.wants_youtube("")


def test_build_filename_rules():
    name = youtube_script.build_filename("초등 수학 공부법?", "수감각")
    assert name == "원고_YT롱폼_초등수학공부법_수감각.md"
    # 금지문자 제거 + 빈 키워드 처리
    assert youtube_script.build_filename('시험 [올백] "비법"', "") == "원고_YT롱폼_시험올백비법.md"
    assert youtube_script.build_filename("", "") == "원고_YT롱폼_기타.md"


# ---------- 저장 (05 리뷰/대기) + script_feedback 감지 ----------

CARD = {
    "page_id": "vault/파이프라인/활성/DG-2026-0009 테스트.md",
    "content_id": "DG-2026-0009",
    "topic": "초등 시험 공부법",
    "audience": "초등 학부모",
    "approved_keyword": "시험 공부법",
    "format": "youtube",
    "review_status": "",
}

BRIEF = {"core_message": "문제 양보다 이해", "outline": ["장면", "반전", "방법"]}

SCRIPT = "# 영상 원고 -- 초등 시험 공부법\n\n## 🎬 도입부 (0:00~0:30)\n" + "가나다라 " * 200


def test_save_to_review_and_feedback_pickup(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    name = youtube_script.save_to_review(CARD, SCRIPT)
    p = tmp_path / "SNS 콘텐츠 제작 시스템" / "05 리뷰" / "대기" / name

    # 폴더 규칙 확인: VAULT_SCRIPT_PATH 기본값과 같은 위치여야 script_feedback이 찾는다
    assert p.exists(), f"원고가 기본 원고 폴더에 없음: {name}"

    # frontmatter 스키마 (사이트/script_feedback과의 계약)
    from vault_pipeline.vault_io import parse_frontmatter
    meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
    assert meta.get("type") == "youtube-script"
    assert str(meta.get("검수상태")) == "대기"
    assert meta.get("generator") == "dreamgrow-orchestrator"
    assert "영상 원고" in body

    # script_feedback의 새 원고 감지에 실제로 잡히는지 (핑퐁 시작점)
    from vault_pipeline import script_feedback
    found = [s["name"] for s in script_feedback.find_new_scripts()]
    assert name in found

    # 같은 이름 재저장 시 덮지 않고 새 파일
    name2 = youtube_script.save_to_review(CARD, SCRIPT)
    assert name2 != name
    assert (p.parent / name2).exists()


def test_generate_rejects_too_short(monkeypatch):
    monkeypatch.setattr(youtube_script.llm, "call_writing", lambda *a, **k: "짧음")
    monkeypatch.setattr(youtube_script.agent_dialogue, "load_hooks", lambda *a, **k: "")
    with pytest.raises(RuntimeError):
        youtube_script.generate(CARD, BRIEF)


# ---------- run.handle_keyword_approved 유튜브 전용 경로 ----------

def _mk_state():
    state = FakeState()
    # handle_keyword_approved가 부르는 나머지 저장소 함수 보강
    state.sections = []
    state.append_section = lambda pid, h, b: state.sections.append((h, b))
    state.append_formatted_section = state.append_section
    state.read_sections_by_prefix = lambda pid, *prefixes: "리서치 요약"
    return state


def test_keyword_approved_youtube_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    state = _mk_state()
    run.store = state
    monkeypatch.setattr(run.llm, "call_json", lambda *a, **k: dict(BRIEF))
    monkeypatch.setattr(run.youtube_script, "generate", lambda *a, **k: SCRIPT)

    run.handle_keyword_approved(dict(CARD))

    merged = {}
    for _pid, fields in state.updates:
        merged.update(fields)
    # 유튜브 전용 카드는 발행 게이트 없이 완료 처리
    assert merged.get("stage") == "published"
    assert merged.get("status") == "done"
    # 원고 파일이 실제로 저장됨
    saved = list((tmp_path / "SNS 콘텐츠 제작 시스템" / "05 리뷰" / "대기").glob("원고_YT롱폼_*.md"))
    assert len(saved) == 1
    # 카드 섹션 + 완료 통지에 파일명 안내
    assert any("유튜브 원고" in h for h, _ in state.sections)
    assert any("유튜브 원고" in m for _, m in state.notes)


def test_keyword_approved_mixed_formats_continues_on_yt_failure(tmp_path, monkeypatch):
    """thread+youtube 카드에서 유튜브 생성이 실패해도 thread 초안은 계속 진행."""
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    state = _mk_state()
    run.store = state
    monkeypatch.setattr(run.llm, "call_json", lambda *a, **k: dict(BRIEF))
    monkeypatch.setattr(
        run.youtube_script, "deliver",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("생성 실패")),
    )
    # thread 초안 경로는 무겁게 돌지 않도록 최소 스텁
    monkeypatch.setattr(
        run.agent_dialogue, "run_draft_dialogue",
        lambda *a, **k: {"rounds": 1, "transcript": "t", "draft": "d",
                         "review": {"review_status": "approved"}},
    )
    monkeypatch.setattr(run.agent_dialogue, "get_style_context", lambda *a, **k: "")
    monkeypatch.setattr(run.agent_dialogue, "load_hooks", lambda *a, **k: "")
    monkeypatch.setattr(run.agent_dialogue, "load_benchmark", lambda *a, **k: "")

    card = dict(CARD, format="thread, youtube")
    run.handle_keyword_approved(card)

    merged = {}
    for _pid, fields in state.updates:
        merged.update(fields)
    # 실패 통지가 나가고, thread 흐름은 발행 승인 게이트까지 도달
    assert any("유튜브 원고 생성에 실패" in m for _, m in state.notes)
    assert merged.get("stage") == "approval"
    assert merged.get("approval_status") == "requested"
