"""원고 수정·보완 핑퐁 — 오케스트레이터 쪽 나머지 절반 (yt_research 연동)

yt_research 사이트(Vercel)는 롱폼 원고를 볼트 `05 리뷰/대기`에 저장하고, 사용자가
텔레그램 봇 답장으로 남긴 수정 의견을 `_system/feedback/`에 `status: pending` 노트로
쌓아둔다(사이트 쪽 수신부는 이미 구현됨). 이 모듈은 오케스트레이터가 해야 할 나머지 절반이다:

  ① 초안 완성 알림: `05 리뷰/대기`의 새 원고를 찾아 **원고 파일명을 포함한** 텔레그램
     메시지를 보낸다. 사용자가 이 메시지에 답장하면 사이트 웹훅이 파일명을 추출해
     피드백 노트를 만든다 (핑퐁의 시작).
  ② 피드백 반영: `_system/feedback/`의 `type: feedback, status: pending` 노트를 읽어
     대상 원고를 수정하고, 노트를 `status: applied`로 갱신한다 (핑퐁의 완료).

폴더/스키마는 사이트(lib/vault.ts)와 정확히 맞춘다:
  - 원고 폴더:   VAULT_SCRIPT_PATH   (기본 "SNS 콘텐츠 제작 시스템/05 리뷰/대기")
  - 피드백 폴더: VAULT_FEEDBACK_PATH (기본 "_system/feedback")

안전 규칙(볼트 헌법·폴더 소유권):
  - 원고 수정은 프론트매터를 그대로 보존하고 본문만 교체한다.
  - 수정 결과가 원본보다 크게 짧아지면(내용 유실 의심) 쓰지 않고 노트를 error로 남긴다.
  - 알림 중복은 장부(_system/logs/script_feedback_ledger.json)로 막는다.
  - 피드백 노트는 status로 재처리를 막는다(pending만 처리).

실행:
    python3 -m vault_pipeline.script_feedback              # 알림 + 피드백 반영
    python3 -m vault_pipeline.script_feedback --dry-run    # 대상만 출력, 쓰지 않음
    python3 -m vault_pipeline.script_feedback --announce-only
    python3 -m vault_pipeline.script_feedback --apply-only
"""
import argparse
import json
import os
import re
from pathlib import Path

from vault_pipeline import prompts, telegram_notify
from vault_pipeline.vault_io import (
    log_line, now_kst, parse_frontmatter, vault_root,
)

from orchestrator import llm

# 사이트(lib/vault.ts)와 동일한 기본 폴더 — env로 조정 가능(양쪽 같은 값을 써야 한다).
SCRIPT_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/05 리뷰/대기"
FEEDBACK_DIR_DEFAULT = "_system/feedback"

# 이보다 짧은 산출물은 수정 결과로 신뢰하지 않는다(LLM이 원고를 통째로 날린 경우 방지).
MIN_SCRIPT_CHARS = 200
# 수정본이 원본의 이 비율 미만이면 내용 유실로 보고 반영하지 않는다.
MIN_KEEP_RATIO = 0.5
# 한 번에 보낼 최대 알림/처리 건수(첫 실행 백로그 폭주 방지).
DEFAULT_MAX = 10

# 검수 대기 상태로 인정하는 값(사이트는 새 원고에 "대기"를 넣는다). 완료/승인은 제외.
PENDING_REVIEW = {"", "대기", "검토대기", "리뷰대기"}


def _script_dir() -> Path:
    rel = os.getenv("VAULT_SCRIPT_PATH", SCRIPT_DIR_DEFAULT).strip("/")
    return vault_root() / rel


def _feedback_dir() -> Path:
    rel = os.getenv("VAULT_FEEDBACK_PATH", FEEDBACK_DIR_DEFAULT).strip("/")
    return vault_root() / rel


def _ledger_path() -> Path:
    return vault_root() / "_system" / "logs" / "script_feedback_ledger.json"


def _load_ledger() -> dict:
    p = _ledger_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_ledger(ledger: dict, dry_run: bool) -> None:
    if dry_run:
        return
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _split_raw(text: str) -> tuple[str, str]:
    """(프론트매터 블록 원문, 본문)으로 분리. 프론트매터를 원문 그대로 보존한다."""
    m = re.match(r"^(---\s*\n.*?\n---\s*\n?)(.*)$", text, re.DOTALL)
    if m:
        return m.group(1), m.group(2)
    return "", text


def _strip_fences(text: str) -> str:
    return re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", text.strip())


# ---------- ① 초안 완성 알림 ----------

def find_new_scripts() -> list[dict]:
    """아직 알리지 않은 검수 대기 원고 목록(오래된 알림 중복은 장부로 막는다)."""
    directory = _script_dir()
    if not directory.exists():
        return []
    ledger = _load_ledger()
    announced = set(ledger.get("announced", {}).keys())
    out: list[dict] = []
    for p in sorted(directory.glob("*.md"), key=lambda x: x.stat().st_mtime,
                    reverse=True):
        if p.name == "README.md" or p.name in announced:
            continue
        meta, _ = parse_frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
        if str(meta.get("type", "")).strip() != "youtube-script":
            continue
        if str(meta.get("검수상태", "")).strip() not in PENDING_REVIEW:
            continue
        out.append({"name": p.name, "path": p, "meta": meta})
    return out


def announce_new_scripts(dry_run: bool, max_items: int = DEFAULT_MAX) -> list[str]:
    """새 원고를 텔레그램으로 알린다(파일명 포함). 알린 파일명 목록 반환."""
    scripts = find_new_scripts()[:max_items]
    if not scripts:
        return []
    ledger = _load_ledger()
    announced = ledger.setdefault("announced", {})
    sent_names: list[str] = []
    for s in scripts:
        meta = s["meta"]
        title = str(meta.get("카테고리", "") or meta.get("키워드", "")).strip()
        length = str(meta.get("길이", "")).strip()
        head = f"✍️ 새 원고 초안 완성{f' · {title}' if title else ''}{f' ({length})' if length else ''}"
        msg = (
            f"{head}\n"
            f"원고: {s['name']}\n\n"
            "이 메시지에 답장으로 수정 의견을 보내면 다음 실행에 반영됩니다. "
            "(예: 도입부를 더 짧게, 사례를 교실 장면으로)"
        )
        ok = False if dry_run else telegram_notify.send(msg)
        log_line(f"원고 알림{'(dry)' if dry_run else ''}: {s['name']}"
                 + ("" if dry_run or ok else " — 텔레그램 미발송(설정 없음)"),
                 dry_run=dry_run)
        # 텔레그램 미설정이어도 장부엔 남겨 재알림 폭주를 막는다(알림은 부가 기능).
        announced[s["name"]] = {
            "announced_at": now_kst().isoformat(timespec="seconds"),
            "sent": bool(ok),
        }
        sent_names.append(s["name"])
    _save_ledger(ledger, dry_run)
    return sent_names


# ---------- ② 피드백 반영 ----------

def find_pending_feedback() -> list[dict]:
    """status: pending 인 피드백 노트 목록(오래된 것부터)."""
    directory = _feedback_dir()
    if not directory.exists():
        return []
    out: list[dict] = []
    for p in sorted(directory.glob("*.md"), key=lambda x: x.name):
        if p.name == "README.md":
            continue
        meta, body = parse_frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
        if str(meta.get("type", "")).strip() != "feedback":
            continue
        if str(meta.get("status", "")).strip() != "pending":
            continue
        target = str(meta.get("target", "")).strip().strip('"').strip("'")
        # 본문에서 "# 피드백 -- 대상" 머리말을 떼고 실제 지시만 남긴다.
        instruction = re.sub(r"^#\s*피드백\s*--.*?\n+", "", body.strip(),
                             count=1).strip() or body.strip()
        out.append({"path": p, "meta": meta, "target": target,
                    "instruction": instruction})
    return out


def _resolve_target(target: str) -> Path | None:
    """피드백 target(원고 파일명) → 원고 폴더 안 실제 파일."""
    if not target:
        return None
    name = Path(target).name
    if not name.endswith(".md"):
        name += ".md"
    candidate = _script_dir() / name
    if candidate.exists():
        return candidate
    # 파일명이 살짝 다를 수 있어(확장자·공백) 느슨히 한 번 더 찾는다.
    stem = Path(name).stem
    for p in _script_dir().glob("*.md"):
        if p.stem == stem:
            return p
    return None


def _mark_feedback(fb: dict, status: str, note: str, dry_run: bool) -> None:
    """피드백 노트의 status를 갱신한다(pending → applied/error). 프론트매터 보존."""
    if dry_run:
        return
    path: Path = fb["path"]
    raw_fm, body = _split_raw(path.read_text(encoding="utf-8", errors="ignore"))
    meta, _ = parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
    stamp = now_kst().isoformat(timespec="seconds")
    # status 줄만 치환하고 처리 흔적을 프론트매터에 덧붙인다(원문 순서 최대한 보존).
    if re.search(r"^status:.*$", raw_fm, flags=re.MULTILINE):
        raw_fm = re.sub(r"^status:.*$", f"status: {status}", raw_fm,
                        count=1, flags=re.MULTILINE)
    else:
        raw_fm = raw_fm.rstrip("\n") + f"\nstatus: {status}\n"
    # 닫는 --- 앞에 처리 메타를 삽입한다.
    extra = f"applied_at: {stamp}\napplied_by: orchestrator\n"
    if note:
        extra += f"applied_note: {note}\n"
    raw_fm = re.sub(r"\n---\s*\n?$", "\n" + extra + "---\n", raw_fm, count=1)
    path.write_text(raw_fm + body, encoding="utf-8")


def apply_one(fb: dict, dry_run: bool) -> str:
    """피드백 1건을 대상 원고에 반영한다. 결과 상태 문자열을 반환한다."""
    target_path = _resolve_target(fb["target"])
    if target_path is None:
        _mark_feedback(fb, "error", f"대상 원고 없음: {fb['target']}", dry_run)
        log_line(f"피드백 반영 실패(대상 없음): {fb['target']}", dry_run=dry_run)
        return "unresolved"
    if not fb["instruction"]:
        _mark_feedback(fb, "error", "수정 지시 없음", dry_run)
        return "empty"

    raw_fm, body = _split_raw(
        target_path.read_text(encoding="utf-8", errors="ignore"))
    original = body.strip()
    if dry_run:
        log_line(f"[계획] 피드백 반영: {target_path.name} ← {fb['path'].name}",
                 dry_run=True)
        return "planned"

    revised = _strip_fences(llm.call_writing(
        prompts.SCRIPT_REVISE.format(
            script=original[:40000], feedback=fb["instruction"][:4000]),
        max_tokens=16000,
    )).strip()

    # 내용 유실 방어: 너무 짧거나 원본 대비 절반 미만이면 반영하지 않는다.
    if len(revised) < MIN_SCRIPT_CHARS or len(revised) < len(original) * MIN_KEEP_RATIO:
        _mark_feedback(fb, "error",
                       f"수정 결과가 비정상적으로 짧음({len(revised)}/{len(original)}자)",
                       dry_run=False)
        log_line(f"피드백 반영 보류(짧은 결과): {target_path.name}")
        telegram_notify.send(
            f"⚠️ 원고 수정 실패(결과가 너무 짧아 보류): {target_path.name}\n"
            f"피드백 노트를 확인하세요.")
        return "too_short"

    stamp = now_kst().strftime("%Y-%m-%d %H:%M")
    audit = f"\n\n<!-- 🔁 수정 반영 {stamp}: {fb['path'].name} -->\n"
    target_path.write_text(raw_fm + revised + audit, encoding="utf-8")
    _mark_feedback(fb, "applied", f"원고 반영 완료: {target_path.name}", dry_run=False)
    log_line(f"피드백 반영 완료: {target_path.name} ← {fb['path'].name}")
    telegram_notify.send(
        f"✅ 원고 수정 반영 완료: {target_path.name}\n"
        f"요청: {fb['instruction'][:200]}\n"
        "볼트 05 리뷰/대기에서 확인하세요.")
    return "applied"


def apply_pending_feedback(dry_run: bool, max_items: int = DEFAULT_MAX) -> dict:
    """대기 중인 피드백을 반영한다. 결과 카운트 dict 반환."""
    pending = find_pending_feedback()[:max_items]
    counts: dict[str, int] = {}
    for fb in pending:
        try:
            result = apply_one(fb, dry_run)
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 전체를 막으면 안 됨
            result = "failed"
            if not dry_run:
                _mark_feedback(fb, "error", f"처리 예외: {type(e).__name__}", dry_run=False)
            log_line(f"피드백 반영 예외({fb['path'].name}): {e}", dry_run=dry_run)
        counts[result] = counts.get(result, 0) + 1
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(
        description="원고 수정·보완 핑퐁(오케스트레이터 쪽): 초안 알림 + 피드백 반영")
    ap.add_argument("--dry-run", action="store_true",
                    help="대상만 출력하고 볼트에 쓰지 않음")
    ap.add_argument("--announce-only", action="store_true",
                    help="① 새 원고 알림만")
    ap.add_argument("--apply-only", action="store_true",
                    help="② 피드백 반영만")
    ap.add_argument("--max", type=int, default=DEFAULT_MAX,
                    help="한 번에 알리거나 반영할 최대 건수")
    args = ap.parse_args()

    do_announce = not args.apply_only
    do_apply = not args.announce_only

    announced: list[str] = []
    if do_announce:
        announced = announce_new_scripts(args.dry_run, args.max)
    counts: dict[str, int] = {}
    if do_apply:
        counts = apply_pending_feedback(args.dry_run, args.max)

    log_line(
        f"원고 핑퐁 완료: 새 원고 알림 {len(announced)}건, "
        f"피드백 반영 {counts.get('applied', 0)}건"
        + (f", 미해결 {counts.get('unresolved', 0)}건" if counts.get('unresolved') else ""),
        dry_run=args.dry_run)


if __name__ == "__main__":
    main()
