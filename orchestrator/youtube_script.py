"""유튜브 롱폼 원고 자동 생성 — format: youtube 카드 처리.

키워드 승인 후(브리프 생성 직후) run.handle_keyword_approved가 호출한다.
원고를 써서 볼트 `05 리뷰/대기`(VAULT_SCRIPT_PATH)에 yt_research 사이트와
동일한 frontmatter(type: youtube-script, 검수상태: 대기)로 저장한다.

이후는 기존 배선이 그대로 잇는다:
  - vault_pipeline.script_feedback(orchestrator.yml 같은 실행)이 새 원고를 찾아
    파일명 포함 텔레그램 알림을 보낸다.
  - 사용자가 그 알림에 답장하면 사이트 웹훅 → `_system/feedback/` pending 노트
    → 다음 실행에서 원고에 수정 반영 (핑퐁).

Threads/스티비 같은 자동 발행은 없다 — 유튜브 원고의 종착지는 사람의 촬영이다.
"""
import json
import os
import re

from vault_pipeline.vault_io import now_kst, vault_root

from orchestrator import agent_dialogue, llm, prompts

# 사이트(lib/vault.ts)·script_feedback과 동일한 기본 폴더
SCRIPT_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/05 리뷰/대기"

# format 필드에서 유튜브로 인정하는 값들
YT_FORMATS = {"youtube", "yt", "video", "유튜브"}

# 말하기 기준 분당 글자 수(한국어) — 본문 목표 분량 계산용
CHARS_PER_MINUTE = 300


def _formats(format_field: str) -> list[str]:
    return [f.strip().lower() for f in (format_field or "").split(",") if f.strip()]


def wants_youtube(format_field: str) -> bool:
    return any(f in YT_FORMATS for f in _formats(format_field))


def _file_token(s: str) -> str:
    """파일명 토큰 정리 — 사이트 lib/vault.ts fileToken과 동일 규칙."""
    return re.sub(r"\s+", "", re.sub(r'[\\/:*?"<>|#^\[\]]', "", s or "")).strip()


def build_filename(topic: str, keyword: str) -> str:
    """원고_YT롱폼_{주제}_{키워드}.md — 사이트 파일명 규칙과 동일 계열."""
    cat = _file_token(topic)[:30] or "기타"
    kw = _file_token(keyword)[:30]
    base = f"원고_YT롱폼_{cat}" + (f"_{kw}" if kw and kw != cat else "")
    return base[:120] + ".md"


def script_minutes() -> int:
    try:
        return max(3, int(os.getenv("DG_YT_SCRIPT_MINUTES", "10")))
    except ValueError:
        return 10


def generate(card: dict, brief: dict, revision_note: str = "") -> str:
    """브리프 → 유튜브 롱폼 원고 마크다운 (글쓰기 모델 사용)."""
    minutes = script_minutes()
    feedback_block = (
        f"[사람 검수자의 수정 지시 — 최우선 반영]\n{revision_note}" if revision_note else ""
    )
    prompt = prompts.YOUTUBE_SCRIPT.format(
        brief=json.dumps(brief, ensure_ascii=False, indent=1),
        hook_examples=agent_dialogue.load_hooks(),
        feedback_block=feedback_block,
        minutes=minutes,
        chars=minutes * CHARS_PER_MINUTE,
        audience=card.get("audience") or "초등 저학년 학부모",
    )
    script = llm.call_writing(prompt, system=prompts.get_system(), max_tokens=16000)
    if len(script.strip()) < 500:
        raise RuntimeError(f"유튜브 원고가 비정상적으로 짧습니다 ({len(script.strip())}자)")
    return script.strip()


def save_to_review(card: dict, script: str) -> str:
    """원고를 05 리뷰/대기에 저장하고 파일명을 반환한다.

    frontmatter는 사이트 saveLongformScript와 동일 스키마 —
    script_feedback이 `type: youtube-script` + `검수상태: 대기`로 새 원고를 인식한다.
    """
    rel = os.getenv("VAULT_SCRIPT_PATH", SCRIPT_DIR_DEFAULT).strip("/")
    folder = vault_root() / rel
    folder.mkdir(parents=True, exist_ok=True)

    topic = card.get("topic") or "무제"
    keyword = card.get("approved_keyword") or ""
    date = now_kst().strftime("%Y-%m-%d")
    minutes = script_minutes()

    fm = "\n".join(
        [
            "---",
            "type: youtube-script",
            "상태: 초안",
            f"생성일: {date}",
            "채널: youtube",
            f"길이: {minutes}분",
            f"카테고리: {topic}",
            f"키워드: {keyword}",
            f"원본: [\"파이프라인 {card.get('content_id', '')}\"]",
            "검수상태: 대기",
            "발행시간:",
            "generator: dreamgrow-orchestrator",
            "---",
        ]
    )
    heading = "" if re.search(r"^\s*#\s+영상\s*원고", script, re.M) else f"# 영상 원고 -- {topic}\n\n"
    md = f"{fm}\n\n{heading}{script}\n"

    name = build_filename(topic, keyword)
    path = folder / name
    n = 1
    while path.exists():  # 재초안 등으로 같은 이름이 있으면 덮지 않고 새 파일로
        n += 1
        path = folder / f"{name[:-3]}-{n}.md"
    path.write_text(md, encoding="utf-8")
    return path.name


def deliver(card: dict, brief: dict, revision_note: str = "") -> str:
    """원고 생성 + 저장. 저장된 파일명을 반환한다."""
    return save_to_review(card, generate(card, brief, revision_note))
