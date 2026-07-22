"""릴스/숏폼 대본 자동 생성 — format: reels 카드 처리.

youtube_script와 같은 경로를 탄다: 키워드 승인 후(브리프 생성 직후)
run.handle_keyword_approved가 호출하고, 대본을 볼트 `05 리뷰/대기`(VAULT_SCRIPT_PATH)에
`type: reels-script, 검수상태: 대기`로 저장한다. 이후는 기존 배선 그대로 —
script_feedback이 파일명 포함 텔레그램 알림을 보내고, 답장하면 수정 핑퐁이 돈다.

자동 발행은 없다 — 릴스 대본의 종착지는 사람의 촬영이다.
"""
import json
import os
import re

from vault_pipeline.vault_io import now_kst, vault_root

from orchestrator import agent_dialogue, llm, prompts
from orchestrator.youtube_script import SCRIPT_DIR_DEFAULT, _file_token

# format 필드에서 릴스/숏폼으로 인정하는 값들
REELS_FORMATS = {"reels", "reel", "shorts", "short", "shortform", "릴스", "숏폼", "쇼츠"}

# 말하기 기준 분당 글자 수(한국어) — 대사 목표 분량 계산용
CHARS_PER_MINUTE = 300


def _formats(format_field: str) -> list[str]:
    return [f.strip().lower() for f in (format_field or "").split(",") if f.strip()]


def wants_reels(format_field: str) -> bool:
    return any(f in REELS_FORMATS for f in _formats(format_field))


def build_filename(topic: str, keyword: str) -> str:
    """원고_릴스_{주제}_{키워드}.md — 05 리뷰/대기의 기존 파일명 규칙 계열."""
    cat = _file_token(topic)[:30] or "기타"
    kw = _file_token(keyword)[:30]
    base = f"원고_릴스_{cat}" + (f"_{kw}" if kw and kw != cat else "")
    return base[:120] + ".md"


def script_seconds() -> int:
    try:
        return max(15, int(os.getenv("DG_REELS_SECONDS") or "45"))
    except ValueError:
        return 45


def generate(card: dict, brief: dict, revision_note: str = "") -> str:
    """브리프 → 릴스 대본 마크다운 (글쓰기 모델 사용)."""
    seconds = script_seconds()
    feedback_block = (
        f"[사람 검수자의 수정 지시 — 최우선 반영]\n{revision_note}" if revision_note else ""
    )
    prompt = prompts.REELS_SCRIPT.format(
        brief=json.dumps(brief, ensure_ascii=False, indent=1),
        hook_examples=agent_dialogue.load_hooks(),
        feedback_block=feedback_block,
        seconds=seconds,
        chars=seconds * CHARS_PER_MINUTE // 60,
        audience=card.get("audience") or "초등 저학년 학부모",
    )
    script = llm.call_writing(prompt, system=prompts.get_system(), max_tokens=8000)
    if len(script.strip()) < 300:
        raise RuntimeError(f"릴스 대본이 비정상적으로 짧습니다 ({len(script.strip())}자)")
    return script.strip()


def save_to_review(card: dict, script: str) -> str:
    """대본을 05 리뷰/대기에 저장하고 파일명을 반환한다."""
    rel = os.getenv("VAULT_SCRIPT_PATH", SCRIPT_DIR_DEFAULT).strip("/")
    folder = vault_root() / rel
    folder.mkdir(parents=True, exist_ok=True)

    topic = card.get("topic") or "무제"
    keyword = card.get("approved_keyword") or ""
    date = now_kst().strftime("%Y-%m-%d")
    seconds = script_seconds()

    fm = "\n".join(
        [
            "---",
            "type: reels-script",
            "상태: 초안",
            f"생성일: {date}",
            "채널: reels",
            f"길이: {seconds}초",
            f"카테고리: {topic}",
            f"키워드: {keyword}",
            f"원본: [\"파이프라인 {card.get('content_id', '')}\"]",
            "검수상태: 대기",
            "발행시간:",
            "generator: dreamgrow-orchestrator",
            "---",
        ]
    )
    heading = "" if re.search(r"^\s*#\s+릴스\s*원고", script, re.M) else f"# 릴스 원고 -- {topic}\n\n"
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
    """대본 생성 + 저장. 저장된 파일명을 반환한다."""
    return save_to_review(card, generate(card, brief, revision_note))
