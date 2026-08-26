"""릴스 원고 자동 추천 — 매일 아침 TOP 3를 텔레그램으로 (월~금).

`05 리뷰/대기`의 릴스 원고 중 아직 안 찍은 것(상태가 발행완료 등이 아닌 것)을 모아
LLM이 후킹 강도·공감 폭·오늘 날짜 기준 시의성으로 TOP N(기본 3)을 고른다.

- **로테이션**: 추천 이력을 장부(`_system/logs/reels_recommend_ledger.json`)에 남겨
  다음 회차엔 아직 추천 안 한 원고를 우선한다. 미추천분이 N개 미만이면
  가장 오래전에 추천된 원고부터 다시 후보에 올린다(전량 소진 후 순환).
- **완료 처리 연동**: 사용자가 촬영한 원고를 `상태: 발행완료`로 바꾸거나
  `05 리뷰/완료/`로 옮기면(이 모듈은 대기 폴더만 스캔) 후보에서 자동 제외된다.
- **안전**: LLM 실패 시 추천을 보내지 않고 로그만 남긴다(다음 실행에 재시도).
  텔레그램 전송이 실제로 성공했을 때만 장부에 기록해, 미발송 원고가
  추천 기회를 잃지 않게 한다.

실행:
    python3 -m vault_pipeline.reels_recommend              # 추천 + 텔레그램 전송
    python3 -m vault_pipeline.reels_recommend --dry-run    # 후보·선정만 출력, 전송/기록 없음
    python3 -m vault_pipeline.reels_recommend --count 3
"""
import argparse
import json
import re
from pathlib import Path

from vault_pipeline import telegram_notify
from vault_pipeline.script_feedback import DONE_STATES, _script_dir, script_links
from vault_pipeline.vault_io import log_line, now_kst, parse_frontmatter, vault_root

from orchestrator import llm

DEFAULT_COUNT = 3
# LLM에 넘기는 후보 상한 — 미추천 원고가 이보다 많아도 프롬프트가 터지지 않게 한다.
MAX_POOL = 60
REELS_CHANNELS = {"reels", "릴스"}
NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

SYSTEM = (
    "너는 초등 학부모 대상 교육 브랜드 '드림그로우'의 릴스 콘텐츠 전략가다. "
    "인스타그램 릴스에서 조회수가 잘 나올 원고를 고른다."
)

CRITERIA = """선정 기준 (드림그로우 후킹 원칙):
- 후킹 강도: 첫 문장이 통념을 깨거나 호기심 갭을 만드는가 (인사말·배경 설명 시작은 감점)
- 공감 폭: 초등 학부모 다수가 "내 얘기다" 할 보편적 고민인가 (좁은 주제는 감점)
- 시의성: 오늘 날짜 기준 계절·학사 일정(개학, 방학, 시험, 새 학년 등)과 맞물리는가
- 구체성: 교실 장면·실측 사례·실천법이 있는가
- 금지: 공포·과장·죄책감 유발 훅은 높게 평가하지 않는다 (브랜드 톤 위반)"""


def _ledger_path() -> Path:
    return vault_root() / "_system" / "logs" / "reels_recommend_ledger.json"


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


def _is_reels(name: str, meta: dict) -> bool:
    if name.startswith("원고_릴스_"):
        return True
    return str(meta.get("채널") or "").strip().lower() in REELS_CHANNELS


def extract_hook(body: str) -> str:
    """원고 본문에서 0~3초 후킹 대사를 뽑는다. 못 찾으면 첫 실문장."""
    m = re.search(r"후킹[^\n]*\n(.*?)(?=\n\*\*|\n##|\n\(화면|\Z)", body, re.DOTALL)
    if m:
        lines = [ln.strip() for ln in m.group(1).strip().splitlines()
                 if ln.strip() and not ln.strip().startswith(("(화면", "*(화면", "> (화면"))]
        if lines:
            return " ".join(lines)[:200]
    for ln in body.splitlines():
        ln = ln.strip().lstrip("> ")
        if ln and not ln.startswith(("#", "**", "---", "(")):
            return ln[:200]
    return ""


def find_candidates() -> list[dict]:
    """대기 폴더의 릴스 원고 중 아직 안 끝난 것(발행완료 등 제외)."""
    directory = _script_dir()
    if not directory.exists():
        return []
    out: list[dict] = []
    for p in sorted(directory.glob("*.md")):
        if p.name == "README.md":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        meta, body = parse_frontmatter(text)
        if not _is_reels(p.name, meta):
            continue
        if str(meta.get("상태") or "").strip() in DONE_STATES:
            continue
        out.append({
            "name": p.name,
            "topic": str(meta.get("주제") or "").strip() or p.stem,
            "category": str(meta.get("카테고리") or "").strip(),
            "hook": extract_hook(body),
        })
    return out


def build_pool(candidates: list[dict], ledger: dict, count: int) -> list[dict]:
    """미추천 원고 우선. 부족하면 가장 오래전에 추천된 원고로 채운다(순환)."""
    recommended = ledger.get("recommended", {})
    fresh = [c for c in candidates if c["name"] not in recommended]
    if len(fresh) >= count:
        return fresh[:MAX_POOL]
    seen = sorted((c for c in candidates if c["name"] in recommended),
                  key=lambda c: recommended[c["name"]].get("last_at", ""))
    return (fresh + seen)[:max(count, MAX_POOL)]


def pick_top(pool: list[dict], count: int) -> list[dict]:
    """LLM으로 TOP N 선정. 각 항목에 reason을 붙여 반환. 실패 시 ValueError."""
    lines = [f"[{i}] ({c['category'] or '기타'}) {c['topic']}\n    훅: {c['hook'] or '(없음)'}"
             for i, c in enumerate(pool)]
    today = now_kst().strftime("%Y-%m-%d (%a)")
    prompt = (
        f"오늘은 {today}. 아래 릴스 원고 후보 중 오늘 촬영하면 조회수가 가장 잘 나올 "
        f"TOP {count}을 골라라.\n\n{CRITERIA}\n\n후보 목록:\n" + "\n".join(lines)
        + "\n\nJSON만 출력: {\"picks\": [{\"index\": 후보번호, \"reason\": \"선정 이유 한두 문장"
          "(훅·공감 폭·시의성 근거를 구체적으로)\"}]}"
        + f" — picks는 정확히 {count}개, 순위순."
    )
    obj = llm.call_json(prompt, system=SYSTEM)
    picks = obj.get("picks") or []
    out: list[dict] = []
    used: set[int] = set()
    for p in picks:
        try:
            idx = int(p.get("index"))
        except (TypeError, ValueError):
            continue
        if idx in used or not (0 <= idx < len(pool)):
            continue
        used.add(idx)
        out.append({**pool[idx], "reason": str(p.get("reason") or "").strip()})
        if len(out) == count:
            break
    if len(out) < min(count, len(pool)):
        raise ValueError(f"LLM 선정 결과가 유효하지 않음: {picks!r}")
    return out


def build_message(picks: list[dict]) -> str:
    date = now_kst().strftime("%m/%d")
    parts = [f"🎬 오늘의 릴스 추천 TOP {len(picks)} ({date})"]
    for i, c in enumerate(picks):
        cat = f" ({c['category']})" if c["category"] else ""
        block = [f"{NUM_EMOJI[i] if i < len(NUM_EMOJI) else i + 1} {c['topic']}{cat}"]
        if c["hook"]:
            block.append(f"훅: {c['hook'][:150]}")
        if c.get("reason"):
            block.append(f"→ {c['reason']}")
        block.append(script_links(c["name"]))
        parts.append("\n".join(block))
    parts.append("📌 찍은 원고는 frontmatter를 `상태: 발행완료`로 바꾸고 "
                 "05 리뷰/완료/로 옮기면 추천에서 빠집니다.")
    return "\n\n".join(parts)


def run(count: int = DEFAULT_COUNT, dry_run: bool = False) -> list[str]:
    """추천 1회 실행. 전송(또는 dry-run 선정)된 파일명 목록 반환."""
    candidates = find_candidates()
    if not candidates:
        log_line("릴스 추천: 후보 원고 없음", dry_run=dry_run)
        return []
    ledger = _load_ledger()
    pool = build_pool(candidates, ledger, count)
    count = min(count, len(pool))
    try:
        picks = pick_top(pool, count)
    except Exception as e:  # noqa: BLE001 — 추천 실패가 워크플로우를 죽이면 안 됨
        log_line(f"릴스 추천: 선정 실패, 이번 회차 건너뜀 — {e}", dry_run=dry_run)
        return []
    msg = build_message(picks)
    if dry_run:
        log_line(f"릴스 추천(dry): {[p['name'] for p in picks]}", dry_run=True)
        print(msg)
        return [p["name"] for p in picks]
    ok = telegram_notify.send(msg)
    if not ok:
        # 미발송이면 장부에 남기지 않는다 — 내일 같은 원고가 다시 기회를 얻는다.
        log_line("릴스 추천: 텔레그램 미발송(설정 없음/실패) — 장부 기록 안 함")
        return []
    recommended = ledger.setdefault("recommended", {})
    now = now_kst().isoformat(timespec="seconds")
    for p in picks:
        entry = recommended.setdefault(p["name"], {"count": 0})
        entry["last_at"] = now
        entry["count"] = int(entry.get("count", 0)) + 1
    _save_ledger(ledger, dry_run=False)
    log_line(f"릴스 추천 전송: {[p['name'] for p in picks]}")
    return [p["name"] for p in picks]


def main() -> None:
    ap = argparse.ArgumentParser(description="릴스 원고 자동 추천 → 텔레그램")
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(count=args.count, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
