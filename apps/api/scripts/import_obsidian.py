"""Import legacy Obsidian markdown files into the contents table.

Maps Korean status values to ContentStatus enum. Idempotent — uses
frontmatter.source_path hash to skip rows that already exist.

Usage:
    python -m apps.api.scripts.import_obsidian /path/to/obsidian/vault
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import select

from apps.api.core.db import SessionLocal
from apps.api.models import Content
from packages.shared.enums import KOREAN_STATUS_MAP, ContentStatus
from packages.shared.frontmatter import split_frontmatter


def _hash_path(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]


async def main(root: Path) -> None:
    if not root.exists():
        print(f"root does not exist: {root}")
        return
    files = list(root.rglob("*.md"))
    print(f"scanning {len(files)} markdown files")
    async with SessionLocal() as db:
        for path in files:
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fm, body = split_frontmatter(raw)
            source_hash = _hash_path(path)
            existing = await db.scalar(
                select(Content).where(Content.frontmatter["source_hash"].astext == source_hash)
            )
            if existing:
                continue
            channel = (fm.channel or "thread").lower()
            status_korean = fm.status or ""
            status = KOREAN_STATUS_MAP.get(status_korean, ContentStatus.DRAFT).value
            data = fm.model_dump(by_alias=True, exclude_none=True)
            data["source_hash"] = source_hash
            data["source_path"] = str(path)
            db.add(Content(
                channel=channel,
                topic=fm.topic or path.stem,
                category=fm.category,
                status=status,
                body_md=body,
                ai_original_md=body,
                frontmatter=data,
            ))
        await db.commit()
    print("import complete")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    asyncio.run(main(target))
