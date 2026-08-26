"""sns_publish 단위 테스트 — 05 리뷰 원고 직접 발행(상태: 리뷰완료 → 발행) 검증

실행: python3 -m pytest orchestrator/test_sns_publish.py -v
"""
from datetime import datetime, timedelta

import pytest

from orchestrator import run as run_mod
from orchestrator import sns_publish as sp
from orchestrator import state as store
from orchestrator.obsidian_state import KST


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    (tmp_path / sp.REVIEW_WAIT_DEFAULT).mkdir(parents=True)
    (tmp_path / sp.REVIEW_WAIT_DEFAULT).parent.joinpath("완료").mkdir()
    return tmp_path


def _write(vault, name, fm_lines, body="첫 글입니다.\n\n---\n\n둘째 글입니다.",
           folder=None):
    folder = folder or sp.REVIEW_WAIT_DEFAULT
    p = vault / folder / name
    p.write_text("---\n" + "\n".join(fm_lines) + f"\n---\n\n{body}\n",
                 encoding="utf-8")
    return p


def _meta(path):
    fm, _ = sp.split_frontmatter(path.read_text(encoding="utf-8"))
    return sp.parse_meta(fm)


def _today():
    return datetime.now(KST).strftime("%Y-%m-%d")


def _past(minutes=30):
    return (datetime.now(KST) - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")


def test_iter_approved_filters_and_strips_copy_note(vault):
    _write(vault, "스레드_대상.md",
           ["주제: 대상", "채널: thread", "상태: 리뷰완료", "검수상태: 통과"])
    _write(vault, "스레드_미승인.md",
           ["주제: 미승인", "채널: thread", "상태: 리뷰대기", "검수상태: 통과"])
    _write(vault, "원고_릴스.md",
           ["주제: 릴스", "채널: reels", "상태: 리뷰완료"])
    _write(vault, "스레드_사본.md",
           ["주제: 사본", "채널: thread", "상태: 리뷰완료", "검수상태: 통과",
            "content_id: DG-2026-0001"],
           body="> 열람용 사본입니다 (원본 카드 DG-2026-0001).\n> 안내 둘째 줄.\n\n진짜 본문.")
    items = sp.iter_approved()
    names = sorted(i["path"].name for i in items)
    assert names == ["스레드_대상.md", "스레드_사본.md"]
    copy = next(i for i in items if i["path"].name == "스레드_사본.md")
    assert copy["body"] == "진짜 본문."  # 안내 인용구는 발행 본문에서 제외


def test_review_gate_holds_unreviewed(vault):
    p = _write(vault, "스레드_미검수.md",
               ["주제: 미검수", "채널: thread", "상태: 리뷰완료", "검수상태: 미검수",
                f"발행시간: {_past()}"])
    counts = sp.run()
    assert counts == {"published": 0, "waiting": 0, "held": 1, "failed": 0}
    assert _meta(p)["상태"] == sp.HOLD_STATE


def test_empty_time_stamps_default_schedule(vault, monkeypatch):
    monkeypatch.setattr(run_mod, "DEFAULT_PUBLISH_TIME", "21:00")
    p = _write(vault, "스레드_예약.md",
               ["주제: 예약", "채널: thread", "상태: 리뷰완료", "검수상태: 통과",
                f"생성일: {_today()}", "발행시간:"])
    counts = sp.run()
    assert counts["waiting"] == 1 and counts["published"] == 0
    meta = _meta(p)
    assert meta["상태"] == sp.TRIGGER_STATE       # 승인 유지, 예약만 걸림
    assert meta["발행시간"].endswith("21:00")


def test_stale_approval_without_time_holds(vault, monkeypatch):
    monkeypatch.setattr(run_mod, "DEFAULT_PUBLISH_TIME", "21:00")
    p = _write(vault, "스레드_옛백로그.md",
               ["주제: 옛것", "채널: thread", "상태: 리뷰완료", "검수상태: 통과",
                "생성일: 2026-04-01", "발행시간:"])
    counts = sp.run()
    assert counts["held"] == 1
    assert _meta(p)["상태"] == sp.HOLD_STATE


def test_long_past_schedule_holds(vault):
    p = _write(vault, "스레드_오래된예약.md",
               ["주제: 오래된 예약", "채널: thread", "상태: 리뷰완료", "검수상태: 통과",
                "발행시간: 2026-04-27T21:00:00"])
    counts = sp.run()
    assert counts["held"] == 1
    assert _meta(p)["상태"] == sp.HOLD_STATE


def test_publish_success_moves_to_done(vault, monkeypatch):
    from orchestrator import publish
    sent = {}
    monkeypatch.setattr(publish, "available", lambda: True)
    def fake_chain(posts, done_ids=None, on_progress=None):
        sent["posts"] = posts
        return ["m1", "m2"], "https://threads.net/@x/post/1"
    monkeypatch.setattr(publish, "publish_chain", fake_chain)

    p = _write(vault, "스레드_발행.md",
               ["주제: 발행", "채널: thread", "상태: 리뷰완료", "검수상태: 통과",
                f"발행시간: {_past()}"],
               folder=str((vault / sp.REVIEW_WAIT_DEFAULT).parent.relative_to(vault) / "완료"))
    counts = sp.run()
    assert counts["published"] == 1
    assert not p.exists()  # 64 발행완료로 이동
    dest = vault / sp.PUBLISHED_DIR_DEFAULT / "스레드_발행.md"
    assert dest.exists()
    meta = _meta(dest)
    assert meta["상태"] == sp.DONE_STATE
    assert meta["발행링크"] == "https://threads.net/@x/post/1"
    assert meta["thread_id"] == "m1"  # 주간 성과 수집(threads_insights)용
    assert len(sent["posts"]) == 2  # '---' 구분 스레드 분할

    # 발행 축적(3단계): 라이브러리 복사 + 월별 발행 기록 + 발행 캘린더
    lib_copies = list((vault / sp.LIBRARY_DIR_DEFAULT).rglob("스레드_발행.md"))
    assert len(lib_copies) == 1
    perf = list((vault / sp.PERF_DIR_DEFAULT).glob("* 발행 기록.md"))
    assert len(perf) == 1
    log = perf[0].read_text(encoding="utf-8")
    assert "스레드_발행.md" in log and "글 수: 2개" in log and "Threads" in log
    cal = list((vault / sp.CALENDAR_DIR_DEFAULT).glob("* 발행 현황.md"))
    assert len(cal) == 1
    assert "[[스레드_발행]]" in cal[0].read_text(encoding="utf-8")


def test_copy_publish_syncs_original_card(vault, monkeypatch):
    from orchestrator import publish
    monkeypatch.setattr(publish, "available", lambda: True)
    monkeypatch.setattr(publish, "publish_chain",
                        lambda posts, done_ids=None, on_progress=None:
                        (["m1"], "https://threads.net/@x/post/2"))
    pid = store.create_card("사본 주제", stage="approval", status="needs_human",
                            format="thread")
    cid = store.query_cards(stage="approval")[0]["content_id"]
    _write(vault, "스레드_사본발행.md",
           ["주제: 사본 주제", "채널: thread", "상태: 리뷰완료", "검수상태: 통과",
            f"content_id: {cid}", f"발행시간: {_past()}"])
    counts = sp.run()
    assert counts["published"] == 1
    card = store.query_cards(stage="published")[0]
    assert card["status"] == "done"
    assert card["published_url"] == "https://threads.net/@x/post/2"


def test_copy_of_already_published_card_not_republished(vault, monkeypatch):
    from orchestrator import publish
    called = {"n": 0}
    monkeypatch.setattr(publish, "available", lambda: True)
    monkeypatch.setattr(publish, "publish_chain",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or ([], ""))
    pid = store.create_card("이미 발행", stage="published", status="done",
                            format="thread")
    store.update_card(pid, published_url="https://threads.net/@x/old")
    cid = store.query_cards(stage="published")[0]["content_id"]
    _write(vault, "스레드_중복방지.md",
           ["주제: 이미 발행", "채널: thread", "상태: 리뷰완료", "검수상태: 통과",
            f"content_id: {cid}", f"발행시간: {_past()}"])
    counts = sp.run()
    assert counts["published"] == 1 and called["n"] == 0  # 재발행 없이 정리만
    dest = vault / sp.PUBLISHED_DIR_DEFAULT / "스레드_중복방지.md"
    assert _meta(dest)["발행링크"] == "https://threads.net/@x/old"


def test_publish_error_keeps_progress_for_resume(vault, monkeypatch):
    from orchestrator import publish
    monkeypatch.setattr(publish, "available", lambda: True)
    def boom(posts, done_ids=None, on_progress=None):
        on_progress(["m1"])  # 첫 글은 나갔고
        raise RuntimeError("컨테이너 생성 실패 [2]")
    monkeypatch.setattr(publish, "publish_chain", boom)
    p = _write(vault, "스레드_부분실패.md",
               ["주제: 부분 실패", "채널: thread", "상태: 리뷰완료", "검수상태: 통과",
                f"발행시간: {_past()}"])
    counts = sp.run()
    assert counts["failed"] == 1
    meta = _meta(p)
    assert meta["상태"] == sp.ERROR_STATE
    assert meta["발행진행"] == "m1"  # 리뷰완료로 되돌리면 2번 글부터 재개


def test_max_per_run_caps_publishing(vault, monkeypatch):
    from orchestrator import publish
    monkeypatch.setattr(publish, "available", lambda: True)
    monkeypatch.setattr(publish, "publish_chain",
                        lambda *a, **k: (["m"], "https://t/1"))
    monkeypatch.setattr(sp, "MAX_PER_RUN", 1)
    for i in range(2):
        _write(vault, f"스레드_한도{i}.md",
               ["주제: 한도", "채널: thread", "상태: 리뷰완료", "검수상태: 통과",
                f"발행시간: {_past()}"])
    counts = sp.run()
    assert counts["published"] == 1 and counts["waiting"] == 1


def test_legacy_pipeline_cards_adopted(vault):
    # yt_research 사이트가 옛 vault/파이프라인/활성에 만든 카드는 다음 실행에 입양된다.
    from orchestrator import obsidian_state as st
    legacy = vault / st.LEGACY_PIPELINE_BASE / "활성"
    legacy.mkdir(parents=True)
    (legacy / "원고_스레드_기타_옛경로_DG-2026-0001.md").write_text(
        "---\ntopic: 옛 경로 카드\ncontent_id: DG-2026-0001\nstage: intake\n"
        "status: queued\n---\n", encoding="utf-8")
    cards = store.query_cards(stage="intake")  # require_backend → 입양
    assert [c["content_id"] for c in cards] == ["DG-2026-0001"]
    assert (st._active_dir() / "원고_스레드_기타_옛경로_DG-2026-0001.md").exists()
    assert not (vault / st.LEGACY_PIPELINE_BASE).exists()  # 빈 옛 폴더는 정리


def test_newsletter_without_stibee_holds(vault, monkeypatch):
    from orchestrator import stibee
    monkeypatch.setattr(stibee, "available", lambda: False)
    p = _write(vault, "원고_뉴스레터_보류.md",
               ["주제: 뉴스레터", "채널: newsletter", "상태: 리뷰완료", "검수상태: 통과",
                f"발행시간: {_past()}"])
    counts = sp.run()
    assert counts["failed"] == 1
    assert _meta(p)["상태"] == sp.HOLD_STATE
