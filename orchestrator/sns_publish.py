"""05 리뷰(SNS 콘텐츠 제작 시스템) 원고 직접 발행 — 볼트 폴더 통합 1단계

지금까지 자동 발행은 `vault/파이프라인/활성` 카드만 가능했다. 이 모듈은
SNS 콘텐츠 제작 시스템의 원래 워크플로우(흐름 D: 05 리뷰 → 발행 → 64 발행완료)를
클라우드(GitHub Actions)에서 되살린다 — 옛 scheduled_publisher.py(맥 로컬 전용,
경로 하드코딩)의 후계자이며, 카드 발행 엔진(publish.py)의 안전장치를 그대로 쓴다.

동작 (orchestrator.yml cron에서 실행):
  1. `05 리뷰/대기`·`05 리뷰/완료`에서 `채널: thread|newsletter` + `상태: 리뷰완료`
     파일을 찾는다 — **상태를 리뷰완료로 바꾸는 것이 발행 승인**이다.
  2. 게이트를 통과하면 본문을 그대로 발행한다:
     - 검수 게이트: `검수상태`가 통과/자동수정완료가 아니면 `상태: 발행보류` + 통지.
     - 예약 게이트: `발행시간`(KST)이 미래면 대기, 비어 있으면 기본 예약 시각
       (DG_DEFAULT_PUBLISH_TIME, orchestrator.yml 기본 21:00)을 기입.
     - 안전장치: 예약 시각이 너무 오래 지났거나(기본 3일) 생성일이 오래된(기본 14일)
       승인은 발행하지 않고 보류 + 통지 — 옛 백로그 오발행 방지.
  3. 발행 성공 시 `상태: 발행완료` + `발행링크` 기입 후 파일을
     `06 제작/64 발행완료/`로 옮기고 텔레그램으로 알린다.
  4. content_id가 있는 파일(파이프라인 카드의 열람 사본)은 사본 본문(사용자가
     폰에서 고친 내용 포함)을 발행하고, 원본 카드도 published로 동기화해
     이중 발행을 막는다.

프론트매터는 원문을 그대로 보존하고 필요한 줄만 바꾼다 — 주제에 콜론이 들어가
YAML 파싱이 깨지는 파일이 실측 39건이라, 파싱은 줄 단위 관대(lenient)하게 한다.

실행:
    python3 -m orchestrator.sns_publish             # 승인분 발행 (cron이 호출)
    python3 -m orchestrator.sns_publish --dry-run   # 계획만 출력
    python3 -m orchestrator.sns_publish --list      # 승인/예약 현황
"""
import argparse
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from orchestrator import state as store
from orchestrator.obsidian_state import KST, _vault
from orchestrator.run import _next_default_publish_at, _parse_publish_at

# script_feedback.SCRIPT_DIR_DEFAULT와 같은 폴더 체계 — 대기/완료 둘 다 본다.
REVIEW_WAIT_DEFAULT = "SNS 콘텐츠 제작 시스템/05 리뷰/대기"
PUBLISHED_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/06 제작/64 발행완료"
# 발행 축적(통합 3단계): 라이브러리(흐름 D5)·성과 기록·발행 캘린더.
LIBRARY_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/03 라이브러리/38 주제별 콘텐츠"
PERF_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/07 운영/61 성과 기록"
CALENDAR_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/06 제작/54 발행 캘린더"

PUBLISHABLE_CHANNELS = {"thread", "newsletter", "스레드", "뉴스레터", "threads"}
CHANNEL_NORM = {"스레드": "thread", "threads": "thread", "뉴스레터": "newsletter"}
REVIEW_PASSED = {"통과", "자동수정완료"}

TRIGGER_STATE = "리뷰완료"     # 사람이 이 값으로 바꾸는 것이 발행 승인
HOLD_STATE = "발행보류"        # 게이트 미충족 — 사유 통지 후 디큐(재통지 방지)
ERROR_STATE = "발행오류"       # 발행 시도 실패 — 고친 뒤 리뷰완료로 되돌리면 이어서 발행
DONE_STATE = "발행완료"

# 오발행 안전장치: 예약 시각이 이 일수보다 오래 지났으면 자동 발행하지 않는다.
MAX_PAST_DAYS = int(os.getenv("DG_SNS_PUBLISH_MAX_PAST_DAYS") or "3")
# 발행시간이 빈 승인은 생성일이 이 일수 안일 때만 기본 예약을 잡는다(옛 백로그 보호).
MAX_CREATED_DAYS = int(os.getenv("DG_SNS_APPROVE_MAX_AGE_DAYS") or "14")
# 한 실행에서 발행하는 최대 건수 — 대량 승인 시 채널 폭주(스팸성 연속 게시) 방지.
MAX_PER_RUN = int(os.getenv("DG_SNS_PUBLISH_MAX_PER_RUN") or "5")

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


# ---------- 파일 프론트매터 (원문 보존, 줄 단위) ----------

def _review_dirs() -> list[Path]:
    wait = os.getenv("VAULT_SCRIPT_PATH", REVIEW_WAIT_DEFAULT).strip("/")
    wait_dir = _vault() / wait
    return [wait_dir, wait_dir.parent / "완료"]


def _published_dir() -> Path:
    rel = os.getenv("DG_SNS_PUBLISHED_PATH", PUBLISHED_DIR_DEFAULT).strip("/")
    return _vault() / rel


def split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter 안쪽 원문, 본문). frontmatter 없으면 ('', 전체)."""
    m = _FM_RE.match(text)
    if not m:
        return "", text
    return m.group(1), text[m.end():]


def parse_meta(fm: str) -> dict:
    """줄 단위 관대한 파싱 — 콜론 든 주제 등 YAML이 깨지는 파일도 읽는다."""
    meta = {}
    for line in fm.splitlines():
        m = re.match(r"^([^:\s#][^:]*):\s*(.*)$", line)
        if m:
            meta[m.group(1).strip()] = m.group(2).strip().strip("'\"")
    return meta


def set_fields(path: Path, **fields: str) -> None:
    """frontmatter의 해당 키 줄만 바꾸거나 끝에 추가한다 (원문 보존)."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = _FM_RE.match(text)
    if not m:
        inner = "\n".join(f"{k}: {v}" for k, v in fields.items())
        path.write_text(f"---\n{inner}\n---\n\n{text}", encoding="utf-8")
        return
    inner = m.group(1)
    for key, value in fields.items():
        line = f"{key}: {value}"
        if re.search(rf"^{re.escape(key)}:.*$", inner, flags=re.MULTILINE):
            inner = re.sub(rf"^{re.escape(key)}:.*$", line, inner,
                           count=1, flags=re.MULTILINE)
        else:
            inner = inner.rstrip("\n") + f"\n{line}"
    path.write_text(f"---\n{inner}\n---\n" + text[m.end():], encoding="utf-8")


def strip_copy_note(body: str) -> str:
    """열람 사본 머리의 안내 인용구(> 열람용 사본…)를 발행 본문에서 뗀다."""
    lines = body.lstrip("\n").split("\n")
    if lines and lines[0].startswith(">") and "열람용 사본" in lines[0]:
        i = 0
        while i < len(lines) and lines[i].startswith(">"):
            i += 1
        return "\n".join(lines[i:]).lstrip("\n")
    return body


# ---------- 후보 스캔 ----------

def _norm_channel(meta: dict) -> str:
    raw = (meta.get("채널") or meta.get("type") or "").strip().lower()
    return CHANNEL_NORM.get(raw, raw)


def iter_approved(dirs: list[Path] | None = None) -> list[dict]:
    """상태: 리뷰완료인 thread/newsletter 원고 목록(승인 순서=파일명 순)."""
    out = []
    for directory in dirs or _review_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            fm, body = split_frontmatter(text)
            meta = parse_meta(fm)
            if (meta.get("상태") or "").strip() != TRIGGER_STATE:
                continue
            channel = _norm_channel(meta)
            if channel not in ("thread", "newsletter"):
                continue
            if not body.strip():
                continue
            out.append({"path": path, "meta": meta, "channel": channel,
                        "body": strip_copy_note(body).strip()})
    return out


# ---------- 게이트 ----------

def _hold(item: dict, reason: str, state: str = HOLD_STATE) -> None:
    path = item["path"]
    set_fields(path, 상태=state)
    store.notify(
        str(path),
        f"⏸️ '{path.stem}' 발행을 멈췄습니다.\n{reason}\n"
        f"해결한 뒤 frontmatter 상태를 '{TRIGGER_STATE}'로 되돌리면 다시 진행합니다.",
    )
    print(f"{path.name}: {state} — {reason}")


def _created_days_ago(meta: dict) -> float | None:
    raw = str(meta.get("생성일") or "").strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if not m:
        return None
    try:
        created = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                           tzinfo=KST)
    except ValueError:
        return None
    return (datetime.now(KST) - created).total_seconds() / 86400


def check_gates(item: dict) -> str:
    """발행 가능 여부: 'publish' | 'waiting' | 'held'. 보류 시 파일 상태 갱신+통지."""
    meta, path = item["meta"], item["path"]

    review = (meta.get("검수상태") or "").strip()
    if review not in REVIEW_PASSED:
        _hold(item, f"교육윤리 검수가 '{review or '미검수'}' 상태입니다. 본문을 확인하고 "
                    "검수상태를 '통과'로 바꿔 주세요."
                    + (f"\n검수 메모: {meta.get('검수메모')}" if meta.get("검수메모") else ""))
        return "held"

    raw_when = (meta.get("발행시간") or "").strip()
    if not raw_when:
        age = _created_days_ago(meta)
        if age is not None and age > MAX_CREATED_DAYS:
            _hold(item, f"생성된 지 {age:.0f}일이 지난 원고라 자동 예약을 잡지 않았습니다. "
                        "지금 발행하려면 발행시간에 'YYYY-MM-DD HH:MM'(KST)을 적어 주세요.")
            return "held"
        stamped = _next_default_publish_at()
        if stamped:
            set_fields(path, 발행시간=stamped)
            store.notify(
                str(path),
                f"⏰ '{path.stem}' 발행 예약 완료 — {stamped} (KST) 이후 자동 발행됩니다. "
                "시각을 바꾸려면 발행시간을 고치고, 바로 발행하려면 비우세요.",
            )
            print(f"{path.name}: 발행 예약 {stamped}")
            return "waiting"
        return "publish"  # 기본 예약 미설정 → 즉시 발행

    when = _parse_publish_at(raw_when)
    if when is None:
        _hold(item, f"발행시간('{raw_when}') 형식을 읽지 못했습니다. "
                    "'YYYY-MM-DD HH:MM'(KST)으로 고쳐 주세요.")
        return "held"
    now = datetime.now(KST)
    if when > now:
        print(f"{path.name}: 예약 대기 — {raw_when}")
        return "waiting"
    if (now - when).total_seconds() > MAX_PAST_DAYS * 86400:
        _hold(item, f"예약 시각({raw_when})이 {MAX_PAST_DAYS}일 넘게 지나 자동 발행을 "
                    "멈췄습니다(옛 승인 오발행 방지). 지금 발행하려면 발행시간을 "
                    "새로 적거나 비워 주세요.")
        return "held"
    return "publish"


# ---------- 발행 ----------

def _find_card(content_id: str) -> dict | None:
    """content_id → 파이프라인 카드(활성/발행완료). 없으면 None."""
    from orchestrator.obsidian_state import (_active_dir, _card_from_file,
                                             _done_dir)
    for d in (_active_dir(), _done_dir()):
        for p in sorted(d.glob(f"*{content_id}*.md")):
            return _card_from_file(p)
    return None


def _move_to_published(path: Path) -> Path:
    dest_dir = _published_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        stamp = datetime.now(KST).strftime("%Y%m%d%H%M")
        dest = dest_dir / f"{path.stem}_{stamp}{path.suffix}"
    path.rename(dest)
    return dest


def _accumulate(dest: Path, meta: dict, channel: str, permalink: str,
                post_count: int) -> None:
    """발행 축적(통합 3단계) — 라이브러리 복사(흐름 D5) + 월별 발행 기록 + 발행 캘린더.

    실패해도 발행 성공을 덮지 않도록 호출부에서 try로 감싼다.
    """
    now = datetime.now(KST)
    platform = "스티비" if channel == "newsletter" else "Threads"

    # ① 03 라이브러리/38 주제별 콘텐츠/<카테고리>/ — 다음 생성 때 AI가 참고할 자산.
    category = (meta.get("카테고리") or "").strip()
    if not category:
        from orchestrator.obsidian_state import topic_category
        category = topic_category(meta.get("주제") or dest.stem)
    lib = _vault() / os.getenv("DG_SNS_LIBRARY_PATH", LIBRARY_DIR_DEFAULT).strip("/") / category
    lib.mkdir(parents=True, exist_ok=True)
    if not (lib / dest.name).exists():
        shutil.copy2(dest, lib / dest.name)

    # ② 07 운영/61 성과 기록/YYYY-MM 발행 기록.md — 기존 파일 형식 그대로 이어 쓴다.
    perf = _vault() / PERF_DIR_DEFAULT / f"{now:%Y-%m} 발행 기록.md"
    perf.parent.mkdir(parents=True, exist_ok=True)
    header = "" if perf.exists() else f"# {now:%Y-%m} 발행 기록\n"
    with perf.open("a", encoding="utf-8") as f:
        f.write(f"{header}\n## {now:%Y-%m-%d %H:%M} - {dest.name}\n"
                f"- 글 수: {post_count}개\n- 플랫폼: {platform}\n"
                f"- 링크: {permalink}\n")

    # ③ 06 제작/54 발행 캘린더/YYYY-MM 발행 현황.md — 표 한 줄씩 누적.
    cal = _vault() / CALENDAR_DIR_DEFAULT / f"{now:%Y-%m} 발행 현황.md"
    cal.parent.mkdir(parents=True, exist_ok=True)
    if not cal.exists():
        cal.write_text(f"# {now:%Y-%m} 발행 현황\n\n자동 기록 — sns_publish가 "
                       "발행할 때마다 한 줄씩 추가합니다.\n\n"
                       "| 발행일 | 채널 | 원고 | 링크 |\n|---|---|---|---|\n",
                       encoding="utf-8")
    with cal.open("a", encoding="utf-8") as f:
        f.write(f"| {now:%m-%d %H:%M} | {platform} | [[{dest.stem}]] | {permalink} |\n")


def publish_item(item: dict) -> bool:
    """원고 하나를 발행한다. 성공 True. 실패는 상태 기록+통지 후 False."""
    path, channel, meta = item["path"], item["channel"], item["meta"]
    from orchestrator import publish

    # 열람 사본이면 원본 카드부터 확인 — 카드에서 이미 발행됐으면 중복 발행 금지.
    content_id = (meta.get("content_id") or "").strip()
    card = _find_card(content_id) if content_id else None
    if card and card.get("stage") == "published":
        set_fields(path, 상태=DONE_STATE,
                   발행링크=card.get("published_url", ""))
        dest = _move_to_published(path)
        store.notify(str(dest),
                     f"ℹ️ '{path.stem}'은 원본 카드({content_id})에서 이미 발행돼 "
                     "발행완료로만 정리했습니다.")
        return True

    try:
        if channel == "newsletter":
            from orchestrator import stibee
            if not stibee.available():
                _hold(item, "STIBEE_API_KEY/STIBEE_LIST_ID Secret이 없어 뉴스레터 자동 "
                            "발송을 못 합니다. 스티비에서 수동 발행 후 상태를 발행완료로 "
                            "바꾸거나, Secret 등록 후 다시 승인해 주세요.")
                return False
            result = stibee.create_and_send(item["body"])
            permalink = result.get("detail", "")
            post_count = 1
        else:
            if not publish.available():
                _hold(item, "THREADS_ACCESS_TOKEN/THREADS_USER_ID Secret이 없어 자동 "
                            "발행을 못 합니다. 수동 발행 후 상태를 발행완료로 바꿔 주세요.")
                return False
            posts = publish.split_posts(item["body"])
            done_ids = [x.strip() for x in (meta.get("발행진행") or "").split(",")
                        if x.strip()]

            def _save_progress(ids: list[str]):
                set_fields(path, 발행진행=",".join(ids))

            media_ids, permalink = publish.publish_chain(
                posts, done_ids=done_ids, on_progress=_save_progress)
            post_count = len(media_ids)
            if media_ids:
                # 주간 성과 수집(threads_insights)이 이 ID로 조회수를 가져온다.
                set_fields(path, thread_id=media_ids[0])
            permalink = permalink or f"발행 {len(media_ids)}개 (링크 조회 실패)"
    except Exception as e:  # noqa: BLE001 — 실패를 기록·통지하고 다음 파일로
        set_fields(path, 상태=ERROR_STATE)
        store.notify(
            str(path),
            f"⚠️ '{path.stem}' 발행 중 오류: {str(e)[:300]}\n"
            f"원인을 고친 뒤 상태를 '{TRIGGER_STATE}'로 되돌리면 발행된 글 다음부터 "
            "이어서 발행합니다.",
        )
        print(f"{path.name}: 발행 실패 — {e}")
        return False

    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    set_fields(path, 상태=DONE_STATE, 발행링크=permalink, 발행진행="",
               발행완료일=stamp)
    dest = _move_to_published(path)

    # 원본 카드 동기화 — 카드 쪽 발행 흐름이 같은 글을 또 올리지 않게 한다.
    if card:
        try:
            store.update_card(card["page_id"], stage="published", status="done",
                              published_url=permalink if channel == "thread" else "")
            store.append_section(
                card["page_id"], "📤 발행 기록 (05 리뷰 사본에서 발행)",
                f"발행 시각: {stamp} KST\n사본: {dest.name}\n결과: {permalink}",
            )
        except Exception as e:  # noqa: BLE001 — 동기화 실패가 발행 성공을 덮으면 안 됨
            print(f"{path.name}: 카드 동기화 실패({content_id}): {e}")

    # 발행 축적(3단계): 라이브러리·성과 기록·발행 캘린더 — 실패해도 발행 성공은 유지.
    try:
        _accumulate(dest, meta, channel, permalink, post_count)
    except Exception as e:  # noqa: BLE001
        print(f"{path.name}: 발행 축적 실패(발행은 완료): {e}")

    store.notify(str(dest),
                 f"✅ '{path.stem}' {'뉴스레터 발송' if channel == 'newsletter' else 'Threads 발행'} "
                 f"완료.\n{permalink}")
    print(f"{path.name}: 발행 완료 → {dest.name}")
    return True


# ---------- 실행 ----------

def run(dry_run: bool = False) -> dict:
    counts = {"published": 0, "waiting": 0, "held": 0, "failed": 0}
    for item in iter_approved():
        if dry_run:
            print(f"[dry-run] {item['channel']:<10} {item['path'].name} "
                  f"(검수: {item['meta'].get('검수상태') or '미검수'}, "
                  f"발행시간: {item['meta'].get('발행시간') or '없음'})")
            continue
        gate = check_gates(item)
        if gate == "waiting":
            counts["waiting"] += 1
            continue
        if gate == "held":
            counts["held"] += 1
            continue
        if counts["published"] >= MAX_PER_RUN:
            print(f"{item['path'].name}: 이번 실행 발행 한도({MAX_PER_RUN}) 도달 — 다음 실행에 발행")
            counts["waiting"] += 1
            continue
        if publish_item(item):
            counts["published"] += 1
        else:
            counts["failed"] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description="05 리뷰 원고 직접 발행 (상태: 리뷰완료 → 발행)")
    ap.add_argument("--dry-run", action="store_true", help="대상만 출력, 발행하지 않음")
    ap.add_argument("--list", action="store_true", help="승인·예약 현황 출력")
    args = ap.parse_args()
    if args.list or args.dry_run:
        items = iter_approved()
        print(f"승인(리뷰완료) 원고 {len(items)}건")
        for item in items:
            print(f"  {item['channel']:<10} {item['path'].name} "
                  f"(검수: {item['meta'].get('검수상태') or '미검수'}, "
                  f"발행시간: {item['meta'].get('발행시간') or '없음'})")
        return 0
    counts = run()
    print(f"SNS 발행 실행 완료: 발행 {counts['published']} / 예약대기 {counts['waiting']} / "
          f"보류 {counts['held']} / 실패 {counts['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
