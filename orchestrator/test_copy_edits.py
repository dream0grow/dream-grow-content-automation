"""열람 사본 직접 수정 반영(copy_edits) 단위 테스트.

GitHub Edit·옵시디언에서 사본을 고쳤을 때 ① 카드 초안으로 반영되는지
② 문체 학습이 호출되는지 ③ 사고(내용 유실)와 재처리를 막는지 검증한다.

실행: python3 -m pytest orchestrator/test_copy_edits.py -q
"""
import pytest

from orchestrator import copy_edits, obsidian_state as st, review_copy

DRAFT = "\n\n".join(f"AI가 쓴 문단 {i}. 초등 저학년 부모를 위한 안내입니다." for i in range(12))


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("VAULT_SCRIPT_PATH", "05 리뷰/대기")
    return tmp_path


def _make_card(fmt="thread"):
    """초안까지 진행된 카드 + 사본을 만들고 (page_id, card, 사본경로)를 준다."""
    page_id = st.create_card("학원 스케줄 고민")
    card = st.query_cards()[0]
    st.append_section(page_id, f"🗄️ AI 원본 ({fmt}) - 수정 금지", DRAFT)
    st.append_section(page_id, f"✍️ 초안 ({fmt})", DRAFT)
    name = review_copy.export(card, fmt, DRAFT)
    return page_id, card, copy_edits._script_dir() / name


def _rewrite_body(path, body):
    """사람이 GitHub Edit으로 본문만 갈아끼운 상황(프론트매터는 그대로)."""
    raw = path.read_text(encoding="utf-8")
    head = raw.split("---\n", 2)[:2]
    path.write_text(f"---\n{head[1]}---\n\n{body}\n", encoding="utf-8")


def test_untouched_copy_is_noop(vault):
    _make_card()
    assert copy_edits.apply_edits() == {"unchanged": 1}


def test_human_edit_flows_into_card_and_style_learning(vault, monkeypatch):
    page_id, _, copy_path = _make_card()
    edited = DRAFT.replace("AI가 쓴", "제가 고친") + "\n\n마지막 한 줄을 덧붙였어요."
    _rewrite_body(copy_path, edited)

    calls, notes = [], []
    monkeypatch.setattr(
        "orchestrator.style_learn.learn_from_edits",
        lambda pid, ch: calls.append((pid, ch)) or 3,
    )
    monkeypatch.setattr("orchestrator.state.notify",
                        lambda pid, msg: notes.append(msg))
    assert copy_edits.apply_edits() == {"applied": 1}

    latest = st.read_latest_section(page_id, "✍️ 초안 (thread)")
    assert "제가 고친" in latest and "마지막 한 줄" in latest
    assert calls == [(page_id, "thread")]          # AI 원본과 비교해 학습 1회
    assert "문체 패턴 3개" in notes[-1]              # 결과를 폰으로 알린다

    # 지문이 갱신돼 같은 수정이 두 번 반영되지 않는다.
    assert copy_edits.apply_edits() == {"unchanged": 1}


def test_edit_without_baseline_hash_is_detected(vault, monkeypatch):
    """이 기능 이전에 만들어진 사본(draft_hash 없음)도 카드와 비교해 잡아낸다."""
    page_id, _, copy_path = _make_card()
    raw = copy_path.read_text(encoding="utf-8")
    copy_path.write_text(
        "\n".join(l for l in raw.splitlines() if not l.startswith("draft_hash:")),
        encoding="utf-8")
    _rewrite_body(copy_path, DRAFT + "\n\n사람이 덧붙인 마무리 문장입니다.")

    monkeypatch.setattr("orchestrator.style_learn.learn_from_edits", lambda *a: 1)
    assert copy_edits.apply_edits() == {"applied": 1}
    assert "사람이 덧붙인" in st.read_latest_section(page_id, "✍️ 초안 (thread)")


def test_truncated_edit_is_rejected(vault, monkeypatch):
    """실수로 본문을 날린 사본은 반영하지 않고 통지만 한다."""
    page_id, _, copy_path = _make_card()
    _rewrite_body(copy_path, "짧게 지워버림")

    monkeypatch.setattr("orchestrator.style_learn.learn_from_edits",
                        lambda *a: pytest.fail("짧은 수정본은 학습하면 안 된다"))
    assert copy_edits.apply_edits() == {"too_short": 1}
    assert "AI가 쓴 문단" in st.read_latest_section(page_id, "✍️ 초안 (thread)")
    # 재처리는 막되(지문 갱신), 보류 사유를 사본에 남긴다.
    assert "보류" in copy_path.read_text(encoding="utf-8")
    assert copy_edits.apply_edits() == {"unchanged": 1}


def test_dry_run_writes_nothing(vault, monkeypatch):
    page_id, _, copy_path = _make_card()
    _rewrite_body(copy_path, DRAFT + "\n\n사람이 덧붙인 마무리 문장입니다.")
    monkeypatch.setattr("orchestrator.style_learn.learn_from_edits",
                        lambda *a: pytest.fail("dry-run은 학습하지 않는다"))
    assert copy_edits.apply_edits(dry_run=True) == {"planned": 1}
    assert "사람이 덧붙인" not in st.read_latest_section(page_id, "✍️ 초안 (thread)")


def test_guide_note_and_comments_are_not_content(vault):
    """상단 안내 인용문·감사 주석은 본문이 아니므로 수정으로 보지 않는다."""
    _, _, copy_path = _make_card()
    raw = copy_path.read_text(encoding="utf-8")
    copy_path.write_text(raw.rstrip() + "\n\n<!-- 🔁 자동 처리 흔적 -->\n",
                         encoding="utf-8")
    assert copy_edits.apply_edits() == {"unchanged": 1}


def test_youtube_copy_is_ignored(vault):
    """유튜브 원고는 자체 핑퐁 경로가 있으니 여기서 건드리지 않는다."""
    page_id, card, _ = _make_card()
    (copy_edits._script_dir() / "원고_YT롱폼_학원.md").write_text(
        f"---\ncontent_id: {card['content_id']}\n채널: youtube\n---\n\n원고 본문\n",
        encoding="utf-8")
    assert [i["fmt"] for i in copy_edits.scan()] == ["thread"]
