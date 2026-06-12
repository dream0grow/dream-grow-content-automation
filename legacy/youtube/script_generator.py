"""Science Channel 롱폼 원고 자동 생성 (Honcho 미사용).

- 논문 리서치 결과를 근거로 10분 분량 스크립트 생성
- 상황/고민/욕구/계획 프레임 적용 (기존 Google Sheets 기획 프레임워크)
- 썸네일 문구 4종 (기대/증거/의문/공감) 생성
- [TTS] / [짤:분류] / [효과음:종류] / [스톡:키워드] 태그를 스크립트에 삽입
- feedback_db의 learned_patterns를 system prompt에 주입
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import anthropic

from . import config, feedback_db
from .researcher import research_topic
from .zettelkasten_writer import create_memos_from_research


SYSTEM_PROMPT = """당신은 과학/심리학 논문 기반 롱폼 YouTube 스크립트 전문 작가입니다.

## 채널 정체성
- 뇌과학/생명과학/물리학/심리학 논문을 근거로 자기계발/학습/공부/독서 인사이트를 전달
- 타겟: 일상 속 어려움(공부 효율, 집중력, 습관, 수면, 동기부여, 인간관계)을 과학으로 이해하고 해결하고 싶은 일반 대중
- 톤: 전문가가 친근하게 설명하는 구어체. 말로 들었을 때 자연스러운 흐름.
- 차별점: "A가 아니라 B이다" 논리 구조 + 논문 근거 + 즉시 실천 가능한 방법

## 분량
- 본문 TTS 대본 기준 한국어 기준 약 2000~2800자 (약 10분 영상)

## 필수 구조 (기존 운영 프레임워크 반영)
1. **인트로** (30초~1분): 훅 + 문제 제기 + 영상 약속
2. **현상** (1~2분): 시청자가 겪는 상황 공감
3. **고민** (1~2분): 왜 이 문제가 생기는가 - 논문 근거 1
4. **욕구** (2~3분): 시청자가 진짜 원하는 것 - 논문 근거 2
5. **계획** (3~4분): 구체적 해결법 단계별 - 논문 근거 3 + 실천법
6. **아웃트로** (30초~1분): 요약 + 감성 마무리 + CTA(구독, 다음 영상)

## 태그 삽입 (영상 제작 자동화용 - 필수)
대본 본문에 다음 태그를 적절히 삽입한다:
- `[TTS] {문장}` : 내레이션으로 읽을 문장
- `[짤:분류]` : 짤/GIF 삽입 (분류: 놀람, 공감, 웃김, 생각, 성공, 실패)
- `[효과음:종류]` : 효과음 (종류: 전환, 강조, 반전, 성공, whoosh)
- `[스톡:영문키워드]` : 스톡영상 B-roll (키워드는 영문)
- `[자막:큰글씨]` : 강조 자막
- `[인포:내용요약]` : 인포그래픽 슬라이드

각 섹션당 최소 1개의 [짤] 또는 [스톡], 1개의 [효과음], 1개의 [자막]을 포함.

## 금지
- 이모지/이모티콘 사용 금지
- 출처 없는 % 수치 사용 금지 (논문에서 나온 숫자만)
- Dream_Grow 고유 문구("아이와 부모의 꿈을 키웁니다" 등) 사용 금지
- 개인 경험/교실 에피소드 금지 (이 채널은 익명 AI 채널)

## 출력 형식 (엄격히 준수)

```
## 메타데이터
제목 후보 3개:
1. ...
2. ...
3. ...

최종 선택 제목: ...

썸네일 문구 4종:
- 기대: ...
- 증거: ...
- 의문: ...
- 공감: ...

최종 선택 썸네일 문구: ...

시청자 분석:
- 현상: (시청자가 겪는 상황 1문장)
- 고민: (페인포인트 1문장)
- 욕구: (원하는 결과 1문장)
- 계획: (영상이 제공할 해결책 1문장)

카테고리: (학습/자기계발/독서/습관/심리 중 1개)
태그: 쉼표로 구분된 5~8개

---

## 본문 스크립트

### 인트로

[TTS] ...
[짤:...] [효과음:...] ...

### 현상

...

### 고민

...

### 욕구

...

### 계획

...

### 아웃트로

...

---

## YouTube 설명란 문구
(3~5문단, 논문 출처 포함)
```
"""


def generate_script(
    topic: str,
    research: dict[str, Any],
    user_title: str | None = None,
    user_hook: str | None = None,
) -> str:
    """논문 리서치 결과를 바탕으로 스크립트 본문을 생성.

    Args:
        topic: 주제 (한글)
        research: researcher.research_topic() 결과
        user_title: 사용자가 Sheets에서 미리 제공한 제목 (선택)
        user_hook: 사용자가 제공한 도입부/훅 (선택)

    Returns:
        전체 스크립트 markdown 문자열
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    findings_text = ""
    for i, f in enumerate(research.get("findings") or [], 1):
        findings_text += (
            f"\n[Finding {i}] (논문 #{f.get('paper_idx')})\n"
            f"- 발견: {f.get('finding')}\n"
            f"- 의미: {f.get('why_matters')}\n"
            f"- 실천: {f.get('actionable')}\n"
        )

    papers_text = ""
    for i, p in enumerate(research.get("papers") or [], 1):
        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:2])
        papers_text += (
            f"\n[논문 {i}] {p.get('title')}\n"
            f"저자: {authors} ({p.get('year')})\n"
            f"인용: {p.get('citationCount', 0)}\n"
            f"초록: {(p.get('abstract') or '')[:800]}\n"
        )

    user_overrides = ""
    if user_title:
        user_overrides += f"\n**사용자 지정 제목 (그대로 사용)**: {user_title}"
    if user_hook:
        user_overrides += f"\n**사용자 지정 도입부 훅 (그대로 사용)**: {user_hook}"

    learned = feedback_db.get_generation_context()

    user_content = f"""주제: {topic}
{user_overrides}

## 리서치에서 추출된 Key Findings
{findings_text}

## 원 논문 정보
{papers_text}
{learned}

위 정보로 롱폼 YouTube 스크립트를 작성해. 시스템 프롬프트의 형식을 엄격히 따를 것."""

    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.SCRIPT_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return msg.content[0].text


def _parse_metadata(script_text: str) -> dict[str, Any]:
    """스크립트에서 frontmatter용 메타데이터 추출."""
    meta: dict[str, Any] = {}

    def find(pattern: str, flags: int = 0) -> str:
        m = re.search(pattern, script_text, flags)
        return (m.group(1).strip() if m else "")

    meta["final_title"] = find(r"최종 선택 제목[:\s]*(.+)")
    meta["final_thumbnail_text"] = find(r"최종 선택 썸네일 문구[:\s]*(.+)")
    meta["category"] = find(r"카테고리[:\s]*([^\n]+)")
    meta["tags"] = find(r"태그[:\s]*([^\n]+)")
    meta["situation"] = find(r"현상[:\s]*([^\n]+)")
    meta["worry"] = find(r"고민[:\s]*([^\n]+)")
    meta["desire"] = find(r"욕구[:\s]*([^\n]+)")
    meta["plan"] = find(r"계획[:\s]*([^\n]+)")
    meta["thumb_expectation"] = find(r"- 기대[:\s]*(.+)")
    meta["thumb_evidence"] = find(r"- 증거[:\s]*(.+)")
    meta["thumb_question"] = find(r"- 의문[:\s]*(.+)")
    meta["thumb_empathy"] = find(r"- 공감[:\s]*(.+)")
    return meta


def save_script(
    script_text: str,
    topic: str,
    research: dict[str, Any],
    channel_brand: str = "science_channel",
    memo_paths: list[Path] | None = None,
) -> Path:
    """스크립트를 채널별 폴더에 frontmatter 붙여 저장."""
    channel = config.get_channel(channel_brand)
    code = channel["code"]
    scripts_dir = config.get_scripts_dir(channel_brand)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    slug = re.sub(r"\s+", "+", re.sub(r"[^\w가-힣+\s-]", "", topic).strip())[:50]
    filename = f"{code}_원고_YT롱폼_{slug}_{today}.md"
    out_path = scripts_dir / filename

    meta = _parse_metadata(script_text)

    # 논문 소스 DOI 리스트
    paper_sources = []
    for p in (research.get("papers") or [])[:5]:
        ext = p.get("externalIds") or {}
        doi = ext.get("DOI")
        if doi:
            paper_sources.append(f"doi:{doi}")

    # 제텔카스텐 메모 링크
    memo_links = []
    if memo_paths:
        for mp in memo_paths:
            memo_links.append(f"[[{mp.stem}]]")

    frontmatter = f"""---
type: youtube
channel_brand: {channel_brand}
channel_code: {code}
channel_name: "{channel['name']}"
channel_id: "{channel.get('id', '')}"
상태: 원고완료
brand_target: "{channel['target']}"
카테고리: {meta.get('category', '')}
주제: "{topic}"
final_title: "{meta.get('final_title', '').replace('"', "'")}"
final_thumbnail_text: "{meta.get('final_thumbnail_text', '').replace('"', "'")}"
thumbnail_variants:
  기대: "{meta.get('thumb_expectation', '').replace('"', "'")}"
  증거: "{meta.get('thumb_evidence', '').replace('"', "'")}"
  의문: "{meta.get('thumb_question', '').replace('"', "'")}"
  공감: "{meta.get('thumb_empathy', '').replace('"', "'")}"
viewer_frame:
  현상: "{meta.get('situation', '').replace('"', "'")}"
  고민: "{meta.get('worry', '').replace('"', "'")}"
  욕구: "{meta.get('desire', '').replace('"', "'")}"
  계획: "{meta.get('plan', '').replace('"', "'")}"
tags_list: "{meta.get('tags', '')}"
research_sources: {json.dumps(paper_sources, ensure_ascii=False)}
zettelkasten_memos: {json.dumps(memo_links, ensure_ascii=False)}
raw_research: "{research.get('saved_path', '')}"
video_path: ""
youtube_video_id: ""
youtube_url: ""
생성일: {date.today().isoformat()}
---

"""
    out_path.write_text(frontmatter + script_text, encoding="utf-8")
    return out_path


def full_research_and_script(
    topic: str,
    channel_brand: str = "science_channel",
    user_title: str | None = None,
    user_hook: str | None = None,
) -> dict[str, Any]:
    """end-to-end: 리서치 → 제텔카스텐 메모 → 원고 저장.

    Returns:
        { "topic", "research_path", "memo_paths", "script_path" }
    """
    channel = config.get_channel(channel_brand)
    code = channel["code"]

    print(f"[1/3] 논문 리서치: {topic}")
    research = research_topic(topic)

    print(f"[2/3] 제텔카스텐 메모 생성 ({len(research.get('findings') or [])}개)")
    memo_paths = create_memos_from_research(research, channel_code=code)

    print(f"[3/3] 스크립트 생성")
    script_text = generate_script(
        topic, research, user_title=user_title, user_hook=user_hook
    )
    script_path = save_script(
        script_text, topic, research, channel_brand=channel_brand, memo_paths=memo_paths
    )

    return {
        "topic": topic,
        "research_path": research.get("saved_path"),
        "memo_paths": [str(p) for p in memo_paths],
        "script_path": str(script_path),
    }


if __name__ == "__main__":
    import sys

    topic = " ".join(sys.argv[1:]) or "도파민과 학습 동기"
    result = full_research_and_script(topic)
    print("\n완료:")
    for k, v in result.items():
        print(f"  {k}: {v}")
