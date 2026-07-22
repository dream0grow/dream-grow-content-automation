"""벤치마킹 소스 인제스트 — 기사/스레드/블로그를 카드 재료로 만든다.

사용자가 "이 기사(글)로 콘텐츠 만들어줘" 할 때의 입구. 카드에 소스를 넣는 방법은 둘:
  ① frontmatter `source_url:` 에 URL — intake 때 여기서 본문을 가져와 저장한다.
  ② 카드 본문 `## 📎 소스 원문` 섹션에 글을 직접 붙여넣기 (URL 없이도 동작).

intake 단계에서 run.handle_intake가 ingest()를 호출한다:
  1. 소스 원문 확보 (URL fetch 또는 붙여넣은 섹션) → `📎 소스 원문` 섹션 저장
  2. LLM 벤치마킹 분석(후킹/구조/사실·수치+출처/드림그로우 각도) → `📎 벤치마킹 분석` 저장
  3. 카드 topic이 비어 있거나 자리표시면 분석의 suggested_topic으로 자동 발제

이후 단계는 `📎` 접두사 섹션을 함께 읽는다 — 키워드 점수화·브리프에 주입되고,
작가(run_draft_dialogue)의 첫 집필에 [벤치마킹 소스]로 들어가 구조·후킹은 배우되
사실·수치는 출처와 함께만 쓰게 한다. 네트워크가 필요한 fetch는 GitHub Actions에서 돈다.

카드 생성 CLI (로컬/Actions 어디서든):
  python3 -m orchestrator.source_ingest --url https://... --format "thread, newsletter, reels"
  python3 -m orchestrator.source_ingest --text-file 원문.md --topic "..." --format thread
"""
import argparse
import html as html_lib
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import llm, prompts
from orchestrator import state as store

# 카드 본문 섹션 이름 (read_sections_by_prefix("📎")로 함께 읽힌다)
SOURCE_SECTION = "📎 소스 원문"
ANALYSIS_SECTION = "📎 벤치마킹 분석"
SOURCE_PREFIX = "📎"

# 카드에 저장할 소스 원문 최대 길이 (LLM 주입도 이 안에서 자른다)
MAX_SOURCE_CHARS = int(os.getenv("DG_SOURCE_MAX_CHARS") or "15000")

# topic이 이 접두사로 시작하면 '자리표시'로 보고 분석의 suggested_topic으로 교체한다
PLACEHOLDER_PREFIX = "(소스"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def log(msg: str):
    print(f"[source-ingest] {msg}", flush=True)


# ---------- HTML → 텍스트 (의존성 없이 정규식으로) ----------

def _strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ",
                      fragment, flags=re.S | re.I)
    fragment = re.sub(r"<!--.*?-->", " ", fragment, flags=re.S)
    fragment = re.sub(r"<(?:br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n",
                      fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html_lib.unescape(fragment)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in fragment.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _extract_title(html: str) -> str:
    m = (re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                   html, re.I)
         or re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I))
    return html_lib.unescape(m.group(1)).strip() if m else ""


def _extract_body(html: str) -> str:
    """본문 후보를 정밀 → 포괄 순서로 찾는다."""
    patterns = [
        # 네이버 뉴스 본문
        r'<article[^>]*id=["\']dic_area["\'][^>]*>(.*?)</article>',
        r'<div[^>]*id=["\']newsct_article["\'][^>]*>(.*?)</div>\s*<',
        # 일반 기사/블로그
        r"<article[^>]*>(.*?)</article>",
        r'<div[^>]*(?:id|class)=["\'][^"\']*(?:article|content|post)[^"\']*["\'][^>]*>(.*?)</div>\s*<',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.S | re.I)
        if m:
            text = _strip_tags(m.group(1))
            if len(text) >= 200:
                return text
    body = re.search(r"<body[^>]*>(.*?)</body>", html, re.S | re.I)
    return _strip_tags(body.group(1) if body else html)


def fetch_url(url: str) -> tuple[str, str]:
    """URL → (제목, 본문 텍스트). 실패 시 예외를 올린다 (호출부가 통지/재시도)."""
    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    html = resp.text
    title, text = _extract_title(html), _extract_body(html)
    if len(text) < 200:
        raise ValueError(f"본문 추출 실패(추출 {len(text)}자): {url}")
    return title, text


# ---------- 벤치마킹 분석 ----------

def _fmt_analysis(a: dict) -> str:
    bullets = lambda items: "\n".join(f"- {x}" for x in (items or []) if str(x).strip())
    return (
        f"**소스**: {a.get('source_title', '')} ({a.get('source_type', '')})\n"
        f"**요약**: {a.get('summary', '')}\n"
        f"**제안 주제**: {a.get('suggested_topic', '')}\n\n"
        f"## 소스의 사실·수치 (출처 포함 — 이것만 인용 가능)\n{bullets(a.get('key_facts'))}\n\n"
        f"## 배울 패턴\n"
        f"- 후킹: {a.get('hook_pattern', '')}\n"
        f"- 구조: {a.get('structure_pattern', '')}\n"
        f"- 톤: {a.get('tone', '')}\n\n"
        f"## 드림그로우 각도\n{bullets(a.get('dreamgrow_angles'))}\n\n"
        f"## 주의\n{bullets(a.get('caution'))}"
    )


def analyze(source_text: str, topic: str, audience: str) -> dict:
    return llm.call_json(
        prompts.SOURCE_BENCHMARK.format(
            topic=topic or "(비어 있음 — 소스에서 발제)",
            audience=audience or "초등 저학년 학부모",
            source=source_text[:MAX_SOURCE_CHARS],
        ),
        system=prompts.get_system(),
    )


def _is_placeholder_topic(topic: str) -> bool:
    t = (topic or "").strip()
    return not t or t.startswith(PLACEHOLDER_PREFIX) or "http" in t


def ingest(card: dict) -> bool:
    """카드에 소스가 있으면 원문·분석 섹션을 채운다. 소스가 없으면 False.

    idempotent — 이미 저장된 섹션은 다시 만들지 않아, 실패 재시도(A3) 시
    URL을 다시 받거나 분석을 중복 실행하지 않는다.
    """
    page_id = card["page_id"]
    source = store.read_latest_section(page_id, SOURCE_SECTION).strip()
    url = str(card.get("source_url", "") or "").strip()
    if not source and url:
        title, text = fetch_url(url)
        source = f"출처: {url}\n제목: {title}\n\n{text}"[:MAX_SOURCE_CHARS]
        store.append_section(page_id, SOURCE_SECTION, source)
        log(f"{card.get('content_id') or page_id} 소스 수집: {title[:50]} ({len(text)}자)")
    if not source:
        return False

    if not store.read_latest_section(page_id, ANALYSIS_SECTION).strip():
        result = analyze(source, card.get("topic", ""), card.get("audience", ""))
        store.append_formatted_section(page_id, ANALYSIS_SECTION, _fmt_analysis(result))
        suggested = str(result.get("suggested_topic", "") or "").strip()
        if suggested and _is_placeholder_topic(card.get("topic", "")):
            store.update_card(page_id, topic=suggested)
            card["topic"] = suggested
            log(f"{card.get('content_id') or page_id} 주제 자동 발제: {suggested}")
    return True


# ---------- 카드 생성 CLI ----------

def create_source_card(*, url: str = "", text: str = "", topic: str = "",
                       audience: str = "", formats: str = "thread") -> str:
    """소스 기반 intake 카드를 만든다. 이후는 오케스트레이터가 자동 진행."""
    if not url and not text.strip():
        raise ValueError("--url 또는 --text-file/--stdin 중 하나는 필요합니다")
    title = topic.strip() or f"{PLACEHOLDER_PREFIX}) 벤치마킹 발제 대기"
    page_id = store.create_card(
        title, audience=audience or "초등 저학년 학부모",
        format=formats, source_url=url,
    )
    if text.strip():
        store.append_section(page_id, SOURCE_SECTION, text.strip()[:MAX_SOURCE_CHARS])
    return page_id


def main() -> None:
    ap = argparse.ArgumentParser(
        description="벤치마킹 소스(기사/스레드/블로그) 기반 intake 카드 생성")
    ap.add_argument("--url", default="", help="소스 URL (fetch는 intake 때 실행)")
    ap.add_argument("--text-file", default="", help="소스 원문 파일 (붙여넣기 대용)")
    ap.add_argument("--stdin", action="store_true", help="소스 원문을 표준입력에서 읽기")
    ap.add_argument("--topic", default="", help="카드 주제 (비우면 소스에서 자동 발제)")
    ap.add_argument("--audience", default="", help="대상 독자 (기본: 초등 저학년 학부모)")
    ap.add_argument("--format", default="thread",
                    help='형식 콤마 혼합 (예: "thread, newsletter, reels, youtube")')
    args = ap.parse_args()

    text = ""
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    elif args.stdin:
        text = sys.stdin.read()

    page_id = create_source_card(
        url=args.url, text=text, topic=args.topic,
        audience=args.audience, formats=args.format,
    )
    log(f"카드 생성: {page_id} (format: {args.format})")
    log("다음 orchestrator 실행에서 소스 수집 → 벤치마킹 분석 → 초안까지 자동 진행됩니다.")


if __name__ == "__main__":
    main()
