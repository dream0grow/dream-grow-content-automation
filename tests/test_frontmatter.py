from packages.shared.frontmatter import (
    Frontmatter, merge_frontmatter, split_frontmatter,
)


def test_roundtrip():
    raw = (
        "---\n"
        "주제: 초등 2학년 수학 자존감\n"
        "카테고리: 수학\n"
        "채널: thread\n"
        "상태: 리뷰대기\n"
        "---\n"
        "본문 내용입니다.\n"
    )
    fm, body = split_frontmatter(raw)
    assert fm.topic == "초등 2학년 수학 자존감"
    assert fm.category == "수학"
    assert fm.status == "리뷰대기"
    assert "본문 내용" in body


def test_merge_updates_field():
    raw = (
        "---\n"
        "주제: 원래 주제\n"
        "채널: thread\n"
        "발행시간: 19:00\n"
        "---\n"
        "본문\n"
    )
    out = merge_frontmatter(raw, **{"상태": "발행완료"})
    fm, _ = split_frontmatter(out)
    assert fm.status == "발행완료"
    assert fm.topic == "원래 주제"


def test_block_render():
    fm = Frontmatter(**{"주제": "테스트", "채널": "thread"})
    block = fm.to_block()
    assert "주제: 테스트" in block
    assert "채널: thread" in block
