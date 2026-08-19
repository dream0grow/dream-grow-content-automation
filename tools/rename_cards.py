"""파이프라인 카드 파일명을 파일명 규칙으로 일괄 개명한다.

옛 이름 `DG-YYYY-NNNN <제목>.md` → 새 이름
`원고_<형식>_<카테고리>_<키워드+키워드>_<DG-YYYY-NNNN>.md`
(SNS 콘텐츠 제작 시스템 `00 시스템/03 파일명 규칙.md` — 큐시트 카드는
`큐시트_프롬프트개선_<DG-ID>.md`).

frontmatter(topic/content_id/format)는 그대로 두고 파일명만 바꾼다.
라우팅은 frontmatter로 돌기 때문에 개명은 파이프라인에 영향이 없다.

사용: python3 -m tools.rename_cards [--dry-run]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import obsidian_state as st  # noqa: E402

ID_RE = re.compile(r"DG-\d{4}-\d{4}")


def rename_all(dry_run: bool = False) -> list[tuple[str, str]]:
    st.require_backend()
    renamed: list[tuple[str, str]] = []
    for d in (st._active_dir(), st._done_dir()):
        for p in sorted(d.glob("*.md")):
            if p.name == "README.md":
                continue
            meta, _ = st._split(p.read_text(encoding="utf-8", errors="ignore"))
            m = ID_RE.search(str(meta.get("content_id", "") or "")) or ID_RE.search(p.name)
            if not m:
                print(f"건너뜀(ID 없음): {p.name}")
                continue
            topic = str(meta.get("topic", "") or "") or p.stem
            new_name = st.card_filename(m.group(0), topic, str(meta.get("format", "") or ""))
            if new_name == p.name:
                continue
            target = p.with_name(new_name)
            if target.exists():
                print(f"건너뜀(이미 있음): {new_name}")
                continue
            renamed.append((p.name, new_name))
            print(f"{'[계획] ' if dry_run else ''}{p.name}\n  → {new_name}")
            if not dry_run:
                p.rename(target)
    print(f"\n{'개명 예정' if dry_run else '개명 완료'}: {len(renamed)}건")
    return renamed


if __name__ == "__main__":
    rename_all(dry_run="--dry-run" in sys.argv)
