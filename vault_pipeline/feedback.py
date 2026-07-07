"""발행 후 되먹임 — 시스템의 심장 (사용자 최우선 요구)

사용자가 초안을 고쳐 frontmatter `상태: 발행완료`(또는 리뷰완료)로 바꾸면:
1. **문체 학습**: AI 원본(_system/ai_originals/) vs 최종본 diff → 일반화된
   편집 규칙을 `_system/style_lessons.md`에 채널별로 누적. 이후 모든 초안
   프롬프트에 주입돼(writers.load_style_lessons) 글이 점점 사용자 문체에 수렴한다.
2. **원자 메모 분해**: 최종본(사람이 확정한 문장)을 제텔카스텐 1. 메모로 분해.
   author: 이한결, source_type: own_content(원출처 추적 필요 플래그) —
   글 하나가 다시 지식 벽돌이 되는 원소스 멀티유즈의 환류 구간.

두 종류의 발행물을 환류한다:
- **교사 초안**(`프로젝트/교육운동/*_초안`, `상태: 발행완료`): 문체 학습 + 메모 분해.
- **학부모 파이프라인 카드**(`파이프라인/…`, `stage: published`, A7): 메모 분해만.
  문체 학습은 발행 시 orchestrator/style_learn이 이미 수행하므로 중복하지 않는다.

실행: python3 -m vault_pipeline.feedback  (plaud-pipeline 워크플로우가 매일 호출)
중복 방지: _system/logs/feedback_ledger.json (기존 파일은 수정하지 않는다)
"""
import argparse
import json
from pathlib import Path

from vault_pipeline import prompts
from vault_pipeline.vault_io import (
    log_line, now_kst, parse_frontmatter, today, vault_root, write_note,
)

from orchestrator import llm

# 되먹임 감시 대상 — 교사 초안 폴더(`상태: 발행완료/리뷰완료`)
DRAFT_DIRS = [
    "프로젝트/교육운동/블로그_초안",
    "프로젝트/교육운동/페이스북_초안",
]
DONE_STATES = {"발행완료", "리뷰완료"}

# 학부모 파이프라인 발행 카드(`stage: published`)의 원자 메모 환류 대상(A7).
# 문체 학습은 orchestrator/style_learn이 발행 시 이미 하므로 여기선 atomize만 한다.
PIPELINE_DIR = "파이프라인"
MIN_DRAFT_CHARS = 100  # 이보다 짧은 스텁·빈 카드는 분해기에 넘기지 않는다


def _ledger_path() -> Path:
    return vault_root() / "_system" / "logs" / "feedback_ledger.json"


def _load_ledger() -> dict:
    p = _ledger_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_ledger(ledger: dict) -> None:
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def find_published() -> list[dict]:
    """발행완료/리뷰완료인데 아직 되먹임하지 않은 초안 목록."""
    ledger = _load_ledger()
    targets = []
    for rel in DRAFT_DIRS:
        directory = vault_root() / rel
        if not directory.exists():
            continue
        for p in sorted(directory.glob("*.md")):
            if p.name in ("README.md",):
                continue
            key = f"{rel}/{p.name}"
            if key in ledger:
                continue
            meta, body = parse_frontmatter(
                p.read_text(encoding="utf-8", errors="ignore"))
            if str(meta.get("상태", "")).strip() not in DONE_STATES:
                continue
            targets.append({"key": key, "path": p, "meta": meta,
                            "body": body.strip(), "dir": rel})
    return targets


def find_published_pipeline() -> list[dict]:
    """학부모 파이프라인의 발행 완료 카드를 원자 메모 환류 대상으로 모은다(A7).

    orchestrator가 `stage: published, status: done`으로 표시한 카드에서 사람이 확정·발행한
    최종 초안을 꺼내 atomize 대상 target으로 만든다. 문체 학습은 발행 시 이미 끝났으므로
    여기서는 atomize만 한다. 최종 초안이 충분히 길고(스텁 방지) 아직 환류 안 한 카드만.
    """
    from orchestrator import state as store
    ledger = _load_ledger()
    targets: list[dict] = []
    try:
        cards = store.query_cards(stage="published", status="done", page_size=100)
    except Exception as e:  # noqa: BLE001 — 조회 실패가 교사 되먹임까지 막으면 안 됨
        log_line(f"파이프라인 발행 카드 조회 실패(교사 되먹임은 계속): {e}", dry_run=False)
        return []
    for card in cards:
        page_id = card["page_id"]
        key = f"pipeline:{page_id}"
        if key in ledger:
            continue
        # 최종 초안(사람이 확정·발행한 본문). 뉴스레터가 있으면 우선(심화), 없으면 스레드.
        nl = store.read_latest_section(page_id, "✍️ 초안 (newsletter)").strip()
        th = (store.read_latest_section(page_id, "✍️ 초안 (thread)").strip()
              or store.read_latest_section(page_id, "✍️ 초안").strip())
        if nl:
            draft, fmt = nl, "newsletter"
        elif th:
            draft, fmt = th, "thread"
        else:
            continue
        if len(draft) < MIN_DRAFT_CHARS:
            continue  # 스텁·빈 카드는 분해기에 넘기지 않는다
        targets.append({
            "key": key,
            "path": vault_root() / page_id,
            "meta": {"채널": fmt, "published_url": card.get("published_url", "")},
            "body": draft,
            "dir": PIPELINE_DIR,
            "pipeline": True,   # main에서 문체 학습을 건너뛰는 표식
        })
    return targets


def _ai_original(target: dict) -> str:
    path = (vault_root() / "_system" / "ai_originals"
            / target["path"].parent.name / target["path"].name)
    if path.exists():
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    return ""


def learn_style(target: dict, dry_run: bool) -> int:
    """AI 원본 vs 최종본 → 편집 규칙 누적. 배운 규칙 수 반환."""
    original = _ai_original(target)
    final = target["body"]
    if not original or original == final:
        return 0
    channel = str(target["meta"].get("채널", "")).strip() or target["dir"].split("/")[-1]
    result = llm.call_json(
        prompts.STYLE_DIFF.format(original=original[:12000], final=final[:12000]),
        max_tokens=2000,
    )
    lessons = [str(x).strip() for x in (result.get("교훈") or []) if str(x).strip()]
    if not lessons or dry_run:
        return len(lessons)
    path = vault_root() / "_system" / "style_lessons.md"
    text = path.read_text(encoding="utf-8") if path.exists() else \
        "# 문체 학습 노트 (자동 누적)\n\n사용자가 초안을 고칠 때마다 편집 규칙이 쌓인다.\n틀린 규칙은 직접 지워도 된다 — 남은 것만 프롬프트에 주입된다.\n"
    heading = f"## {channel}"
    entry = (f"\n### {today()} — {target['path'].stem}\n"
             + "\n".join(f"- {les}" for les in lessons) + "\n")
    if heading in text:
        # 해당 채널 섹션 끝(다음 ## 직전 또는 파일 끝)에 추가
        idx = text.index(heading)
        next_idx = text.find("\n## ", idx + len(heading))
        insert_at = len(text) if next_idx < 0 else next_idx
        text = text[:insert_at].rstrip() + "\n" + entry + text[insert_at:]
    else:
        text = text.rstrip() + f"\n\n{heading}\n{entry}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return len(lessons)


def atomize(target: dict, dry_run: bool) -> int:
    """최종본을 제텔카스텐 원자 메모로 분해. 생성 메모 수 반환."""
    channel = str(target["meta"].get("채널", "")).strip()
    result = llm.call_json(
        prompts.ATOMIZE.format(channel=channel, final=target["body"][:15000]),
        max_tokens=3000,
    )
    memos = result.get("메모") or []
    count = 0
    for memo in memos[:5]:
        title = str(memo.get("제목", "")).strip()
        excerpt = str(memo.get("발췌", "")).strip()
        if not title or not excerpt:
            continue
        meta = {
            "title": title,
            "author": "이한결",              # 사람이 확정·발행한 문장
            "source_type": "own_content",   # 자기 콘텐츠 출신 — 원출처 추적 필요
            "원출처_추적": "필요",
            "출처": target["key"],
            "published_url": str(target["meta"].get("published_url", "") or ""),
            "created": today(),
        }
        body = (f"> \"{excerpt}\"\n\n"
                f"발행 글 [[{target['path'].stem}]]에서 분해. "
                "책·논문에 인용하려면 원출처(경험·근거)를 붙일 것.\n")
        write_note("제텔카스텐/1. 메모", title, meta, body, dry_run=dry_run)
        count += 1
    return count


def main() -> None:
    ap = argparse.ArgumentParser(description="발행 후 되먹임: 문체 학습 + 메모 분해")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 교사 초안(문체 학습 + 메모 분해) + 학부모 파이프라인 발행 카드(메모 분해만, A7)
    targets = find_published() + find_published_pipeline()
    if not targets:
        log_line("되먹임: 새 발행완료 글 없음", dry_run=args.dry_run)
        return

    ledger = _load_ledger()
    for t in targets:
        try:
            # 학부모 파이프라인 카드는 발행 시 style_learn이 이미 문체를 학습했으므로 생략
            lessons = 0 if t.get("pipeline") else learn_style(t, args.dry_run)
            memos = atomize(t, args.dry_run)
            src = "학부모" if t.get("pipeline") else "교사"
            log_line(f"되먹임 완료[{src}]: {t['key']} → 문체 규칙 {lessons}건, "
                     f"원자 메모 {memos}건", dry_run=args.dry_run)
            if not args.dry_run:
                ledger[t["key"]] = {
                    "processed_at": now_kst().isoformat(timespec="seconds"),
                    "lessons": lessons, "memos": memos,
                }
                _save_ledger(ledger)
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 전체를 막으면 안 됨
            log_line(f"되먹임 실패({t['key']}): {e}", dry_run=args.dry_run)


if __name__ == "__main__":
    main()
