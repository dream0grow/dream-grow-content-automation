"""플라우드 → 볼트 파이프라인 실행 진입점

사용:
    python3 -m vault_pipeline.run                     # 최근 7일, 최대 3건 처리
    python3 -m vault_pipeline.run --dry-run           # 처리 대상만 보여주고 쓰지 않음
    python3 -m vault_pipeline.run --source inbox      # 수집함 파일만 (API 미인증 환경)

한 녹음의 처리 흐름:
    전사 → triage(LLM 1회, JSON) → ①사례은행(신호등) ②메모→키워드→의견 ③교사 글 초안
    → 장부 기록(재처리 방지) → 인박스 파일이면 처리됨/으로 이동

안전 규칙: 녹음 하나가 실패해도 전체는 계속 간다. 실패 건은 파일을 만들지 않고
로그만 남긴다(_검토필요 오염 재발 방지).
"""
import argparse
import sys
import traceback
from pathlib import Path

from vault_pipeline import prompts, telegram_notify, writers
from vault_pipeline.plaud_client import (
    Recording, archive_inbox_file, fetch_recordings,
)
from vault_pipeline.vault_io import log_line, mark_processed, processed_ids

from orchestrator import llm

# 전사가 너무 짧으면 가공할 내용이 없다 (인사말·오녹음)
MIN_TRANSCRIPT_CHARS = 80
# LLM 입력 보호 상한 (초장시간 녹음)
MAX_TRANSCRIPT_CHARS = 60_000


def process_recording(rec: Recording, dry_run: bool) -> dict:
    """녹음 1건을 3종 시스템으로 가공한다.

    반환: {"artifacts": [파일명들], "drafts": [교사 초안명], "green": n,
          "yellow": n, "memos": n, "detail": 녹음별 산출물 제목(알림용)}
    """
    transcript = rec.transcript[:MAX_TRANSCRIPT_CHARS]
    triage = llm.call_json(
        prompts.TRIAGE.format(transcript=transcript, name=rec.name,
                              recorded=rec.recorded),
        system=prompts.TRIAGE_SYSTEM,
        max_tokens=8000,
    )
    case_result = writers.write_cases(rec, triage.get("사례") or [], dry_run)
    artifacts: list[str] = list(case_result["artifacts"])
    memo_stems = writers.write_memos(rec, triage.get("메모") or [], dry_run)
    artifacts += list(memo_stems.values())
    keyword_files = writers.write_keywords(rec, triage.get("키워드") or [],
                                           memo_stems, dry_run)
    artifacts += keyword_files
    opinion_files = writers.write_opinions(rec, triage.get("의견") or [], dry_run)
    artifacts += opinion_files
    seed = triage.get("교사_글감") or {}
    artifacts += writers.write_activity_record(rec, seed, dry_run)
    drafts = writers.write_teacher_posts(rec, seed, dry_run)
    artifacts += drafts
    detail = {
        "녹음": rec.name,
        "메모": [{"제목": title, "경로": f"제텔카스텐/1. 메모/{stem}.md"}
                for title, stem in memo_stems.items()],
        "키워드": [{"제목": f.removesuffix(".md").removeprefix("K_ai - "),
                   "경로": f"제텔카스텐/2. 키워드/{f}"}
                  for f in keyword_files],
        "의견": [{"제목": f.removesuffix(".md").removeprefix("O - "),
                 "경로": f"제텔카스텐/3. 의견/{f}"}
                for f in opinion_files],
    }
    return {"artifacts": artifacts, "drafts": drafts,
            "green": case_result["green"], "yellow": case_result["yellow"],
            "memos": len(memo_stems), "detail": detail}


def main() -> None:
    ap = argparse.ArgumentParser(description="플라우드 → 옵시디언 볼트 파이프라인")
    ap.add_argument("--since-days", type=int, default=7, help="조회 기간(일)")
    ap.add_argument("--max", type=int, default=3, help="한 번에 처리할 최대 녹음 수")
    ap.add_argument("--source", choices=["auto", "inbox", "mcp"], default="auto")
    ap.add_argument("--dry-run", action="store_true",
                    help="처리 대상과 계획만 출력, 볼트에 쓰지 않음")
    args = ap.parse_args()

    recordings, warnings, pending = fetch_recordings(
        args.since_days, args.max * 3, source=args.source)
    for w in warnings:
        log_line(w, dry_run=args.dry_run)
    if pending:
        log_line(f"전사 대기 {len(pending)}건 (플라우드 앱에서 전사하면 자동 처리): "
                 + ", ".join(pending[:5]), dry_run=args.dry_run)

    done = processed_ids()
    todo = [r for r in recordings if r.id not in done]
    # 오래된 녹음부터 — 최신 녹음이 quota를 선점해 옛 녹음이 since_days 창을
    # 벗어나기 전에 처리되지 못하는 기아 현상을 막는다.
    todo.sort(key=lambda r: r.recorded)
    todo = todo[:args.max]
    skipped = len(recordings) - len(todo)
    log_line(f"녹음 {len(recordings)}건 조회 — 신규 {len(todo)}건 처리 예정"
             + (f", 기처리 {skipped}건 생략" if skipped else ""),
             dry_run=args.dry_run)

    if args.dry_run:
        for r in todo:
            print(f"  [계획] {r.recorded} {r.name} (id={r.id}, "
                  f"{len(r.transcript)}자, source={r.source})")
        return

    failures = 0
    total = {"drafts": [], "green": 0, "yellow": 0, "memos": 0}
    details: list[dict] = []
    for rec in todo:
        if len(rec.transcript) < MIN_TRANSCRIPT_CHARS:
            log_line(f"생략(전사 {len(rec.transcript)}자로 너무 짧음): {rec.name}")
            mark_processed(rec.id, rec.name, ["짧아서 생략"])
            archive_inbox_file(rec)
            continue
        try:
            result = process_recording(rec, dry_run=False)
            mark_processed(rec.id, rec.name, result["artifacts"])
            archive_inbox_file(rec)
            log_line(f"완료: {rec.name} → 산출물 {len(result['artifacts'])}건")
            total["drafts"] += result["drafts"]
            for k in ("green", "yellow", "memos"):
                total[k] += result[k]
            details.append(result["detail"])
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 전체를 죽이면 안 됨
            failures += 1
            log_line(f"실패({rec.id} {rec.name}): {e}")
            traceback.print_exc()

    # 폰 알림 (TELEGRAM_* Secrets 있을 때만) — 확인·대기할 것이 있거나 실패 시
    if todo or failures or pending:
        draft_links = [{"제목": Path(p).stem, "경로": p}
                       for p in total["drafts"]]
        sent = telegram_notify.send(telegram_notify.briefing(
            draft_links, total["yellow"], total["green"], total["memos"],
            failures, pending=len(pending), details=details), html=True)
        if sent:
            log_line("텔레그램 알림 발송 완료")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
