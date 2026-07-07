"""카드 저장소 파사드 — 옵시디언 볼트 백엔드 (노션 철수 완료)

호출처는 `from orchestrator import state as store`로 이 모듈만 본다.
저장소는 옵시디언 볼트 하나뿐이다 — `vault/파이프라인/` 아래 md 카드
(`orchestrator/obsidian_state.py`, 볼트 경로는 환경변수 `DG_VAULT_ROOT`, 기본 `vault/`).
볼트 동기화는 GitHub Actions가 `vault/`를 커밋·push하는 git/GitHub 단일 경로다.

과거 노션 백엔드(`DG_STATE_BACKEND` 스위치)는 폐기됐다. 이관 경위는 docs/HISTORY.md,
설계는 docs/기획/노션_옵시디언_이관설계.md 참고.
"""
from orchestrator.obsidian_state import (  # noqa: F401
    age_minutes, append_formatted_section, append_section, create_card,
    next_content_id, notify, query_cards, read_latest_section,
    read_sections, read_sections_by_prefix, require_backend, update_card,
)
