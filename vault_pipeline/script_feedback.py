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
from urllib.parse import quote

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
# 이 상태의 원고는 이미 끝난 것으로 보고 알리지 않는다.
DONE_STATES = {"발행완료", "발행됨", "완료", "보류", "폐기"}
# youtube-script 외 형식(스레드/릴스/뉴스레터 등)은 생성일이 이 일수 안일 때만 알린다 —
# 폴더에 수백 건 쌓인 옛 백로그가 확대 적용 첫날 알림으로 쏟아지는 것을 막는다.
ANNOUNCE_MAX_AGE_DAYS = int(os.getenv("DG_ANNOUNCE_MAX_AGE_DAYS") or "7")

# 파이프라인 카드(스레드/뉴스레터 → 카드뉴스) 피드백 — target이 카드 ID면 원고 파일 대신
# 카드의 수정 요청 경로(재초안)로 보낸다. 섹션 이름은 orchestrator run.py와 같아야
# handle_revision_requested가 지시를 읽는다.
CARD_ID_RE = re.compile(r"DG-\d{4}-\d{4}")
REVISION_SECTION = "📝 수정 요청"


def _active_cards_dir() -> Path:
    return vault_root() / "파이프라인" / "활성"


def _script_dir() -> Path:
    rel = os.getenv("VAULT_SCRIPT_PATH", SCRIPT_DIR_DEFAULT).strip("/")
    return vault_root() / rel


def _feedback_dir() -> Path:
    rel = os.getenv("VAULT_FEEDBACK_PATH", FEEDBACK_DIR_DEFAULT).strip("/")
    return vault_root() / rel


# 링크 생성용 설정(볼트=옵시디언 볼트=git 저장소의 vault/ 폴더).
GITHUB_REPO = os.getenv("DG_GITHUB_REPO", "dream0grow/dream-grow-content-automation")
GITHUB_BRANCH = os.getenv("DG_GITHUB_BRANCH", "main")
# 저장소 안에서 볼트 루트가 놓인 폴더(옵시디언 볼트 루트 = 이 폴더).
REPO_VAULT_PREFIX = os.getenv("DG_VAULT_REPO_PREFIX", "vault")
# 옵시디언 앱에서 열기용 vault 이름(사용자 볼트 이름). 없으면 옵시디언 링크는 생략.
OBSIDIAN_VAULT = os.getenv("DG_OBSIDIAN_VAULT", "").strip()


def script_links(name: str) -> str:
    """원고 파일명 → 클릭 가능한 링크 묶음(GitHub 웹 + 옵시디언). 텔레그램이 자동 링크한다.

    - GitHub: 웹에서 바로 원고를 본다(항상 포함).
    - 옵시디언: DG_OBSIDIAN_VAULT가 설정돼 있으면 앱에서 열기 링크도 추가한다.
    """
    script_rel = os.getenv("VAULT_SCRIPT_PATH", SCRIPT_DIR_DEFAULT).strip("/")
    in_vault_path = f"{script_rel}/{name}"                 # 옵시디언 볼트 기준 경로
    in_repo_path = f"{REPO_VAULT_PREFIX}/{in_vault_path}"  # git 저장소 기준 경로
    gh = (f"https://github.com/{GITHUB_REPO}/blob/{GITHUB_BRANCH}/"
          + quote(in_repo_path, safe="/"))
    lines = [f"🔗 GitHub: {gh}"]
    if OBSIDIAN_VAULT:
        obs = (f"obsidian://open?vault={quote(OBSIDIAN_VAULT)}"
               f"&file={quote(in_vault_path, safe='')}")
        lines.append(f"🟣 옵시디언: {obs}")
    return "\n".join(lines)


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
        # 빈 값은 YAML이 None으로 파싱하므로 `or ""`로 받는다 (스레드 파일 다수가 빈 검수상태).
        if str(meta.get("상태") or "").strip() in DONE_STATES:
            continue
        if str(meta.get("검수상태") or "").strip() not in PENDING_REVIEW:
            continue
        # youtube-script 외 형식(스레드/릴스 등)은 생성일이 최근일 때만 알린다.
        if (str(meta.get("type", "")).strip() != "youtube-script"
                and not _created_recently(meta)):
            continue
        out.append({"name": p.name, "path": p, "meta": meta})
    return out


def _created_recently(meta: dict) -> bool:
    """frontmatter 생성일 기준 최근 여부.

    Actions 체크아웃은 파일 mtime을 매번 초기화하므로 mtime은 신뢰할 수 없다 —
    생성일이 없거나 파싱이 안 되면 옛 백로그로 보고 알리지 않는다.
    """
    raw = str(meta.get("생성일") or meta.get("created") or "").strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if not m:
        return False
    now = now_kst()
    try:
        created = now.replace(year=int(m.group(1)), month=int(m.group(2)),
                              day=int(m.group(3)), hour=0, minute=0,
                              second=0, microsecond=0)
    except ValueError:
        return False
    return (now - created).days <= ANNOUNCE_MAX_AGE_DAYS


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
            f"원고: {s['name']}\n"
            f"{script_links(s['name'])}\n\n"
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


def _resolve_card(target: str) -> Path | None:
    """피드백 target에서 카드 ID(DG-YYYY-NNNN)를 찾아 활성 카드 파일로 푼다."""
    m = CARD_ID_RE.search(target or "")
    if not m:
        return None
    matches = sorted(_active_cards_dir().glob(f"{m.group(0)}*.md"))
    return matches[0] if matches else None


def _apply_card_revision(fb: dict, card_path: Path, dry_run: bool) -> str:
    """파이프라인 카드에 수정 요청을 기록하고 재초안 경로로 되돌린다.

    원고 파일과 달리 여기서 LLM을 부르지 않는다 — approval_status를
    revision_requested로 바꿔두면 오케스트레이터 handle_revision_requested가
    REVISION_SECTION의 지시를 작가에게 되먹여 재초안한다.
    """
    if not fb["instruction"]:
        _mark_feedback(fb, "error", "수정 지시 없음", dry_run)
        return "empty"
    if dry_run:
        log_line(f"[계획] 카드 수정 요청: {card_path.name} ← {fb['path'].name}",
                 dry_run=True)
        return "planned"
    stamp = now_kst().strftime("%Y-%m-%d %H:%M")
    with card_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {REVISION_SECTION} — {stamp}\n\n"
                f"{fb['instruction'].rstrip()}\n")
    text = card_path.read_text(encoding="utf-8")
    if re.search(r"^approval_status:", text, flags=re.MULTILINE):
        text = re.sub(r"^approval_status:.*$",
                      "approval_status: revision_requested",
                      text, count=1, flags=re.MULTILINE)
        card_path.write_text(text, encoding="utf-8")
    card_id = CARD_ID_RE.search(card_path.name).group(0)
    _mark_feedback(fb, "applied", f"카드 수정 요청 기록: {card_path.name}",
                   dry_run=False)
    log_line(f"카드 수정 요청 접수: {card_path.name} ← {fb['path'].name}")
    telegram_notify.send(
        f"📝 [{card_id}] 수정 요청 접수 — 다음 실행에서 재초안하고, "
        f"완성되면 다시 알립니다.\n요청: {fb['instruction'][:200]}")
    return "applied"


def apply_one(fb: dict, dry_run: bool) -> str:
    """피드백 1건을 대상(원고 파일 또는 파이프라인 카드)에 반영한다."""
    card_path = _resolve_card(fb["target"])
    if card_path is not None:
        return _apply_card_revision(fb, card_path, dry_run)
    target_path = _resolve_target(fb["target"])
    if target_path is None:
        _mark_feedback(fb, "error", f"대상 원고 없음: {fb['target']}", dry_run)
        log_line(f"피드백 반영 실패(대상 없음): {fb['target']}", dry_run=dry_run)
        return "unresolved"
    # 열람 사본(스레드_/뉴스레터_ — frontmatter content_id 보유)이면 원본 카드의
    # 수정 요청으로 라우팅한다 — 사본을 고쳐 봐야 발행에 반영되지 않기 때문.
    meta, _ = parse_frontmatter(
        target_path.read_text(encoding="utf-8", errors="ignore"))
    linked_card = _resolve_card(str(meta.get("content_id") or ""))
    if linked_card is not None:
        return _apply_card_revision(fb, linked_card, dry_run)
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
        f"{script_links(target_path.name)}\n"
        f"요청: {fb['instruction'][:200]}")
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
