from app.services.splitter import join_posts, split_posts


def test_split_basic():
    body = "첫 글\n---\n1/\n두 번째 글\n---\n2/\n세 번째 글"
    posts = split_posts(body)
    assert posts == ["첫 글", "두 번째 글", "세 번째 글"]


def test_split_bracket_prefix():
    body = "[1/3] 첫 글\n---\n[2/3] 두 번째 글\n---\n[3/3] 세 번째 글"
    posts = split_posts(body)
    assert posts == ["첫 글", "두 번째 글", "세 번째 글"]


def test_split_single_post():
    assert split_posts("단일 글입니다") == ["단일 글입니다"]


def test_split_empty():
    assert split_posts("") == []
    assert split_posts("   \n  ") == []


def test_roundtrip():
    posts = ["첫 글", "두 번째 글"]
    assert split_posts(join_posts(posts)) == posts
