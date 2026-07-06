#!/usr/bin/env python3
"""네이버 블로그 글 스크랩 → 볼트 raw/블로그글/ (로컬 실행 전용)

본인 블로그(공개 글)를 문체 벤치마크로 볼트에 넣기 위한 도구.
클라우드 세션에서는 네이버가 차단되므로 **맥북에서 실행**한다.

사용:
    python3 tools/naver_blog_scrape.py l0126j --count 10
    python3 tools/naver_blog_scrape.py l0126j --count 10 --out "vault/raw/블로그글"

주의: 본인 블로그에만 사용할 것. 결과 md의 frontmatter에 원본 URL이 남는다.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch_post_list(blog_id: str, count: int) -> list[dict]:
    """모바일 블로그 API에서 최신 글 목록을 가져온다."""
    url = f"https://m.blog.naver.com/api/blogs/{blog_id}/post-list"
    resp = requests.get(url, params={"categoryNo": 0, "itemCount": count, "page": 1},
                        headers={**UA, "Referer": f"https://m.blog.naver.com/{blog_id}"},
                        timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = (data.get("result") or {}).get("items") or []
    posts = []
    for it in items:
        log_no = str(it.get("logNo") or "").strip()
        title = html.unescape(str(it.get("titleWithInspectMessage")
                                  or it.get("title") or log_no))
        if log_no:
            posts.append({"logNo": log_no, "title": title.strip(),
                          "date": str(it.get("addDate") or "")[:10]})
    return posts


def fetch_post_body(blog_id: str, log_no: str) -> str:
    """글 본문 텍스트 추출 (스마트에디터 se-main-container 우선)."""
    url = f"https://m.blog.naver.com/{blog_id}/{log_no}"
    resp = requests.get(url, headers=UA, timeout=20)
    resp.raise_for_status()
    page = resp.text
    m = re.search(r'<div[^>]*class="[^"]*se-main-container[^"]*"[^>]*>(.*?)</div>\s*'
                  r'(?:<div[^>]*class="[^"]*(?:post_btn|se_component_wrap_footer)',
                  page, re.DOTALL)
    chunk = m.group(1) if m else page
    # 문단 태그를 줄바꿈으로 바꾸고 나머지 태그 제거
    chunk = re.sub(r"</p>|<br\s*/?>", "\n", chunk)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", chunk, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [ln.strip() for ln in text.splitlines()]
    body = "\n".join(ln for ln in lines if ln)
    # 상단 내비게이션 잔재 제거를 위한 휴리스틱: 본문은 보통 100자 이상
    return body.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="네이버 블로그 → 볼트 문체 벤치마크")
    ap.add_argument("blog_id", help="블로그 ID (예: l0126j)")
    ap.add_argument("--count", type=int, default=10, help="가져올 글 수")
    ap.add_argument("--out", default="vault/raw/블로그글", help="저장 폴더")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        posts = fetch_post_list(args.blog_id, args.count)
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"목록 조회 실패: {e}\n(네이버 API 형식이 바뀌었을 수 있음 — 글을 수동 복사해 넣어도 됩니다)",
              file=sys.stderr)
        sys.exit(1)
    if not posts:
        print("글을 찾지 못함 — 블로그 ID를 확인하세요", file=sys.stderr)
        sys.exit(1)

    saved = 0
    for p in posts:
        try:
            body = fetch_post_body(args.blog_id, p["logNo"])
        except requests.RequestException as e:
            print(f"[실패] {p['title']}: {e}")
            continue
        if len(body) < 100:
            print(f"[생략] {p['title']}: 본문 추출 실패(짧음)")
            continue
        safe = re.sub(r'[\\/:*?"<>|#^\[\]]', " ", p["title"]).strip()[:60] or p["logNo"]
        dest = out_dir / f"{safe}.md"
        dest.write_text(
            f"---\ntitle: {p['title']}\nsource_url: https://blog.naver.com/{args.blog_id}/{p['logNo']}\n"
            f"date: {p['date']}\nauthor: 이한결\n용도: 문체 벤치마크\n---\n\n{body}\n",
            encoding="utf-8")
        saved += 1
        print(f"[저장] {dest.name} ({len(body)}자)")

    print(f"\n완료: {saved}건 → {out_dir}")
    print("다음: git add·commit·push 하면 파이프라인이 문체 벤치마크로 사용합니다.")


if __name__ == "__main__":
    main()
