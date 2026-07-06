"""옵시디언 볼트 읽기/쓰기 — frontmatter, 안전한 파일명, 중복 방지 장부

볼트 헌법(vault/CLAUDE.md)의 집행 계층:
- 기존 파일은 절대 덮어쓰지 않는다 (신규 생성만)
- 모든 산출물 frontmatter에 `출처: plaud:<file_id>` 기록
- 처리 완료 장부는 _system/logs/plaud_ledger.json

경로는 매 호출 시 DG_VAULT_ROOT 환경변수에서 읽는다 (테스트·로컬 실행 대응).
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

KST = timezone(timedelta(hours=9))

# 옵시디언/파일시스템에서 문제가 되는 문자
_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]\n\r\t]')


def vault_root() -> Path:
    return Path(os.getenv("DG_VAULT_ROOT", str(PROJECT_ROOT / "vault")))


def _ledger_path() -> Path:
    return vault_root() / "_system" / "logs" / "plaud_ledger.json"


def now_kst() -> datetime:
    return datetime.now(KST)


def today() -> str:
    return now_kst().strftime("%Y-%m-%d")


def safe_filename(title: str, max_len: int = 80) -> str:
    """제목을 파일명으로 안전하게. 마침표·공백 정리, 길이 제한."""
    name = _UNSAFE.sub(" ", title).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    return name[:max_len].strip() or "무제"


def frontmatter_block(meta: dict) -> str:
    """dict → YAML frontmatter 블록 (한글 보존, 키 순서 유지)."""
    body = yaml.safe_dump(
        meta, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).strip()
    return f"---\n{body}\n---\n"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """마크다운에서 (frontmatter dict, 본문)을 분리. 없으면 ({}, 원문)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except yaml.YAMLError:
        meta = {}
    return meta, text[m.end():]


def write_note(rel_dir: str, title: str, meta: dict, body: str,
               dry_run: bool = False) -> Path:
    """볼트에 새 노트를 만든다. 같은 이름이 있으면 절대 덮지 않고 ' (2)'를 붙인다."""
    directory = vault_root() / rel_dir
    directory.mkdir(parents=True, exist_ok=True)
    base = safe_filename(title)
    path = directory / f"{base}.md"
    n = 2
    while path.exists():
        path = directory / f"{base} ({n}).md"
        n += 1
    content = frontmatter_block(meta) + "\n" + body.rstrip() + "\n"
    if not dry_run:
        path.write_text(content, encoding="utf-8")
    return path


def load_ledger() -> dict:
    path = _ledger_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_ledger(ledger: dict) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def processed_ids() -> set[str]:
    """이미 처리한 plaud file_id 집합 — 장부 + 볼트 frontmatter 이중 확인."""
    ids = set(load_ledger().keys())
    # 장부가 유실돼도 볼트 노트의 `출처: plaud:<id>` 필드로 복원 가능
    pat = re.compile(r"plaud:([A-Za-z0-9_\-]+)")
    for sub in ("제텔카스텐", "발행"):
        root = vault_root() / sub
        if not root.exists():
            continue
        for p in root.rglob("*.md"):
            try:
                head = p.read_text(encoding="utf-8", errors="ignore")[:600]
            except OSError:
                continue
            for m in pat.finditer(head):
                ids.add(m.group(1))
    return ids


def mark_processed(file_id: str, name: str, artifacts: list[str],
                   dry_run: bool = False) -> None:
    if dry_run:
        return
    ledger = load_ledger()
    ledger[file_id] = {
        "name": name,
        "processed_at": now_kst().isoformat(timespec="seconds"),
        "artifacts": artifacts,
    }
    save_ledger(ledger)


def append_review_queue(lines: list[str], dry_run: bool = False) -> None:
    """결재함에 항목을 추가한다 (append만, 기존 내용 불변)."""
    if not lines or dry_run:
        return
    queue = vault_root() / "_system" / "review_queue.md"
    queue.parent.mkdir(parents=True, exist_ok=True)
    stamp = now_kst().strftime("%Y-%m-%d %H:%M")
    block = f"\n## {stamp} plaud 파이프라인\n" + "\n".join(lines) + "\n"
    with queue.open("a", encoding="utf-8") as f:
        f.write(block)


def log_line(msg: str, dry_run: bool = False) -> None:
    """일자별 실행 로그. 빨강 차단 통계 등 파일로 남기면 안 되는 내용의 유일한 기록처."""
    print(msg)
    if dry_run:
        return
    log_dir = vault_root() / "_system" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"plaud_{today()}.log"
    stamp = now_kst().strftime("%H:%M:%S")
    with log_file.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {msg}\n")
