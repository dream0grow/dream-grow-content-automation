"""split_posts 회귀 테스트 — 장문 문단이 잘리지 않고 문장 단위로 이월되는지"""
from orchestrator.publish import POST_CHAR_LIMIT, split_posts


def test_separator_based_split():
    posts = split_posts("첫 글입니다.\n---\n둘째 글입니다.\n---\n셋째 글입니다.")
    assert posts == ["첫 글입니다.", "둘째 글입니다.", "셋째 글입니다."]


def test_long_paragraph_no_content_loss():
    """500자 넘는 문단도 내용이 유실되지 않아야 한다 (감사 A5)."""
    sentences = [f"이것은 {i}번째 문장이고 교실에서 아이들과 나눈 이야기입니다." for i in range(30)]
    para = " ".join(sentences)          # 약 900자 단일 문단
    posts = split_posts(para)
    assert len(posts) >= 2
    assert all(len(p) <= POST_CHAR_LIMIT for p in posts)
    rejoined = " ".join(posts)
    for i in range(30):                  # 모든 문장이 어딘가에 살아 있어야 함
        assert f"{i}번째 문장" in rejoined


def test_short_draft_single_post():
    assert split_posts("짧은 글") == ["짧은 글"]
