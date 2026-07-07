"""카드 저장소 파사드 — 노션 ↔ 옵시디언 백엔드 스위치 (이관설계 M1)

호출처는 `from orchestrator import state as notion_state`로 이 모듈만 본다.
백엔드 선택: 환경변수 `DG_STATE_BACKEND`
- "notion"   (기본) : 기존 notion_state — 노션 DB
- "obsidian"        : obsidian_state — vault/파이프라인/ md 카드

이관 절차: Actions Variables에 DG_STATE_BACKEND=obsidian 설정 + 노션 잔여 카드
이전(M2) 후 노션 Secrets 삭제. 상세: docs/기획/노션_옵시디언_이관설계.md
"""
import os

BACKEND = os.getenv("DG_STATE_BACKEND", "notion").strip().lower()

if BACKEND == "obsidian":
    from orchestrator.obsidian_state import (  # noqa: F401
        age_minutes, append_formatted_section, append_section, create_card,
        next_content_id, notify, query_cards, read_latest_section,
        read_sections, read_sections_by_prefix, require_backend, update_card,
    )
else:
    from orchestrator.notion_state import (  # noqa: F401
        age_minutes, append_formatted_section, append_section, create_card,
        next_content_id, notify, query_cards, read_latest_section,
        read_sections, read_sections_by_prefix, update_card,
    )
    from orchestrator.config import require_notion as require_backend  # noqa: F401
