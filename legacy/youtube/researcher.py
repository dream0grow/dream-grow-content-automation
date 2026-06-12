"""Semantic Scholar 기반 논문 검색 + 핵심 발견 추출.

- API 키 불필요 (무료)
- 초록(abstract)만 사용, 풀 PDF 다운로드 안 함
- 결과는 raw/papers/{slug}_{date}.json 에 저장
"""
from __future__ import annotations

import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import anthropic
import requests

from . import config

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
PAPER_FIELDS = (
    "paperId,title,abstract,year,authors,citationCount,venue,"
    "externalIds,url,openAccessPdf"
)


def _slugify(text: str) -> str:
    """파일명용 slug. 한글 그대로 허용, 공백→+, 특수문자 제거."""
    cleaned = re.sub(r"[^\w가-힣+\s-]", "", text).strip()
    return re.sub(r"\s+", "+", cleaned)[:60]


def search_papers(
    query: str,
    limit: int = 10,
    min_year: int | None = None,
    min_citations: int = 0,
) -> list[dict[str, Any]]:
    """Semantic Scholar에서 논문 검색.

    Args:
        query: 영어 검색어. 한국어 주제는 호출 전에 영어로 변환 권장.
        limit: 최대 결과 수
        min_year: 최소 발행 연도 필터
        min_citations: 최소 인용 수 필터

    Returns:
        논문 dict 리스트. abstract가 있는 것만 반환.
    """
    params: dict[str, Any] = {
        "query": query,
        "limit": limit * 2,  # 필터 후 limit 맞추기 위해 여유
        "fields": PAPER_FIELDS,
    }
    if min_year:
        params["year"] = f"{min_year}-"

    headers: dict[str, str] = {}
    if config.SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = config.SEMANTIC_SCHOLAR_API_KEY

    resp = requests.get(
        SEMANTIC_SCHOLAR_URL, params=params, headers=headers, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    papers = []
    for p in data.get("data", []):
        if not p.get("abstract"):
            continue
        if (p.get("citationCount") or 0) < min_citations:
            continue
        papers.append(p)
        if len(papers) >= limit:
            break
    return papers


def translate_topic_to_english_queries(topic_ko: str) -> list[str]:
    """한국어 주제를 영어 검색 쿼리 2~3개로 변환.

    Claude를 이용해 학술 검색에 적합한 영문 쿼리를 생성한다.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": (
                    f"주제: {topic_ko}\n\n"
                    "이 주제에 대한 뇌과학/심리학/생명과학/물리학 논문을 Semantic Scholar에서 "
                    "찾기 위한 영문 학술 검색 쿼리 3개를 JSON 배열로만 응답해. "
                    "각 쿼리는 3~6단어, 학술 용어 사용. 예: "
                    '["dopamine learning motivation", "reward prediction error study", "intrinsic motivation neuroscience"]'
                ),
            }
        ],
    )
    text = msg.content[0].text.strip()
    # JSON 배열 추출
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if not match:
        return [topic_ko]
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return [topic_ko]


def extract_key_findings(papers: list[dict[str, Any]], topic: str) -> list[dict[str, Any]]:
    """논문 초록에서 시청자에게 가치 있는 핵심 발견을 Claude로 추출.

    각 논문당 1~3개의 atomized finding을 반환.
    """
    if not papers:
        return []

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    papers_text = ""
    for idx, p in enumerate(papers, 1):
        authors = ", ".join(
            a.get("name", "") for a in (p.get("authors") or [])[:3]
        )
        papers_text += (
            f"\n[논문 {idx}]\n"
            f"제목: {p.get('title')}\n"
            f"저자: {authors}\n"
            f"연도: {p.get('year')}\n"
            f"인용수: {p.get('citationCount', 0)}\n"
            f"초록: {p.get('abstract', '')[:1500]}\n"
        )

    prompt = (
        f"주제: {topic}\n\n"
        f"다음 논문 초록들을 읽고, 일반 대중이 자기계발/학습/공부/독서에 활용할 수 있는 "
        f"핵심 발견(key findings)을 추출해. 각 발견은 atomic(1개 아이디어)이어야 하고, "
        f"논문 번호를 명시해.\n\n"
        f"{papers_text}\n\n"
        f"아래 JSON 형식으로만 응답 (설명 없이):\n"
        f'[{{"paper_idx": 1, "finding": "핵심 발견 1문장", "why_matters": "왜 중요한지 1문장", '
        f'"actionable": "일반인이 적용할 수 있는 방법 1문장"}}, ...]'
    )

    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return []


def research_topic(topic_ko: str, limit_per_query: int = 5) -> dict[str, Any]:
    """주제 하나에 대해 full 리서치 실행 → raw/papers/에 저장.

    Returns:
        { "topic": str, "papers": [...], "findings": [...], "saved_path": str }
    """
    queries = translate_topic_to_english_queries(topic_ko)
    all_papers: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    current_year = date.today().year
    for q in queries:
        papers = search_papers(
            q,
            limit=limit_per_query,
            min_year=current_year - 10,
            min_citations=5,
        )
        for p in papers:
            pid = p.get("paperId")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_papers.append(p)

    # 인용수 기준 상위 정렬
    all_papers.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
    top_papers = all_papers[:10]

    findings = extract_key_findings(top_papers, topic_ko)

    result = {
        "topic": topic_ko,
        "queries": queries,
        "papers": top_papers,
        "findings": findings,
        "researched_at": datetime.now().isoformat(),
    }

    # 저장
    config.RAW_PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slugify(topic_ko)
    today = date.today().strftime("%Y%m%d")
    out_path = config.RAW_PAPERS_DIR / f"{slug}_{today}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["saved_path"] = str(out_path)
    return result


if __name__ == "__main__":
    import sys

    topic = " ".join(sys.argv[1:]) or "도파민과 학습 동기"
    print(f"리서치 시작: {topic}")
    result = research_topic(topic)
    print(f"\n논문 {len(result['papers'])}편, finding {len(result['findings'])}개 추출")
    print(f"저장: {result['saved_path']}")
    for f in result["findings"][:3]:
        print(f"- [{f.get('paper_idx')}] {f.get('finding')}")
