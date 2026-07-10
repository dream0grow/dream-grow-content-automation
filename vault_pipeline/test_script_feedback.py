"""원고 수정·보완 핑퐁(오케스트레이터 쪽) 단위 테스트 — LLM/텔레그램 mock

실행: python3 -m pytest vault_pipeline/test_script_feedback.py -v
"""
import pytest

from orchestrator import llm
from vault_pipeline import script_feedback as sf
from vault_pipeline import telegram_notify

SCRIPT_BODY = (
    "# 영상 원고 -- 초등 수학\n\n"
    "## 00:00 도입\n안녕하세요, 오늘은 초등 수학 이야기입니다. "
    "많은 학부모가 연산을 걱정합니다. 문제집을 몇 권씩 풀려도 아이가 힘들어합니다.\n\n"
    "## 01:00 본론\n연산보다 수 감각이 먼저입니다. 손으로 세어보는 경험이 중요합니다. "
    "구체물을 만지며 수를 이해한 아이는 나중에 추상적인 연산도 훨씬 수월하게 받아들입니다. "
    "그래서 서두르지 말고 충분히 놀듯이 익히게 해야 합니다.\n\n"
    "## 09:00 마무리\n오늘도 봐주셔서 감사합니다. 구독과 좋아요 부탁드립니다.\n"
)

SCRIPT_FM = (
    "---\n"
    "type: youtube-script\n"
    "상태: 초안\n"
    "생성일: 2026-07-10\n"
    "채널: youtube\n"
    "길이: 20분\n"
    "카테고리: 수학\n"
    "키워드: 초등수학, 수감각\n"
    "검수상태: 대기\n"
    "generator: yt-research\n"
    "---\n\n"
)

FEEDBACK_FM = (
    "---\n"
    "type: feedback\n"
    'target: "원고_YT롱폼_수학_초등수학.md"\n'
    "status: pending\n"
    "출처: telegram\n"
    "author: 이한결(구술)\n"
    "created: 2026-07-10\n"
    "tags: [피드백, 수정요청]\n"
    "---\n\n"
    "# 피드백 -- 원고_YT롱폼_수학_초등수학\n\n"
    "도입부를 더 짧게 줄이고 구독 요청 문장은 빼주세요.\n"
)

REVISED = (
    "# 영상 원고 -- 초등 수학\n\n"
    "## 00:00 도입\n오늘은 초등 수학 이야기입니다. 많은 학부모가 연산을 걱정합니다.\n\n"
    "## 01:00 본론\n연산보다 수 감각이 먼저입니다. 손으로 세어보는 경험이 중요합니다. "
    "구체물을 만지며 수를 이해한 아이는 나중에 추상적인 연산도 훨씬 수월하게 받아들입니다. "
    "그래서 서두르지 말고 충분히 놀듯이 익히게 해야 합니다.\n\n"
    "## 09:00 마무리\n오늘도 봐주셔서 감사합니다.\n"
)


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    monkeypatch.delenv("VAULT_FEEDBACK_PATH", raising=False)
    script_dir = tmp_path / sf.SCRIPT_DIR_DEFAULT
    script_dir.mkdir(parents=True)
    (script_dir / "원고_YT롱폼_수학_초등수학.md").write_text(
        SCRIPT_FM + SCRIPT_BODY, encoding="utf-8")
    fb_dir = tmp_path / sf.FEEDBACK_DIR_DEFAULT
    fb_dir.mkdir(parents=True)
    (fb_dir / "2026-07-10 1200 원고_YT롱폼_수학_초등수학 피드백.md").write_text(
        FEEDBACK_FM, encoding="utf-8")

    sent: list[str] = []
    monkeypatch.setattr(telegram_notify, "send",
                        lambda text: sent.append(text) or True)
    monkeypatch.setattr(sf.telegram_notify, "send",
                        lambda text: sent.append(text) or True)
    monkeypatch.setattr(llm, "call_writing", lambda *a, **k: REVISED)
    return {"root": tmp_path, "script_dir": script_dir, "fb_dir": fb_dir,
            "sent": sent}


# ---------- ① 알림 ----------

def test_find_new_scripts_lists_pending_youtube_script(vault):
    found = sf.find_new_scripts()
    assert [s["name"] for s in found] == ["원고_YT롱폼_수학_초등수학.md"]


def test_announce_includes_filename_and_ledgers(vault):
    names = sf.announce_new_scripts(dry_run=False)
    assert names == ["원고_YT롱폼_수학_초등수학.md"]
    # 텔레그램 메시지에 원고 파일명이 포함돼야 답장 핑퐁이 성립한다.
    assert any("원고_YT롱폼_수학_초등수학.md" in m for m in vault["sent"])
    # 클릭 가능한 GitHub 링크(퍼센트 인코딩)가 포함돼야 한다.
    assert any("https://github.com/" in m and "/blob/main/" in m
               for m in vault["sent"])
    # 두 번째 실행은 장부 때문에 재알림하지 않는다.
    assert sf.announce_new_scripts(dry_run=False) == []


def test_script_links_github_and_obsidian(monkeypatch):
    name = "원고_YT롱폼_수학_초등수학.md"
    monkeypatch.delenv("DG_OBSIDIAN_VAULT", raising=False)
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    gh = sf.script_links(name)
    assert gh.startswith("🔗 GitHub: https://github.com/")
    assert "%20" in gh  # 공백이 인코딩돼 텔레그램이 URL로 인식한다
    assert "obsidian://" not in gh  # vault 이름 미설정 시 옵시디언 링크 생략
    # vault 이름을 주면 옵시디언 링크도 붙는다.
    monkeypatch.setattr(sf, "OBSIDIAN_VAULT", "dreamgrow")
    both = sf.script_links(name)
    assert "obsidian://open?vault=dreamgrow" in both


def test_announce_skips_non_pending_review(vault):
    # 검수 완료 원고는 알리지 않는다.
    (vault["script_dir"] / "원고_YT롱폼_수학_초등수학.md").write_text(
        SCRIPT_FM.replace("검수상태: 대기", "검수상태: 완료") + SCRIPT_BODY,
        encoding="utf-8")
    assert sf.find_new_scripts() == []


# ---------- ② 반영 ----------

def test_apply_pending_revises_script_and_marks_applied(vault):
    counts = sf.apply_pending_feedback(dry_run=False)
    assert counts.get("applied") == 1
    # 원고 본문이 수정되고 프론트매터는 보존된다.
    script = (vault["script_dir"] / "원고_YT롱폼_수학_초등수학.md").read_text(
        encoding="utf-8")
    assert "type: youtube-script" in script
    assert "구독과 좋아요" not in script          # 요청대로 제거된 문장
    assert "수정 반영" in script                   # 감사 흔적(HTML 주석)
    # 피드백 노트가 applied로 갱신된다(재처리 방지).
    fb = list(vault["fb_dir"].glob("*.md"))[0].read_text(encoding="utf-8")
    assert "status: applied" in fb
    assert "status: pending" not in fb
    assert "applied_by: orchestrator" in fb
    # 두 번째 실행은 pending이 없어 반영 0건.
    assert sf.apply_pending_feedback(dry_run=False).get("applied") is None


def test_apply_unresolved_target_marks_error(vault):
    (vault["fb_dir"] / "2026-07-10 1200 원고_YT롱폼_수학_초등수학 피드백.md").write_text(
        FEEDBACK_FM.replace("원고_YT롱폼_수학_초등수학.md", "없는원고.md"),
        encoding="utf-8")
    counts = sf.apply_pending_feedback(dry_run=False)
    assert counts.get("unresolved") == 1
    fb = list(vault["fb_dir"].glob("*.md"))[0].read_text(encoding="utf-8")
    assert "status: error" in fb


def test_apply_guards_against_content_loss(vault, monkeypatch):
    # LLM이 원고를 통째로 날린(짧은) 결과를 내면 반영하지 않고 error로 남긴다.
    monkeypatch.setattr(llm, "call_writing", lambda *a, **k: "짧음")
    counts = sf.apply_pending_feedback(dry_run=False)
    assert counts.get("too_short") == 1
    script = (vault["script_dir"] / "원고_YT롱폼_수학_초등수학.md").read_text(
        encoding="utf-8")
    assert "수 감각이 먼저입니다" in script  # 원본 보존
    fb = list(vault["fb_dir"].glob("*.md"))[0].read_text(encoding="utf-8")
    assert "status: error" in fb


def test_dry_run_writes_nothing(vault):
    sf.announce_new_scripts(dry_run=True)
    sf.apply_pending_feedback(dry_run=True)
    # 원고·피드백 모두 원문 그대로.
    fb = list(vault["fb_dir"].glob("*.md"))[0].read_text(encoding="utf-8")
    assert "status: pending" in fb
    assert not sf._ledger_path().exists()
