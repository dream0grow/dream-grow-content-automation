"""논문 리서치 결과를 제텔카스텐 1단계 메모로 자동 적재.

- 폴더: 초생산/제텔카스텐/5. 제텔카스텐/1단계 - 메모/ (하위 분리 없음)
- 파일명: YT_{CODE}_{키워드}_{날짜}.md
- 사용자 수동 메모와는 frontmatter origin + #ai_generated 태그로만 구분
- Graph View 오염 방지: 서로 연결 없음. 사용자 승격 시에만 연결 생성
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from . import config


# 주제 키워드 → 한국십진분류 매핑 (대략적 규칙 기반)
DOMAIN_TAG_MAP = {
    "neuroscience": "#4000자연과학/4700생명과학/4780신경과학",
    "brain": "#4000자연과학/4700생명과학/4780신경과학",
    "dopamine": "#4000자연과학/4700생명과학/4780신경과학",
    "psychology": "#1000철학/1500심리학",
    "cognitive": "#1000철학/1500심리학/1580인지심리학",
    "learning": "#3000사회과학/3700교육학",
    "education": "#3000사회과학/3700교육학",
    "biology": "#4000자연과학/4700생명과학",
    "physics": "#4000자연과학/4200물리학",
    "memory": "#1000철학/1500심리학/1580인지심리학",
    "motivation": "#1000철학/1500심리학",
    "habit": "#1000철학/1500심리학",
    "sleep": "#4000자연과학/4700생명과학",
    "reading": "#3000사회과학/3700교육학",
}


def _infer_tag(topic: str, paper: dict) -> str:
    """주제/논문 정보로 한국십진분류 태그 추론."""
    text = (topic + " " + (paper.get("title") or "") + " " + (paper.get("venue") or "")).lower()
    for keyword, tag in DOMAIN_TAG_MAP.items():
        if keyword in text:
            return tag
    return "#4000자연과학"


def _extract_doi(paper: dict) -> str:
    """논문 dict에서 DOI URL 추출."""
    ext_ids = paper.get("externalIds") or {}
    doi = ext_ids.get("DOI")
    if doi:
        return f"https://doi.org/{doi}"
    return paper.get("url") or ""


def _authors_str(paper: dict) -> str:
    authors = paper.get("authors") or []
    names = [a.get("name", "") for a in authors[:3]]
    result = ", ".join(n for n in names if n)
    if len(authors) > 3:
        result += f" et al."
    year = paper.get("year")
    if year:
        result += f" ({year})"
    return result


def _slugify_for_filename(text: str) -> str:
    cleaned = re.sub(r"[^\w가-힣+\s-]", "", text).strip()
    return re.sub(r"\s+", "+", cleaned)[:50]


def create_memo(
    finding: dict[str, Any],
    paper: dict[str, Any],
    topic: str,
    channel_code: str = "SC",
    raw_json_path: str | None = None,
) -> Path:
    """단일 finding → 제텔카스텐 1단계 메모 1개 생성.

    Args:
        finding: {finding, why_matters, actionable, paper_idx}
        paper: Semantic Scholar 논문 dict
        topic: 원본 한글 주제
        channel_code: SC/DG/SM
        raw_json_path: 원본 raw/papers/... 경로

    Returns:
        생성된 메모 파일의 Path
    """
    config.ZETTELKASTEN_MEMO_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    title = finding.get("finding", "")[:80]
    slug_source = f"{topic}_{finding.get('paper_idx', '')}"
    slug = _slugify_for_filename(slug_source)
    filename = f"YT_{channel_code}_{slug}_{today}.md"
    out_path = config.ZETTELKASTEN_MEMO_DIR / filename

    # 중복 방지
    if out_path.exists():
        i = 2
        while True:
            alt = config.ZETTELKASTEN_MEMO_DIR / f"YT_{channel_code}_{slug}_{today}_{i}.md"
            if not alt.exists():
                out_path = alt
                break
            i += 1

    tag = _infer_tag(topic, paper)
    doi = _extract_doi(paper)
    authors = _authors_str(paper)

    # YAML frontmatter
    frontmatter = f"""---
title: "{title.replace('"', "'")}"
type: memo
origin: ai_generated
source_system: youtube_auto
source_channel: {channel_code.lower()}
source_video: ""
promoted: false
promoted_to: ""
promotion_score: 0.0
promotion_date: ""
promotion_reason: ""
created: {date.today().isoformat()}
tags:
  - "{tag}"
  - "#ai_generated"
  - "#youtube_research"
출처: "{doi}"
저자: "{authors}"
venue: "{paper.get('venue') or ''}"
citation_count: {paper.get('citationCount') or 0}
raw: "{raw_json_path or ''}"
topic_source: "{topic}"
---
"""

    body = f"""# {title}

## 핵심 발견
{finding.get('finding', '')}

## 왜 중요한가
{finding.get('why_matters', '')}

## 실천 가능한 적용
{finding.get('actionable', '')}

## 원 논문
- **제목**: {paper.get('title', '')}
- **저자**: {authors}
- **발행**: {paper.get('venue', '')} ({paper.get('year', '')})
- **인용수**: {paper.get('citationCount', 0)}
- **출처**: [{doi}]({doi})

## 초록 발췌
> {(paper.get('abstract') or '')[:500]}...
"""

    out_path.write_text(frontmatter + body, encoding="utf-8")
    return out_path


def create_memos_from_research(research_result: dict[str, Any], channel_code: str = "SC") -> list[Path]:
    """research_topic() 결과에서 findings 전체를 메모로 변환.

    Returns:
        생성된 메모 파일 경로 리스트
    """
    created: list[Path] = []
    papers = research_result.get("papers") or []
    findings = research_result.get("findings") or []
    topic = research_result.get("topic", "")
    raw_path = research_result.get("saved_path")

    for finding in findings:
        idx = finding.get("paper_idx", 1) - 1
        if 0 <= idx < len(papers):
            paper = papers[idx]
        elif papers:
            paper = papers[0]
        else:
            continue
        path = create_memo(finding, paper, topic, channel_code, raw_path)
        created.append(path)

    return created


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m youtube.zettelkasten_writer <raw_papers_json>")
        sys.exit(1)

    research = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    paths = create_memos_from_research(research)
    for p in paths:
        print(f"생성: {p}")
