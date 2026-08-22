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


def test_read_sections_by_prefix_filters(vault):
    """B3: 접두사에 맞는 섹션만 골라 읽고, 무거운 누적 초안은 제외한다."""
    pid = st.create_card("주제")
    st.append_formatted_section(pid, "🔍 리서치: 감정", "부모의 언어")
    st.append_formatted_section(pid, "🏷️ 키워드 후보 (승인 필요)", "키워드 표")
    st.append_section(pid, "✍️ 초안 (thread)", "아주 긴 초안 본문")
    st.append_formatted_section(pid, "✅ 교육윤리 검수 (thread)", "검수 결과")

    picked = st.read_sections_by_prefix(pid, "🔍 리서치", "🏷️ 키워드")
    assert "부모의 언어" in picked
    assert "키워드 표" in picked
    assert "아주 긴 초안 본문" not in picked   # 초안은 제외돼 토큰 절감
    assert "검수 결과" not in picked
    # 접두사 없으면 전체
    assert "아주 긴 초안 본문" in st.read_sections_by_prefix(pid)


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
    assert "발행 승인 대기" in queue and "알림+테스트" in queue


def test_card_filename_follows_naming_rule(vault):
    """SNS `03 파일명 규칙`: 원고_형식_카테고리_키워드+키워드_DG-ID.md"""
    name = st.card_filename("DG-2026-0042", "수학 문제집 앞에서 모르겠다며 미루는 아이")
    assert name == "원고_스레드_수학_수학+문제집+앞에서_DG-2026-0042.md"
    # 형식은 format 필드를 따르고, 혼합(comma)이면 첫 형식
    assert st.card_filename("DG-2026-0001", "책 읽기 싫어하는 아이",
                            "newsletter").startswith("원고_뉴스레터_독서_")
    assert st.card_filename("DG-2026-0001", "주제", "youtube,thread").startswith("원고_YT롱폼_")
    # 큐시트(시스템 결재) 카드는 별도 패턴
    assert st.card_filename("DG-2026-0002", "[큐시트] 프롬프트 개선안 DG-2026-0002") \
        == "큐시트_프롬프트개선_DG-2026-0002.md"


def test_topic_category_fallback(vault):
    assert st.topic_category("유튜브 그만 보라고 하면 짜증내는 아이") == "미디어"
    assert st.topic_category("전혀 무관한 주제") == "기타"


def test_create_card_new_naming_keeps_pipeline_working(vault):
    """새 파일명에서도 채번·ID 검색(피드백 라우팅)이 돈다."""
    pid = st.create_card("받아쓰기 시험만 보면 우는 아이", format="thread")
    assert pid.endswith("_DG-2026-0001.md")
    assert st.next_content_id().endswith("-0002")      # 끝에 있는 ID로도 채번
    card = st.query_cards(stage="intake")[0]
    assert card["format"] == "thread"                  # format이 frontmatter에 반영


def test_format_aliases_normalized_on_read(vault):
    """사람이 `threads`처럼 변형으로 적어도 카드 읽기에서 정식 값으로 정규화된다.

    DG-2026-0033이 `format: threads`로 발행 분기에서 빠져 멈춘 실사례 회귀 테스트.
    """
    pid = st.create_card("그림일기 숙제 앞에서 멍한 아이", format="thread")
    read = lambda: st._card_from_file(st._resolve(pid))["format"]
    st.update_card(pid, format="threads")
    assert read() == "thread"
    st.update_card(pid, format="Threads, 뉴스레터")
    assert read() == "thread, newsletter"
    st.update_card(pid, format="유튜브")                # 유튜브 별칭은 그대로 통과
    from orchestrator import youtube_script
    assert youtube_script.wants_youtube(read())


def test_read_final_draft_prefers_2nd_draft(vault):
    """발행 원고는 '✍️ 2차안'이 있으면 2차안이다.

    DG-2026-0033이 사람이 고친 2차안을 두고 1차 초안으로 발행된 실사례 회귀 테스트.
    """
    pid = st.create_card("그림일기 주제", format="thread")
    st.append_section(pid, "✍️ 초안 (thread)", "1차 초안 본문")
    assert st.read_final_draft(pid, "thread") == "1차 초안 본문"
    st.append_section(pid, "✍️ 2차안 (thread)", "2차안 본문 (사람 수정본)")
    assert st.read_final_draft(pid, "thread") == "2차안 본문 (사람 수정본)"


def test_state_facade_is_obsidian(vault):
    """파사드는 옵시디언 볼트 백엔드 하나로 고정됐다 (노션 철수)."""
    from orchestrator import state
    pid = state.create_card("파사드 경유 카드")
    assert pid.endswith(".md")
    assert len(state.query_cards(stage="intake")) == 1
    state.require_backend()                            # 외부 키 없이 통과해야 함
    # 파사드가 옵시디언 공개 함수를 그대로 노출하는지
    assert hasattr(state, "read_sections_by_prefix")
