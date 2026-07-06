"""발행 후 되먹임(문체 학습 + 원자 메모 분해) 단위 테스트 — LLM mock

실행: python3 -m pytest vault_pipeline/test_feedback.py -v
"""
import pytest

from orchestrator import llm
from vault_pipeline import feedback
from vault_pipeline.writers import load_style_lessons


AI_ORIGINAL = "# 오답 교실\n\n첫째, 오답을 공유합니다. 둘째, 칭찬합니다.\n결론적으로 오답은 좋은 것입니다."
FINAL = "# 오답 교실\n\n오답을 같이 봅니다.\n그 순간 교실 공기가 달라집니다.\n\n오답은 배움의 재료입니다."

STYLE_RESULT = {"교훈": [
    "'첫째·둘째' 병렬을 쓰지 말고 장면으로 이어가라",
    "'결론적으로' 같은 정리 신호어를 빼라",
]}
ATOMIZE_RESULT = {"메모": [
    {"제목": "오답은 배움의 재료다", "발췌": "오답은 배움의 재료입니다."},
]}


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    draft_dir = tmp_path / "프로젝트/교육운동/블로그_초안"
    draft_dir.mkdir(parents=True)
    (draft_dir / "2026-07-06 오답 교실.md").write_text(
        "---\ntitle: 오답 교실\n채널: 블로그(교사)\n상태: 발행완료\n"
        "타겟: 교사그룹\n---\n\n" + FINAL, encoding="utf-8")
    # 리뷰대기(미발행) 글은 되먹임 대상이 아니어야 한다
    (draft_dir / "2026-07-06 미발행 글.md").write_text(
        "---\n채널: 블로그(교사)\n상태: 리뷰대기\n---\n\n본문", encoding="utf-8")
    orig_dir = tmp_path / "_system/ai_originals/블로그_초안"
    orig_dir.mkdir(parents=True)
    (orig_dir / "2026-07-06 오답 교실.md").write_text(AI_ORIGINAL, encoding="utf-8")

    def fake_call_json(prompt, **k):
        return STYLE_RESULT if "편집 규칙" in prompt else ATOMIZE_RESULT
    monkeypatch.setattr(llm, "call_json", fake_call_json)
    return tmp_path


def _run():
    for t in feedback.find_published():
        lessons = feedback.learn_style(t, dry_run=False)
        memos = feedback.atomize(t, dry_run=False)
        ledger = feedback._load_ledger()
        ledger[t["key"]] = {"lessons": lessons, "memos": memos}
        feedback._save_ledger(ledger)


def test_feedback_loop(vault):
    targets = feedback.find_published()
    assert len(targets) == 1                      # 발행완료 글만 대상
    _run()

    # ① 문체 학습: 채널 섹션에 규칙 누적 + 프롬프트 주입 확인
    lessons_md = (vault / "_system/style_lessons.md").read_text(encoding="utf-8")
    assert "## 블로그(교사)" in lessons_md
    assert "'첫째·둘째' 병렬" in lessons_md
    injected = load_style_lessons("블로그(교사)")
    assert "반드시 전부 적용" in injected and "정리 신호어" in injected
    assert load_style_lessons("페이스북(교사)") == ""   # 다른 채널엔 미주입

    # ② 원자 메모: 사람이 확정한 문장 그대로, own_content + 원출처 추적 플래그
    memos = list((vault / "제텔카스텐/1. 메모").glob("*.md"))
    assert len(memos) == 1
    text = memos[0].read_text(encoding="utf-8")
    assert "author: 이한결" in text
    assert "source_type: own_content" in text
    assert "원출처_추적" in text
    assert "오답은 배움의 재료입니다." in text


def test_feedback_idempotent(vault):
    _run()
    assert feedback.find_published() == []        # 장부 기록 후 재처리 없음
    _run()
    assert len(list((vault / "제텔카스텐/1. 메모").glob("*.md"))) == 1


def test_no_style_learning_without_original(vault):
    """AI 원본이 없으면(직접 쓴 글) 문체 학습은 건너뛰고 메모 분해만 한다."""
    orig = vault / "_system/ai_originals/블로그_초안/2026-07-06 오답 교실.md"
    orig.unlink()
    t = feedback.find_published()[0]
    assert feedback.learn_style(t, dry_run=False) == 0
    assert not (vault / "_system/style_lessons.md").exists()
    assert feedback.atomize(t, dry_run=False) == 1
