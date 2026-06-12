"""스레드 본문 <-> 개별 포스트 분할/결합

레거시 threads_publisher.py parse_thread_file의 본문 분할 로직 포팅.
생성기 출력은 `1/` 형식, 레거시 파일은 `[1/7]` 형식 프리픽스를 쓰므로 둘 다 처리.
"""
import re

# [1/7], 1/7, 1/ 등의 번호 프리픽스 제거
_PREFIX_RE = re.compile(r"^\[?\d+/\d*\]?\s*")


def split_posts(body: str) -> list[str]:
    """`---` 구분자로 스레드 본문을 개별 포스트로 분할한다."""
    body = body.strip()
    if not body:
        return []
    if "\n---\n" in body or body.startswith("---\n"):
        parts = re.split(r"\n---\n|^---\n", body)
    else:
        parts = [body]
    posts = []
    for part in parts:
        text = _PREFIX_RE.sub("", part.strip())
        if text:
            posts.append(text)
    return posts


def join_posts(posts: list[str]) -> str:
    return "\n---\n".join(p.strip() for p in posts if p.strip())
