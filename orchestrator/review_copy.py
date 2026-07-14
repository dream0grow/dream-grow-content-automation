"""thread/newsletter 초안 열람 사본 — `05 리뷰/대기` 내보내기.

발행 원본은 어디까지나 파이프라인 카드(`vault/파이프라인/활성/DG-....md`)다.
카드는 리서치·토론·검수가 전부 쌓여 있어 폰에서 초안만 읽기가 어렵기 때문에,
초안이 완성될 때 다른 원고들과 같은 폴더·파일명 규칙(스레드_*, 뉴스레터_*)으로
**열람용 사본**을 함께 저장한다.

- script_feedback이 새 파일로 인식해 파일명+링크 포함 텔레그램 알림을 보낸다.
- frontmatter의 content_id 덕분에 이 파일명으로 온 텔레그램 피드백은
  script_feedback이 원본 카드의 수정 요청(재초안)으로 라우팅한다.
- 재초안되면 같은 파일명으로 덮어써 사본이 항상 최신 초안을 비춘다.
"""
import os

from vault_pipeline.vault_io import now_kst, vault_root

from orchestrator.youtube_script import SCRIPT_DIR_DEFAULT, _file_token

# format → 폴더의 기존 파일명 규칙 접두사
PREFIX = {"thread": "스레드", "newsletter": "뉴스레터"}


def build_filename(fmt: str, topic: str) -> str:
    """{스레드|뉴스레터}_{주제}.md — 05 리뷰/대기의 기존 파일명 규칙."""
    prefix = PREFIX.get(fmt, fmt)
    token = _file_token(topic)[:60] or "무제"
    return f"{prefix}_{token}.md"


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
        "---",
    ])
    note = (
        f"> 열람용 사본입니다. 발행 원본은 파이프라인 카드({content_id})예요.\n"
        "> 수정은 이 파일이 아니라 **텔레그램 알림에 답장**하거나 카드에서 하세요 — "
        "여기에 직접 고친 내용은 발행에 반영되지 않습니다.\n"
    )
    (folder / name).write_text(
        f"{fm}\n\n{note}\n{draft.strip()}\n", encoding="utf-8")
    return name
