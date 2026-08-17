"""thread/newsletter 초안 열람 사본 — `05 리뷰/대기` 내보내기.

발행 원본은 어디까지나 파이프라인 카드(`vault/파이프라인/활성/DG-....md`)다.
카드는 리서치·토론·검수가 전부 쌓여 있어 폰에서 초안만 읽기가 어렵기 때문에,
초안이 완성될 때 다른 원고들과 같은 폴더·파일명 규칙(스레드_*, 뉴스레터_*)으로
**열람용 사본**을 함께 저장한다.

- script_feedback이 새 파일로 인식해 파일명+링크 포함 텔레그램 알림을 보낸다.
- frontmatter의 content_id 덕분에 이 파일명으로 온 텔레그램 피드백은
  script_feedback이 원본 카드의 수정 요청(재초안)으로 라우팅한다.
- 재초안되면 같은 파일명으로 덮어써 사본이 항상 최신 초안을 비춘다.
- **사본을 직접 고쳐도 된다**(GitHub Edit·옵시디언). 내보낼 때 남긴 `draft_hash`와
  본문이 달라지면 `copy_edits`가 사람 수정으로 보고 카드 초안에 되먹이고
  AI 원본과 비교해 문체를 학습한다.
"""
import hashlib
import os
import re

from vault_pipeline.vault_io import now_kst, parse_frontmatter, vault_root

from orchestrator.youtube_script import SCRIPT_DIR_DEFAULT, _file_token

# format → 폴더의 기존 파일명 규칙 접두사
PREFIX = {"thread": "스레드", "newsletter": "뉴스레터"}


def build_filename(fmt: str, topic: str) -> str:
    """{스레드|뉴스레터}_{주제}.md — 05 리뷰/대기의 기존 파일명 규칙."""
    prefix = PREFIX.get(fmt, fmt)
    token = _file_token(topic)[:60] or "무제"
    return f"{prefix}_{token}.md"


def normalize(text: str) -> str:
    """비교·해시용 정규화 — 줄 끝 공백과 앞뒤 빈 줄 차이는 수정으로 보지 않는다."""
    return "\n".join(line.rstrip() for line in (text or "").strip().splitlines())


def content_hash(text: str) -> str:
    """초안 본문의 지문(사람 수정 감지용). 정규화 후 sha1 앞 12자."""
    return hashlib.sha1(normalize(text).encode("utf-8")).hexdigest()[:12]


def body_of(raw: str) -> str:
    """사본 파일 원문 → 초안 본문만(프론트매터·안내 인용문·감사 주석 제거)."""
    _, body = parse_frontmatter(raw)
    lines = body.strip().splitlines()
    # 파일 맨 앞의 안내 인용문(> ...) 블록을 걷어낸다.
    start = 0
    while start < len(lines) and (not lines[start].strip()
                                  or lines[start].lstrip().startswith(">")):
        start += 1
    body = "\n".join(lines[start:])
    # 자동 처리가 남긴 HTML 주석(감사 흔적)은 본문이 아니다.
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    return normalize(body)


def guide_note(content_id: str) -> str:
    """사본 상단 안내문 — 직접 수정이 어떻게 반영되는지 알려준다."""
    return (
        f"> 열람용 사본입니다. 발행 원본은 파이프라인 카드({content_id})예요.\n"
        "> 이 파일을 GitHub Edit이나 옵시디언에서 **직접 고쳐도 됩니다** — 다음 실행"
        "(15분 주기)에 카드의 '✍️ 초안'으로 반영하고, AI 원본과 비교해 문체를 학습합니다.\n"
        "> 발행은 여전히 카드에서 approval_status를 approved로 바꿔야 시작됩니다.\n"
    )


def export(card: dict, fmt: str, draft: str) -> str:
    """초안 열람 사본을 05 리뷰/대기에 저장하고 파일명을 반환한다."""
    rel = os.getenv("VAULT_SCRIPT_PATH", SCRIPT_DIR_DEFAULT).strip("/")
    folder = vault_root() / rel
    folder.mkdir(parents=True, exist_ok=True)

    topic = card.get("topic") or "무제"
    content_id = card.get("content_id") or ""
    name = build_filename(fmt, topic)
    date = now_kst().strftime("%Y-%m-%d")

    fm = "\n".join([
        "---",
        f"주제: {topic}",
        f"content_id: {content_id}",
        f"채널: {fmt}",
        "상태: 리뷰대기",
        f"생성일: {date}",
        f"카테고리: {card.get('approved_keyword') or ''}",
        f"원본: 파이프라인/활성 카드 {content_id}",
        "검수상태: 대기",
        "generator: dreamgrow-orchestrator",
        # 사람 수정 감지 기준선 — 이 값과 본문 지문이 달라지면 copy_edits가 반영한다.
        f"draft_hash: {content_hash(draft)}",
        "---",
    ])
    (folder / name).write_text(
        f"{fm}\n\n{guide_note(content_id)}\n{draft.strip()}\n", encoding="utf-8")
    return name
