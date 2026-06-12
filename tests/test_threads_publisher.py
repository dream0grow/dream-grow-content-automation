from packages.integrations.threads import split_thread_posts


def test_split_by_separator():
    body = "1번째 글\n---\n1/\n2번째 글\n---\n2/\n3번째 글"
    posts = split_thread_posts(body)
    assert posts == ["1번째 글", "2번째 글", "3번째 글"]


def test_split_strips_number_prefix():
    body = "[1/3] 첫 글\n---\n[2/3] 두 번째\n---\n[3/3] 세 번째"
    posts = split_thread_posts(body)
    assert posts == ["첫 글", "두 번째", "세 번째"]


def test_single_post():
    body = "단일 글입니다."
    assert split_thread_posts(body) == ["단일 글입니다."]
