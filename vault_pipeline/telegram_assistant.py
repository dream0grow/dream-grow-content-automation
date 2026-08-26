"""텔레그램 비서 — 일반 메시지(후보 노트)를 AI가 판단·실행·답장하는 모듈.

텔레그램 봇의 일반 메시지(알림 답장 아님)는 yt_research 웹훅이
`_system/candidates/telegram/`에 `status: candidate` 노트로 저장만 한다.
이 모듈은 orchestrator cron에서 그 미처리 노트를 읽어:

  ① LLM 의도 판별(`prompts.TELEGRAM_ASSISTANT`) — 메시지 하나에 섞인 여러 요청을 액션 목록으로.
  ② 실행:
     - revise    → `_system/feedback/`에 pending 피드백 노트 생성 — 같은 orchestrator 실행의
                   script_feedback 단계가 기존 안전장치(프론트매터 보존·유실 감지·완료 통지)로 반영.
                   target은 웹훅이 추정한 「참고 후보」 안에서만 고르고, 해석 실패 시 확인 질문으로 폴백.
     - recommend → `reels_recommend.run(count)` 즉시 호출(자체 전송·장부 기록).
     - answer    → 텔레그램 답장.
     - idea      → 실행 없음. 후보 노트를 그대로 두어 기존 승격 검토 흐름을 해치지 않는다.
  ③ 마감: 실행한 노트는 `status: processed` + 처리 결과 기록. idea만 있으면 status 유지.
     어느 쪽이든 장부(`_system/logs/telegram_assistant_ledger.json`)에 남겨 재판정을 막는다.

안전:
  - LLM 실패 시 노트를 건너뛴다(장부 미기록 → 다음 실행 재시도).
  - 원고를 직접 고치지 않는다 — 수정은 전부 script_feedback 경로로만.
  - `--dry-run`은 판정만 출력하고 쓰기/전송을 하지 않는다.

실행:
    python3 -m vault_pipeline.telegram_assistant
    python3 -m vault_pipeline.telegram_assistant --dry-run
"""
import argparse
import json
import re
from pathlib import Path

from vault_pipeline import prompts, reels_recommend, telegram_notify
from vault_pipeline.script_feedback import CARD_ID_RE, _resolve_target
from vault_pipeline.vault_io import log_line, now_kst, parse_frontmatter, vault_root

from orchestrator import llm

CANDIDATE_DIR = "_system/candidates/telegram"
FEEDBACK_DIR = "_system/feedback"
# 한 실행에 처리할 최대 노트 수(백로그 폭주 방지).
DEFAULT_MAX = 5
VALID_KINDS = {"revise", "recommend", "answer", "idea"}


def _candidate_dir() -> Path:
    return vault_root() / CANDIDATE_DIR


def _feedback_dir() -> Path:
    return vault_root() / FEEDBACK_DIR


def _ledger_path() -> Path:
    return vault_root() / "_system" / "logs" / "telegram_assistant_ledger.json"


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


def _split_note(body: str) -> tuple[str, list[str]]:
    """노트 본문 → (사용자 메시지, 참고 후보 경로 목록)."""
    refs: list[str] = []
    m = re.search(r"^##\s*참고 후보.*$", body, flags=re.MULTILINE)
    if m:
        tail = body[m.end():]
        refs = [ln.strip().lstrip("- ").strip()
                for ln in tail.splitlines() if ln.strip().startswith("- ")]
        body = body[:m.start()]
    # 첫 제목(# 메시지 요약)을 떼고 실제 메시지만 남긴다.
    message = re.sub(r"^#\s+.*?\n+", "", body.strip(), count=1).strip()
    return message or body.strip(), refs


def find_pending_notes() -> list[dict]:
    """아직 판정하지 않은 텔레그램 후보 노트(오래된 것부터)."""
    directory = _candidate_dir()
    if not directory.exists():
        return []
    ledger = _load_ledger()
    seen = set(ledger.get("notes", {}).keys())
    out: list[dict] = []
    for p in sorted(directory.glob("*.md"), key=lambda x: x.name):
        if p.name == "README.md" or p.name in seen:
            continue
        meta, body = parse_frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
        if str(meta.get("status") or "").strip() != "candidate":
            continue
        if str(meta.get("출처") or "").strip() != "telegram":
            continue
        message, refs = _split_note(body)
        out.append({"name": p.name, "path": p, "meta": meta,
                    "message": message, "refs": refs})
    return out


def triage(note: dict) -> list[dict]:
    """LLM 의도 판별 → 유효한 액션 목록. 실패 시 ValueError."""
    candidates = "\n".join(f"- {r}" for r in note["refs"]) or "(없음)"
    prompt = prompts.TELEGRAM_ASSISTANT.format(
        today=now_kst().strftime("%Y-%m-%d (%a)"),
        candidates=candidates,
        message=note["message"],
    )
    obj = llm.call_json(prompt)
    actions = obj.get("actions") or []
    valid = [a for a in actions if isinstance(a, dict)
             and str(a.get("kind") or "").strip() in VALID_KINDS]
    if not valid:
        raise ValueError(f"유효한 액션 없음: {actions!r}")
    return valid


def _valid_revise_target(target: str) -> bool:
    """target이 실제 원고 파일이나 카드 ID로 해석되는지."""
    if not target:
        return False
    if CARD_ID_RE.search(target):
        return True
    return _resolve_target(target) is not None


def _create_feedback_note(target: str, instruction: str, dry_run: bool) -> str:
    """script_feedback이 집는 pending 피드백 노트를 만든다. 파일명 반환."""
    stamp = now_kst()
    safe_target = Path(target).stem[:60]
    name = f"{stamp.strftime('%Y-%m-%d %H%M%S')} {safe_target} 피드백.md"
    content = (
        "---\n"
        "type: feedback\n"
        f'target: "{target}"\n'
        "status: pending\n"
        "출처: telegram_assistant\n"
        "author: 이한결(구술)\n"
        f"created: {stamp.strftime('%Y-%m-%d')}\n"
        "tags: [피드백, 수정요청]\n"
        "---\n\n"
        f"# 피드백 -- {target}\n\n"
        f"{instruction.strip()}\n"
    )
    if not dry_run:
        _feedback_dir().mkdir(parents=True, exist_ok=True)
        (_feedback_dir() / name).write_text(content, encoding="utf-8")
    return name


def _mark_processed(note: dict, results: list[str], dry_run: bool) -> None:
    """실행한 후보 노트를 status: processed로 마감하고 처리 결과를 남긴다."""
    if dry_run:
        return
    path: Path = note["path"]
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"^status:\s*candidate\s*$", "status: processed", text,
                  count=1, flags=re.MULTILINE)
    stamp = now_kst().strftime("%Y-%m-%d %H:%M")
    text += (f"\n\n## 처리 결과 ({stamp}, telegram_assistant)\n"
             + "\n".join(f"- {r}" for r in results) + "\n")
    path.write_text(text, encoding="utf-8")


def process_note(note: dict, dry_run: bool) -> bool:
    """노트 하나 처리. 장부에 기록할지(=판정 완료) 반환."""
    try:
        actions = triage(note)
    except Exception as e:  # noqa: BLE001 — 판정 실패는 다음 실행에 재시도
        log_line(f"텔레그램 비서: 판정 실패, 건너뜀 — {note['name']} ({e})",
                 dry_run=dry_run)
        return False
    results: list[str] = []
    replies: list[str] = []
    for a in actions:
        kind = str(a.get("kind")).strip()
        if kind == "revise":
            target = str(a.get("target") or "").strip()
            instruction = str(a.get("instruction") or "").strip()
            if not instruction or not _valid_revise_target(target):
                replies.append("어느 원고를 고칠지 못 찾았어요. 원고 알림 메시지에 "
                               "답장으로 보내주시면 정확히 반영됩니다.")
                results.append(f"revise 해석 실패(target={target!r}) → 확인 질문")
                continue
            fb_name = _create_feedback_note(target, instruction, dry_run)
            replies.append(f"'{Path(target).stem}' 수정 요청으로 접수했어요. "
                           "이번 파이프라인 실행에서 반영되고 완료되면 알려드릴게요.")
            results.append(f"revise → 피드백 노트 {fb_name}")
        elif kind == "recommend":
            try:
                count = max(1, int(a.get("count") or 3))
            except (TypeError, ValueError):
                count = 3
            sent = [] if dry_run else reels_recommend.run(count=count)
            results.append(f"recommend {count}편 → {len(sent)}편 전송")
        elif kind == "answer":
            reply = str(a.get("reply") or "").strip()
            if reply:
                replies.append(reply)
                results.append("answer → 답장")
        elif kind == "idea":
            results.append("idea → 후보 유지(실행 없음)")
    executed = any(not r.startswith("idea") for r in results)
    if replies and not dry_run:
        telegram_notify.send("💬 " + "\n\n".join(replies))
    if executed:
        _mark_processed(note, results, dry_run)
    log_line(f"텔레그램 비서{'(dry)' if dry_run else ''}: {note['name']} → "
             + "; ".join(results), dry_run=dry_run)
    return True


def run(dry_run: bool = False, max_items: int = DEFAULT_MAX) -> int:
    """미처리 후보 노트를 처리한다. 판정 완료 건수 반환."""
    notes = find_pending_notes()[:max_items]
    if not notes:
        log_line("텔레그램 비서: 미처리 메시지 없음", dry_run=dry_run)
        return 0
    ledger = _load_ledger()
    done = 0
    for note in notes:
        if process_note(note, dry_run):
            ledger.setdefault("notes", {})[note["name"]] = {
                "processed_at": now_kst().isoformat(timespec="seconds"),
            }
            done += 1
    if done:
        _save_ledger(ledger, dry_run)
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description="텔레그램 일반 메시지 AI 비서")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=DEFAULT_MAX)
    args = ap.parse_args()
    run(dry_run=args.dry_run, max_items=args.max)


if __name__ == "__main__":
    main()
