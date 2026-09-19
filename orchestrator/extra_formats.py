"""릴스 스크립트 · 네이버 블로그 원고 자동 생성 — format 에 reels / blog 가 있는 카드 처리.

youtube_script 와 같은 자리(run.handle_keyword_approved, 브리프 직후)에서 호출된다.
브리프(리서치+키워드+훅)를 받아 형식별 원고를 써서 볼트 `05 리뷰/대기`(VAULT_SCRIPT_PATH)에
저장한다. 이후는 기존 배선이 그대로 잇는다:
  - vault_pipeline.script_feedback 이 새 원고를 텔레그램으로 알리고, 답장으로 수정 지시를 받는다(핑퐁)
  - AI 원본을 `_system/ai_originals/원고/<파일명>` 에 남겨, 사람이 고친 뒤(05 리뷰/완료·64 발행완료)
    vault_pipeline.script_learn 이 diff 를 학습해 다음 원고에 반영한다 (학습 루프)

한 카드에 여러 형식(youtube, reels, thread, newsletter, blog)을 적으면 한 번에 다 만든다.
실패는 카드에 경고만 남기고 다른 형식은 계속 진행한다 (youtube_script 와 동일 정책).
"""
import json
import os
import re

from vault_pipeline.vault_io import now_kst, vault_root

from orchestrator import agent_dialogue, llm, prompts
from orchestrator.youtube_script import SCRIPT_DIR_DEFAULT, _file_token

REELS_FORMATS = {"reels", "reel", "shorts", "short", "릴스", "쇼츠", "숏폼"}
BLOG_FORMATS = {"blog", "naver", "naverblog", "블로그", "네이버", "네이버블로그"}

# frontmatter type / 채널 / 파일명 라벨
SPEC = {
    "reels": {"type": "reels-script", "channel": "reels", "label": "릴스", "heading": "릴스 스크립트"},
    "blog": {"type": "blog-post", "channel": "blog", "label": "블로그", "heading": "네이버 블로그 원고"},
}

REELS_PROMPT = """당신은 초등 학부모 대상 교육 브랜드 '드림그로우'의 숏폼(릴스/쇼츠) 작가입니다.
아래 브리프를 바탕으로 30~60초 릴스 스크립트를 한국어로 씁니다.

[브리프]
{brief}

[검증된 훅 예시 — 구조만 참고, 문장을 베끼지 말 것]
{hook_examples}

{feedback_block}

규칙
- 첫 3초 훅 1문장: 스크롤을 멈추게 하되 과장·공포 조장 금지, 부모의 실제 상황을 짚는다
- 구성: 훅(0~3초) → 상황/현상(3~15초) → 원리 또는 관찰 포인트(15~40초) → 오늘 해볼 한 가지(40~55초) → 마무리 한 줄
- 자막 텍스트(짧게, 화면용)와 내레이션(구어체)을 구분한다. 장면마다 화면 연출 지시를 적는다
- 통계·연구는 브리프에 근거가 있는 것만, 출처 없는 숫자는 쓰지 않는다
- 이모지는 쓰지 않는다. 대상은 {audience}

출력 형식(마크다운, 이 형식만)
## 릴스 스크립트

**컨셉:** (한 줄)
**예상 길이:** N초
**BGM 분위기:** (한 줄)

| 시간 | 화면 | 자막/텍스트 | 내레이션 |
|------|------|-------------|----------|
| 0-3초 | ... | ... | ... |
| ... | ... | ... | ... |

**캡션(게시글 본문, 3~5줄):**
...

**해시태그:** #태그1 #태그2 ... (8~12개)

**촬영 메모:** (촬영·편집자에게 남기는 2~3줄)
"""

BLOG_PROMPT = """당신은 초등 학부모 대상 교육 브랜드 '드림그로우'의 네이버 블로그 작가입니다.
아래 브리프를 바탕으로 네이버 검색에서 읽히는 블로그 글을 한국어로 씁니다.

[브리프]
{brief}

[검증된 훅 예시 — 구조만 참고]
{hook_examples}

{feedback_block}

규칙
- 분량 1,800~2,600자. 소제목(##) 4~6개로 나누고, 각 소제목 아래 2~4문단
- 핵심 키워드 "{keyword}" 를 제목·첫 문단·소제목 1개·마지막 문단에 자연스럽게 넣는다 (억지 반복 금지)
- 도입: 학부모가 겪는 구체적 장면 1개로 시작 → 왜 그런지(원리) → 집에서 해볼 방법(단계별) → 주의점 → 정리
- 통계·연구는 브리프에 근거가 있는 것만 인용하고 출처를 문장 안에 밝힌다. 없으면 쓰지 않는다
- 이모지는 쓰지 않는다. 단정·훈계 대신 관찰과 제안의 말투. 대상은 {audience}
- 마지막 문장은 "아이와 부모의 꿈을 키웁니다." 로 끝내고 다음 줄에 "-Dream_Grow-" 서명

출력 형식(마크다운, 이 형식만)
## 제목 후보
1. ...
2. ...
3. ...

## 본문
(제목은 본문에 다시 쓰지 않는다. 소제목부터 시작)

## 이미지 넣을 자리
- (몇 번째 소제목 아래 / 어떤 이미지) × 3~4개

## 해시태그
#태그1 #태그2 ... (10~15개)

## 검색 노출 메모
- 대표 키워드 / 보조 키워드 2~3개 / 예상 검색 의도 한 줄
"""


def _formats(format_field: str) -> list[str]:
    return [f.strip().lower() for f in str(format_field or "").split(",") if f.strip()]


def wanted(format_field: str) -> list[str]:
    """카드 format 에서 이 모듈이 만들 형식 목록 (순서 고정: reels → blog)."""
    toks = set(_formats(format_field))
    out = []
    if toks & REELS_FORMATS:
        out.append("reels")
    if toks & BLOG_FORMATS:
        out.append("blog")
    return out


def build_filename(fmt: str, topic: str, keyword: str) -> str:
    cat = _file_token(topic)[:30] or "기타"
    kw = _file_token(keyword)[:30]
    base = f"원고_{SPEC[fmt]['label']}_{cat}" + (f"_{kw}" if kw and kw != cat else "")
    return base[:120] + ".md"


def generate(fmt: str, card: dict, brief: dict, revision_note: str = "") -> str:
    feedback_block = (
        f"[사람 검수자의 수정 지시 — 최우선 반영]\n{revision_note}" if revision_note else ""
    )
    common = dict(
        brief=json.dumps(brief, ensure_ascii=False, indent=1),
        hook_examples=agent_dialogue.load_hooks(),
        feedback_block=feedback_block,
        audience=card.get("audience") or "초등 저학년 학부모",
        keyword=card.get("approved_keyword") or card.get("topic") or "",
    )
    prompt = (REELS_PROMPT if fmt == "reels" else BLOG_PROMPT).format(**common)
    # 사람 수정에서 학습된 문체 패턴(Honcho) 을 시스템 프롬프트 뒤에 붙인다
    style = agent_dialogue.get_style_context(SPEC[fmt]["channel"])
    system = prompts.get_system() + (f"\n\n{style}" if style else "")
    text = llm.call_writing(prompt, system=system, max_tokens=8000)
    minimum = 300 if fmt == "reels" else 800
    if len(text.strip()) < minimum:
        raise RuntimeError(f"{SPEC[fmt]['label']} 원고가 비정상적으로 짧습니다 ({len(text.strip())}자)")
    return text.strip()


def save_ai_original(name: str, md: str) -> None:
    """학습용 AI 원본 보관 (_system/ai_originals/원고/). 실패해도 원고 저장에는 영향 없음."""
    try:
        d = vault_root() / "_system" / "ai_originals" / "원고"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(md, encoding="utf-8")
    except Exception:
        pass


def save_to_review(fmt: str, card: dict, text: str) -> str:
    """원고를 05 리뷰/대기에 저장하고 파일명을 반환한다 (youtube_script.save_to_review 와 같은 스키마)."""
    rel = os.getenv("VAULT_SCRIPT_PATH", SCRIPT_DIR_DEFAULT).strip("/")
    folder = vault_root() / rel
    folder.mkdir(parents=True, exist_ok=True)
    spec = SPEC[fmt]
    topic = card.get("topic") or "무제"
    keyword = card.get("approved_keyword") or ""
    date = now_kst().strftime("%Y-%m-%d")
    fm = "\n".join(
        [
            "---",
            f"type: {spec['type']}",
            "상태: 초안",
            f"생성일: {date}",
            f"채널: {spec['channel']}",
            f"카테고리: {topic}",
            f"키워드: {keyword}",
            f"원본: [\"파이프라인 {card.get('content_id', '')}\"]",
            "검수상태: 대기",
            "발행시간:",
            "generator: dreamgrow-orchestrator",
            "---",
        ]
    )
    heading = "" if re.search(r"^\s*#\s+", text, re.M) else f"# {spec['heading']} -- {topic}\n\n"
    md = f"{fm}\n\n{heading}{text}\n"
    name = build_filename(fmt, topic, keyword)
    path = folder / name
    n = 1
    while path.exists():
        n += 1
        path = folder / f"{name[:-3]}-{n}.md"
    path.write_text(md, encoding="utf-8")
    save_ai_original(path.name, md)
    return path.name


def deliver(fmt: str, card: dict, brief: dict, revision_note: str = "") -> str:
    """원고 생성 + 저장. 저장된 파일명을 반환한다."""
    return save_to_review(fmt, card, generate(fmt, card, brief, revision_note))
