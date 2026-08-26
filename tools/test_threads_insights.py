"""threads_insights 클라우드 이식 테스트 — 경로·백필·텔레그램 요약 검증

실행: python3 -m pytest tools/test_threads_insights.py -v
"""
import importlib
from pathlib import Path

import pytest


@pytest.fixture()
def ti(tmp_path, monkeypatch):
    """DG_VAULT_ROOT를 임시 볼트로 바꿔 모듈 경로를 재계산한다."""
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    import threads_insights as m
    importlib.reload(m)
    Path(m.PUBLISHED_DIR).mkdir(parents=True)
    Path(m.REPORT_DIR).mkdir(parents=True)
    yield m
    monkeypatch.delenv("DG_VAULT_ROOT")
    importlib.reload(m)  # 다른 테스트가 실제 경로 상수를 보도록 복원


def test_paths_follow_vault_root(ti, tmp_path):
    assert ti.SNS_SYSTEM.startswith(str(tmp_path))  # 맥 하드코딩 제거 확인
    assert "64 발행완료" in ti.PUBLISHED_DIR


def test_backfill_thread_ids_from_publish_log(ti):
    (Path(ti.PUBLISHED_DIR) / "스레드_백필.md").write_text(
        "---\n주제: 백필\n카테고리: 수학\n채널: thread\n---\n\n본문\n",
        encoding="utf-8")
    (Path(ti.REPORT_DIR) / "2026-08 발행 기록.md").write_text(
        "# 2026-08 발행 기록\n\n## 2026-08-26 21:00 - 스레드_백필.md\n"
        "- 글 수: 5개\n- 플랫폼: Threads\n- 첫 글 ID: 18012345678901234\n",
        encoding="utf-8")
    assert ti.backfill_thread_ids() == 1
    fm = ti.parse_frontmatter(str(Path(ti.PUBLISHED_DIR) / "스레드_백필.md"))
    assert fm["thread_id"] == "18012345678901234"
    assert ti.backfill_thread_ids() == 0  # 재실행 무해(idempotent)


def test_find_published_files_picks_backfilled(ti):
    (Path(ti.PUBLISHED_DIR) / "스레드_수집대상.md").write_text(
        "---\n주제: 수집\n카테고리: 감정\nthread_id: 111\n발행시간: 2026-08-25 21:00\n"
        "---\n\n본문\n", encoding="utf-8")
    (Path(ti.PUBLISHED_DIR) / "스레드_ID없음.md").write_text(
        "---\n주제: 없음\n---\n\n본문\n", encoding="utf-8")
    files = ti.find_published_files()
    assert [f["_filename"] for f in files] == ["스레드_수집대상.md"]
    assert files[0]["_category"] == "감정"
    assert files[0]["_hour"] == 21


def test_telegram_summary_message(ti, monkeypatch):
    sent = []
    from vault_pipeline import telegram_notify
    monkeypatch.setattr(telegram_notify, "send",
                        lambda msg, html=False: sent.append(msg) or True)
    published = [
        {"_filename": "a.md", "주제": "1등 글", "조회수": "12,345"},
        {"_filename": "b.md", "주제": "2등 글", "조회수": "99"},
    ]
    ok = ti.send_telegram_summary(
        str(Path(ti.REPORT_DIR) / "주간성과_2026-08-31.md"),
        published, {"views": 150000, "followers_count": 34000})
    assert ok and len(sent) == 1
    msg = sent[0]
    assert "7일 조회수 150,000" in msg and "팔로워 34,000" in msg
    assert "1등 글" in msg and "12,345" in msg
    assert "https://github.com/" in msg and "2026-08-31.md" in msg  # 리포트 링크(한글은 URL 인코딩)
