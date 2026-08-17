"""열람 사본 직접 수정 반영 — GitHub Edit·옵시디언에서 고친 초안을 카드에 되먹인다.

`05 리뷰/대기/{스레드|뉴스레터}_*.md`는 카드 초안의 열람 사본(review_copy.py)이다.
예전엔 "여기 고쳐 봐야 발행에 반영 안 됨"이었지만, 폰·웹에서 손이 제일 잘 닿는 곳이
이 파일이라 사람이 직접 고치는 게 자연스럽다. 이 모듈이 그 수정을 주워 담는다:

  ① 감지 — 사본 본문의 지문이 내보낼 때 남긴 `draft_hash`와 다르고, 카드의 최신
     '✍️ 초안 (채널)'과도 다르면 사람이 고친 것으로 본다(기준선이 없는 옛 사본도
     카드 초안과 직접 비교하므로 첫 실행부터 잡힌다).
  ② 반영 — 수정본을 카드에 '✍️ 초안 (채널) 🧑 사람 수정본'으로 덧붙인다. 발행은
     최신 초안 섹션을 읽으므로, 승인만 하면 사람 손이 간 원고가 그대로 나간다.
  ③ 학습 — style_learn이 '🗄️ AI 원본 (채널)'과 수정본을 비교해 문체 패턴을 뽑아
     Honcho({채널}-corrections)에 쌓는다. 다음 초안부터 작가 프롬프트에 반영된다.
  ④ 통지 — 반영 결과를 텔레그램으로 알리고, 사본 frontmatter의 지문을 갱신해
     같은 수정이 두 번 처리되지 않게 한다.

안전장치: 수정본이 너무 짧거나(200자 미만) 카드 초안의 절반 미만이면 사고로 보고
반영하지 않고 통지만 한다. 발행 게이트는 건드리지 않는다 — 승인은 사람 몫 그대로다.

실행:
    python3 -m orchestrator.copy_edits              # 감지 + 반영
    python3 -m orchestrator.copy_edits --dry-run    # 대상만 출력
"""
import argparse
import os
import re
from pathlib import Path

from vault_pipeline.vault_io import now_kst, parse_frontmatter, vault_root

from orchestrator import review_copy
from orchestrator import state as store
from orchestrator.youtube_script import SCRIPT_DIR_DEFAULT

# 이 채널의 사본만 카드로 되먹인다(유튜브 원고는 자체 핑퐁 경로가 따로 있다).
SUPPORTED = {"thread", "newsletter"}
# 사고 방지 — 이보다 짧은 수정본은 반영하지 않는다.
MIN_CHARS = 200
# 카드 초안 대비 이 비율 미만이면 내용 유실로 보고 반영하지 않는다.
MIN_KEEP_RATIO = 0.5
# 한 실행에서 처리할 최대 건수(첫 실행 백로그 폭주 방지).
DEFAULT_MAX = 10

CARD_ID_RE = re.compile(r"DG-\d{4}-\d{4}")


def log(msg: str) -> None:
    print(f"[copy_edits] {msg}", flush=True)


def _script_dir() -> Path:
    rel = os.getenv("VAULT_SCRIPT_PATH", SCRIPT_DIR_DEFAULT).strip("/")
    return vault_root() / rel


def _card_dirs() -> list[Path]:
    base = vault_root() / "파이프라인"
    return [base / "활성", base / "발행완료"]


def find_card(content_id: str) -> Path | None:
    """content_id(DG-YYYY-NNNN) → 카드 파일. 활성 → 발행완료 순으로 찾는다."""
    m = CARD_ID_RE.search(content_id or "")
    if not m:
        return None
    for directory in _card_dirs():
        matches = sorted(directory.glob(f"{m.group(0)}*.md"))
        if matches:
            return matches[0]
    return None


def scan() -> list[dict]:
    """사본 폴더에서 카드와 연결된 thread/newsletter 사본 목록을 읽는다."""
    directory = _script_dir()
    if not directory.exists():
        return []
    out: list[dict] = []
    for p in sorted(directory.glob("*.md")):
        if p.name == "README.md":
            continue
        raw = p.read_text(encoding="utf-8", errors="ignore")
        meta, _ = parse_frontmatter(raw)
        content_id = str(meta.get("content_id") or "").strip()
        fmt = str(meta.get("채널") or meta.get("channel") or "").strip()
        if not content_id or fmt not in SUPPORTED:
            continue
        body = review_copy.body_of(raw)
        out.append({
            "path": p,
            "meta": meta,
            "content_id": content_id,
            "fmt": fmt,
            "body": body,
            "hash": review_copy.content_hash(body),
            "stored_hash": str(meta.get("draft_hash") or "").strip(),
        })
    return out


def _update_frontmatter(path: Path, updates: dict) -> None:
    """사본 frontmatter의 키를 갱신한다(원문 순서·서식 보존, 없으면 끝에 추가)."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n?)(.*)$", text, re.DOTALL)
    if not m:
        return
    head, fm, close, body = m.group(1), m.group(2), m.group(3), m.group(4)
    lines = fm.split("\n")
    for key, value in updates.items():
        line = f"{key}: {value}"
        for i, existing in enumerate(lines):
            if re.match(rf"^{re.escape(key)}\s*:", existing):
                lines[i] = line
                break
        else:
            lines.append(line)
    path.write_text(head + "\n".join(lines) + close + body, encoding="utf-8")


def _stamp(item: dict, note: str = "") -> None:
    """처리한 사본의 지문을 현재 본문으로 갱신해 재처리를 막는다."""
    updates = {"draft_hash": item["hash"]}
    if note:
        updates["수정반영"] = f"{now_kst().strftime('%Y-%m-%d %H:%M')} {note}"
    _update_frontmatter(item["path"], updates)


def apply_one(item: dict, dry_run: bool = False) -> str:
    """사본 1건을 검사해 필요하면 카드에 반영하고 문체를 학습한다.

    Returns: unchanged / applied / too_short / no_card / planned
    """
    card_path = find_card(item["content_id"])
    if card_path is None:
        log(f"카드 없음({item['content_id']}) — 사본 {item['path'].name} 건너뜀")
        return "no_card"

    page_id = str(card_path)
    fmt = item["fmt"]
    current = store.read_latest_section(page_id, f"✍️ 초안 ({fmt})")
    edited = item["body"]

    if review_copy.normalize(current) == review_copy.normalize(edited):
        # 카드와 같은 내용 — 사람 수정 아님. 지문만 맞춰 다음 실행 비교를 아낀다.
        if item["stored_hash"] != item["hash"] and not dry_run:
            _stamp(item)
        return "unchanged"

    if len(edited) < MIN_CHARS or (
            current and len(edited) < len(current) * MIN_KEEP_RATIO):
        log(f"{item['path'].name} 수정본이 너무 짧음"
            f"({len(edited)}/{len(current)}자) — 반영 보류")
        if not dry_run:
            _stamp(item, "보류(내용 유실 의심)")
            store.notify(
                page_id,
                f"⚠️ [{item['content_id']}] 열람 사본 수정본이 카드 초안보다 크게 "
                f"짧아 반영하지 않았습니다({len(edited)}자). 실수로 지운 게 아니라면 "
                f"05 리뷰/대기/{item['path'].name}에 본문을 다시 채워주세요.",
            )
        return "too_short"

    if dry_run:
        log(f"[계획] {item['path'].name} → 카드 {item['content_id']} 초안 반영")
        return "planned"

    store.append_section(page_id, f"✍️ 초안 ({fmt}) 🧑 사람 수정본", edited)
    log(f"{item['content_id']} 사람 수정본 반영 ← {item['path'].name}")

    saved = 0
    learned = False
    try:
        from orchestrator import style_learn
        saved = style_learn.learn_from_edits(page_id, fmt)
        learned = True
    except Exception as e:  # noqa: BLE001 — 학습 실패가 반영을 되돌리면 안 됨
        log(f"문체 학습 실패(반영은 유지): {e}")

    _stamp(item, f"카드 반영{'·문체 학습' if learned else ''}")
    card_meta, _ = parse_frontmatter(
        card_path.read_text(encoding="utf-8", errors="ignore"))
    published = str(card_meta.get("stage") or "").strip() == "published"
    store.notify(
        page_id,
        f"🧑 [{item['content_id']}] 열람 사본에서 직접 고치신 내용을 카드 "
        f"'✍️ 초안 ({fmt})'에 반영했습니다. "
        + (f"AI 원본과 비교해 문체 패턴 {saved}개를 학습했어요. "
           if saved else "문체 학습은 AI 원본과 차이가 없거나 저장에 실패했습니다. ")
        + ("이미 발행된 카드라 발행본은 그대로입니다 — 수정분은 다음 글의 문체 "
           "학습에만 쓰입니다."
           if published else
           "이대로 발행하려면 카드에서 approval_status를 approved로 바꾸세요."),
    )
    return "applied"


def apply_edits(dry_run: bool = False, max_items: int = DEFAULT_MAX) -> dict:
    """열람 사본의 사람 수정을 모두 처리한다. 결과 카운트 dict 반환."""
    counts: dict[str, int] = {}
    processed = 0
    for item in scan():
        # 지문이 그대로면 내보낸 뒤 손대지 않은 사본 — 카드를 읽을 필요도 없다.
        if item["stored_hash"] and item["stored_hash"] == item["hash"]:
            counts["unchanged"] = counts.get("unchanged", 0) + 1
            continue
        if processed >= max_items:
            log(f"실행당 최대 {max_items}건 도달, 다음 실행에 계속")
            break
        try:
            result = apply_one(item, dry_run)
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 전체를 막으면 안 됨
            log(f"사본 처리 예외({item['path'].name}): {e}")
            result = "failed"
        counts[result] = counts.get(result, 0) + 1
        if result in ("applied", "too_short", "planned"):
            processed += 1
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(
        description="열람 사본(05 리뷰/대기)의 사람 수정을 카드 초안에 반영하고 문체 학습")
    ap.add_argument("--dry-run", action="store_true",
                    help="대상만 출력하고 볼트에 쓰지 않음")
    ap.add_argument("--max", type=int, default=DEFAULT_MAX,
                    help="한 번에 반영할 최대 건수")
    args = ap.parse_args()
    counts = apply_edits(args.dry_run, args.max)
    log("완료: " + ", ".join(f"{k} {v}건" for k, v in sorted(counts.items()))
        if counts else "완료: 대상 없음")


if __name__ == "__main__":
    main()
