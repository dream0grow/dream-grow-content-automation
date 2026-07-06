#!/usr/bin/env python3
"""볼트 비밀값 스캐너 — 커밋 전 안전 게이트 (Phase 0 보안)

옵시디언 볼트(마크다운)에 API 키·토큰·개인식별정보가 섞여 git으로
반출되는 사고를 막는다. 2026-07 실사에서 볼트 raw/ 안 Roam 일간노트에
실제 Anthropic API 키가 평문으로 발견된 전력이 있다.

사용:
    python3 tools/vault_secret_scan.py vault/            # 스캔, 발견 시 exit 1
    python3 tools/vault_secret_scan.py vault/ --quiet    # 파일·종류만 출력(값 미출력)

GitHub Actions에서는 볼트 커밋 직전에 실행해, 발견되면 커밋을 중단한다.
"""
import argparse
import re
import sys
from pathlib import Path

# (이름, 패턴) — 패턴은 오탐을 줄이기 위해 실제 키 형식 위주로 좁게 잡는다
PATTERNS = [
    ("Anthropic API 키", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI API 키", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("GitHub 토큰", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}")),
    ("AWS 액세스 키", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Slack 토큰", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("노션 시크릿", re.compile(r"secret_[A-Za-z0-9]{40,}|ntn_[A-Za-z0-9]{40,}")),
    ("텔레그램 봇 토큰", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}\b")),
    ("비밀키 블록", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("주민등록번호", re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b")),
    ("개인통관고유부호", re.compile(r"\bP\d{12}\b")),
    # .env 형식의 키=값 (값이 20자 이상 무작위 문자열일 때만)
    ("환경변수 형식 비밀값", re.compile(
        r"(?:API_KEY|SECRET|TOKEN|PASSWORD)\s*[=:]\s*['\"]?[A-Za-z0-9_\-/+]{20,}")),
]

SCAN_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".canvas", ".env"}
SKIP_DIRS = {".git", ".obsidian", "node_modules", "__pycache__"}


def scan(root: Path, quiet: bool) -> int:
    findings = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pat in PATTERNS:
            for m in pat.finditer(text):
                findings += 1
                line_no = text.count("\n", 0, m.start()) + 1
                if quiet:
                    print(f"[발견] {name}: {path}:{line_no}")
                else:
                    masked = m.group(0)[:12] + "…" + m.group(0)[-4:]
                    print(f"[발견] {name}: {path}:{line_no} ({masked})")
    return findings


def main() -> None:
    ap = argparse.ArgumentParser(description="볼트 비밀값 스캐너")
    ap.add_argument("root", help="스캔할 볼트 경로")
    ap.add_argument("--quiet", action="store_true", help="값 일부도 출력하지 않음")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"경로 없음: {root}", file=sys.stderr)
        sys.exit(2)

    n = scan(root, args.quiet)
    if n:
        print(f"\n비밀값 의심 {n}건 — 볼트에서 제거(또는 패스워드 매니저로 반출)하고 키는 재발급하세요.")
        sys.exit(1)
    print("비밀값 미발견 — 통과")


if __name__ == "__main__":
    main()
