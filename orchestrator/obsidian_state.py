"""옵시디언 볼트 카드 저장소 — 파이프라인의 유일한 저장소 (노션 철수 완료)

카드 = `vault/파이프라인/활성/<content_id> <topic>.md`
- frontmatter = 라우팅 속성 (stage, status, approval_status …)
- 본문 `## 제목 — 타임스탬프` 섹션 = 단계 산출물
- page_id = 저장소 루트 기준 카드 파일 상대경로 문자열

공개 함수는 `orchestrator.state` 파사드를 통해 run.py 등 호출처에 노출된다.
승인은 사람이 옵시디언/텔레그램에서 frontmatter를 바꾸는 것으로 이뤄진다.
"""
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))

SELECT_FIELDS = {"stage", "status", "priority", "approval_status", "review_status"}
TEXT_FIELDS = {
    "content_id", "audience", "approved_keyword",
    "manus_task_ids", "idempotency_key", "last_error",
}
ALL_FIELDS = SELECT_FIELDS | TEXT_FIELDS | {"published_url"}


def _vault() -> Path:
    return Path(os.getenv("DG_VAULT_ROOT", str(PROJECT_ROOT / "vault")))


def _active_dir() -> Path:
    return _vault() / "파이프라인" / "활성"


def _done_dir() -> Path:
    return _vault() / "파이프라인" / "발행완료"


def require_backend() -> None:
    """볼트 준비 — 카드 폴더만 있으면 된다 (외부 키 불필요)."""
    _active_dir().mkdir(parents=True, exist_ok=True)
    _done_dir().mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def _resolve(page_id: str) -> Path:
    """page_id(저장소 상대경로 또는 절대경로) → 절대경로. 발행완료도 찾는다."""
    raw = Path(page_id)
    for candidate in (raw if raw.is_absolute() else PROJECT_ROOT / page_id,
                      _done_dir() / raw.name, _active_dir() / raw.name):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"카드 없음: {page_id}")


def _rel(path: Path) -> str:
    """카드 식별자(page_id). 저장소 안이면 상대경로, 밖(테스트 등)이면 절대경로."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _split(text: str) -> tuple[dict, str]:
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


def _dump(meta: dict, body: str) -> str:
    fm = yaml.safe_dump({k: ("" if v is None else v) for k, v in meta.items()},
                        allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm}\n---\n{body if body.startswith(chr(10)) else chr(10) + body}"


def _card_from_file(path: Path) -> dict:
    meta, _ = _split(path.read_text(encoding="utf-8", errors="ignore"))
    get = lambda k: str(meta.get(k, "") or "")
    return {
        "page_id": _rel(path),
        "created_time": get("created_time"),
        "last_edited_time": get("last_edited_time"),
        "topic": get("topic"),
        "content_id": get("content_id"),
        "stage": get("stage"),
        "status": get("status"),
        "audience": get("audience"),
        "format": get("format"),
        "priority": get("priority"),
        "approval_status": get("approval_status"),
        "review_status": get("review_status"),
        "approved_keyword": get("approved_keyword"),
        "manus_task_ids": get("manus_task_ids"),
        "idempotency_key": get("idempotency_key"),
        "published_url": get("published_url"),
    }


# ---------- 조회 ----------

def age_minutes(card: dict) -> float:
    ts = card.get("last_edited_time") or card.get("created_time")
    if not ts:
        return 9999.0
    try:
        dt = datetime.strptime(str(ts), "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        return (datetime.now(KST) - dt).total_seconds() / 60
    except ValueError:
        return 9999.0


def query_cards(stage: str | None = None, status: str | None = None,
                approval_status: str | None = None, page_size: int = 20) -> list[dict]:
    """stage/status/approval 조합으로 활성 카드를 조회한다 (파일 스캔)."""
    require_backend()
    cards = []
    for p in sorted(_active_dir().glob("*.md")):
        if p.name == "README.md":
            continue
        card = _card_from_file(p)
        if stage and card["stage"] != stage:
            continue
        if status and card["status"] != status:
            continue
        if approval_status and card["approval_status"] != approval_status:
            continue
        cards.append(card)
        if len(cards) >= page_size:
            break
    return cards


# ---------- 갱신 ----------

def update_card(page_id: str, **fields) -> None:
    unknown = set(fields) - ALL_FIELDS
    if unknown:
        raise ValueError(f"알 수 없는 필드: {', '.join(sorted(unknown))}")
    path = _resolve(page_id)
    text = path.read_text(encoding="utf-8")
    meta, body = _split(text)
    for k, v in fields.items():
        meta[k] = v if v is not None else ""
    meta["last_edited_time"] = _now()
    path.write_text(_dump(meta, body), encoding="utf-8")


def next_content_id() -> str:
    """DG-YYYY-NNNN 채번 — 활성+발행완료 파일명·frontmatter 최대값+1."""
    require_backend()
    year = datetime.now(KST).year
    pat = re.compile(rf"DG-{year}-(\d{{4}})")
    max_n = 0
    for d in (_active_dir(), _done_dir()):
        for p in d.glob("*.md"):
            for m in pat.finditer(p.name):
                max_n = max(max_n, int(m.group(1)))
    return f"DG-{year}-{max_n + 1:04d}"


def create_card(topic: str, *, stage: str = "intake", status: str = "queued",
                audience: str = "", body: str = "") -> str:
    """새 콘텐츠 카드를 생성하고 page_id(상대경로)를 반환한다."""
    require_backend()
    content_id = next_content_id()
    safe_topic = re.sub(r'[\\/:*?"<>|#^\[\]\n\r\t]', " ", topic).strip()[:60]
    path = _active_dir() / f"{content_id} {safe_topic}.md"
    meta = {
        "topic": topic, "content_id": content_id,
        "stage": stage, "status": status,
        "format": "", "audience": audience, "priority": "",
        "approval_status": "", "review_status": "",
        "approved_keyword": "", "manus_task_ids": "", "idempotency_key": "",
        "last_error": "", "published_url": "",
        "created_time": _now(), "last_edited_time": _now(),
    }
    path.write_text(_dump(meta, ""), encoding="utf-8")
    page_id = _rel(path)
    if body:
        append_section(page_id, "📋 상세", body)
    return page_id


# ---------- 본문 섹션 (단계 산출물) ----------

def append_section(page_id: str, heading: str, body: str) -> None:
    path = _resolve(page_id)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {heading} — {_now()}\n\n{body.rstrip()}\n")


def append_formatted_section(page_id: str, heading: str, markdown: str) -> None:
    """옵시디언은 md 원문이 곧 서식이다."""
    append_section(page_id, heading, markdown)


def read_sections(page_id: str) -> str:
    path = _resolve(page_id)
    _, body = _split(path.read_text(encoding="utf-8", errors="ignore"))
    return body.strip()


def read_latest_section(page_id: str, heading_prefix: str) -> str:
    """같은 접두사의 섹션 중 마지막 것의 본문을 반환한다 (없으면 빈 문자열)."""
    body = read_sections(page_id)
    sections = re.split(r"^## ", body, flags=re.MULTILINE)
    latest = ""
    for sec in sections:
        if sec.startswith(heading_prefix):
            latest = sec.split("\n", 1)[1] if "\n" in sec else ""
    return latest.strip()


def read_sections_by_prefix(page_id: str, *prefixes: str) -> str:
    """heading이 주어진 접두사 중 하나로 시작하는 섹션들만 골라 읽는다(B3).

    다음 단계에 카드 본문 전체 대신 필요한 섹션만 주입해 토큰을 아낀다.
    접두사가 없으면 전체를 읽는다.
    """
    if not prefixes:
        return read_sections(page_id)
    body = read_sections(page_id)
    out: list[str] = []
    for sec in re.split(r"^## ", body, flags=re.MULTILINE):
        sec = sec.strip()
        if sec and any(sec.startswith(p) for p in prefixes):
            out.append("## " + sec)
    return "\n\n".join(out)


# ---------- 알림 ----------

def notify(page_id: str, message: str) -> None:
    """텔레그램 폰 알림 + 결재함 기록. 알림에서 바로 카드를 열 수 있게 링크를 붙인다."""
    card_name = Path(page_id).stem
    try:
        from vault_pipeline import telegram_notify
        link = ""
        try:
            rel = _resolve(page_id).relative_to(_vault()).as_posix()
            link = f"\n🔗 {telegram_notify.note_url(rel)}"
        except Exception:  # noqa: BLE001 — 링크는 부가 정보, 못 만들면 생략
            pass
        telegram_notify.send(f"📱[콘텐츠] {card_name}\n{message[:1500]}{link}")
    except Exception as e:  # noqa: BLE001 — 알림 실패가 파이프라인을 멈추면 안 됨
        print(f"텔레그램 알림 실패 (계속 진행): {e}")
    try:
        queue = _vault() / "_system" / "review_queue.md"
        queue.parent.mkdir(parents=True, exist_ok=True)
        with queue.open("a", encoding="utf-8") as f:
            f.write(f"\n- [ ] {_now()} [[{card_name}]] — {message[:300]}\n")
    except OSError as e:
        print(f"결재함 기록 실패 (계속 진행): {e}")
