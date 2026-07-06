"""obsidian_state 단위 테스트 — 노션 없이 카드 상태 머신이 도는지 검증

실행: python3 -m pytest orchestrator/test_obsidian_state.py -v
"""
import importlib

import pytest

from orchestrator import obsidian_state as st


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    return tmp_path


def test_card_lifecycle(vault):
    # 생성 → 채번 → 조회 → 갱신 → 섹션의 전체 수명주기
    pid = st.create_card("아이가 숙제를 미룰 때", audience="초등 저학년 학부모")
    assert "DG-" in pid and pid.endswith(".md")

    cards = st.query_cards(stage="intake", status="queued")
    assert len(cards) == 1
    card = cards[0]
    assert card["topic"] == "아이가 숙제를 미룰 때"
    assert card["audience"] == "초등 저학년 학부모"
    assert card["content_id"].endswith("-0001")
    assert st.next_content_id().endswith("-0002")     # 채번 증가

    st.update_card(pid, stage="research", status="running",
                   manus_task_ids="t1,t2", last_error="")
    assert st.query_cards(stage="intake") == []
    updated = st.query_cards(stage="research", status="running")[0]
    assert updated["manus_task_ids"] == "t1,t2"

    with pytest.raises(ValueError):
        st.update_card(pid, 없는필드="x")


def test_sections_latest_wins(vault):
    pid = st.create_card("주제")
    st.append_section(pid, "✍️ 초안 (thread)", "첫 번째 초안")
    st.append_formatted_section(pid, "📐 평가표 점검", "| 점수 | 90 |")
    st.append_section(pid, "✍️ 초안 (thread)", "두 번째 초안")

    assert "두 번째 초안" in st.read_latest_section(pid, "✍️ 초안")
    assert "첫 번째 초안" not in st.read_latest_section(pid, "✍️ 초안")
    assert "90" in st.read_latest_section(pid, "📐 평가표")
    assert st.read_latest_section(pid, "🔍 리서치") == ""
    assert "첫 번째 초안" in st.read_sections(pid)     # 전체 이력은 보존


def test_approval_gate_query(vault):
    """발행 승인 게이트: 사람이 frontmatter만 바꾸면 디스패치에 걸린다."""
    pid = st.create_card("승인 대기 글")
    st.update_card(pid, stage="approval", status="needs_human")
    assert st.query_cards(stage="approval", approval_status="approved") == []
    # 사람이 옵시디언/대시보드에서 approval_status: approved 입력한 상황
    st.update_card(pid, approval_status="approved")
    assert len(st.query_cards(stage="approval", approval_status="approved")) == 1


def test_notify_writes_review_queue(vault, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    pid = st.create_card("알림 테스트")
    st.notify(pid, "발행 승인 대기")
    queue = (vault / "_system/review_queue.md").read_text(encoding="utf-8")
    assert "발행 승인 대기" in queue and "알림 테스트" in queue


def test_state_facade_switch(vault, monkeypatch):
    monkeypatch.setenv("DG_STATE_BACKEND", "obsidian")
    from orchestrator import state
    importlib.reload(state)
    assert state.BACKEND == "obsidian"
    pid = state.create_card("파사드 경유 카드")
    assert len(state.query_cards(stage="intake")) == 1
    state.require_backend()                            # 노션 키 없이 통과해야 함
    # 원복 (다른 테스트 오염 방지)
    monkeypatch.setenv("DG_STATE_BACKEND", "notion")
    importlib.reload(state)
