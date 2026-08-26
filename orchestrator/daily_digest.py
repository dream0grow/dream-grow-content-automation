"""일일 발행 추천 다이제스트 — 대기 카드 중 반응 예상 상위 N개 추천 (P2)

발행 승인 대기 카드가 쌓이면 사람은 어느 것부터 봐야 할지 몰라 아무것도 승인하지
못한다. 이 모듈은 매일 1회:

  ① 발행 승인 대기(stage=approval) 카드를 모아
  ② LLM이 훅 강도·시의성·실용성 기준으로 예상 반응 상위 N개(기본 5)를 고르고
  ③ 아직 발행 심사(verify)가 없는 추천 카드는 그 자리에서 심사한 뒤
  ④ 카드 링크·심사 요약·승인 방법을 담은 다이제스트를 텔레그램으로 보낸다.

사람은 다이제스트의 N개만 확인하고 승인하면 된다. 승인 방법 둘:
  - 옵시디언에서 카드 frontmatter approval_status: approved
  - 텔레그램에서 이 메시지에 "DG-YYYY-NNNN 승인" 답장 (script_feedback이 처리)

실행:
    python3 -m orchestrator.daily_digest [--dry-run] [--count N]
워크플로우: .github/workflows/daily-digest.yml (매일 아침 KST)
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import llm, prompts, verify
from orchestrator import state as store
from orchestrator.config import DIGEST_COUNT

KST = timezone(timedelta(hours=9))


def log(msg: str):
    print(f"[daily-digest] {msg}", flush=True)


def _hook_snippet(page_id: str, fmt: str, limit: int = 120) -> str:
    """최종 원고의 첫 의미 있는 줄(훅)을 뽑는다."""
    draft = store.read_final_draft(page_id, fmt)
    for line in draft.splitlines():
        line = line.strip().strip("-# ")
        if len(line) >= 5:
            return line[:limit]
    return ""


def collect_waiting_cards() -> list[dict]:
    """발행 승인 대기 카드 + 훅 문장. 심사로 발행이 차단된(blocked) 카드는 제외."""
    out = []
    for card in store.query_cards(stage="approval", page_size=200):
        if card.get("approval_status") != "requested":
            continue
        formats = [f.strip() for f in str(card.get("format", "")).split(",")
                   if f.strip() in ("thread", "newsletter")]
        fmt = formats[0] if formats else "thread"
        hook = _hook_snippet(card["page_id"], fmt)
        if not hook:
            continue  # 원고가 없는 카드는 추천 불가
        out.append({**card, "digest_fmt": fmt, "hook": hook})
    return out


def rank_cards(cards: list[dict], count: int) -> list[dict]:
    """LLM이 예상 반응 상위 count개를 고른다. 실패하면 최신순 상위 count개."""
    if len(cards) <= count:
        return cards
    listing = "\n".join(
        f"- {c['content_id']} | 주제: {c['topic'][:80]} | 훅: {c['hook']}"
        for c in cards
    )
    by_id = {c["content_id"]: c for c in cards}
    try:
        data = llm.call_json(
            prompts.DIGEST_RANK.format(
                count=count, today=datetime.now(KST).strftime("%Y-%m-%d"),
                cards=listing[:24000],
            ),
            system=prompts.get_system(),
        )
        picks = []
        for p in data.get("picks", []):
            card = by_id.get(str(p.get("content_id", "")).strip())
            if card is not None and card not in picks:
                picks.append({**card, "pick_reason": str(p.get("reason", "")),
                              "expected_score": p.get("expected_score", "")})
            if len(picks) >= count:
                break
        if picks:
            return picks
    except Exception as e:  # noqa: BLE001 — 랭킹 실패가 다이제스트를 막으면 안 됨
        log(f"랭킹 실패(최신순 폴백): {e}")
    return cards[-count:][::-1]


def _ensure_verified(card: dict, dry_run: bool) -> str:
    """추천 카드에 발행 심사가 없으면 그 자리에서 심사하고 요약 한 줄을 돌려준다."""
    if str(card.get("verify_verdict", "")).strip():
        return f"심사 {card.get('verify_score', '?')} · {card.get('verify_verdict')}"
    if dry_run:
        return "(심사 예정)"
    try:
        results = verify.verify_card(card)
        if results:
            return verify.summary_line(results[0])
    except Exception as e:  # noqa: BLE001
        log(f"{card.get('content_id')} 심사 실패: {e}")
    return "(심사 없음)"


def _card_link(page_id: str) -> str:
    try:
        from vault_pipeline import telegram_notify
        from orchestrator.obsidian_state import _resolve, _vault
        rel = _resolve(page_id).relative_to(_vault()).as_posix()
        return telegram_notify.note_url(rel)
    except Exception:  # noqa: BLE001 — 링크는 부가 정보
        return ""


def build_digest(picks: list[dict], waiting_total: int, dry_run: bool) -> str:
    """텔레그램 다이제스트 본문을 만든다."""
    today = datetime.now(KST).strftime("%m/%d")
    lines = [f"📮 오늘의 발행 추천 {len(picks)}건 ({today}, 대기 {waiting_total}건)"]
    for i, c in enumerate(picks, 1):
        verify_note = _ensure_verified(c, dry_run)
        link = _card_link(c["page_id"])
        entry = [
            f"\n{i}. [{c['content_id']}] {c['topic'][:60]}",
            f"   훅: {c['hook'][:80]}",
            f"   {verify_note}",
        ]
        reason = str(c.get("pick_reason", "")).strip()
        if reason:
            entry.append(f"   추천 이유: {reason[:100]}")
        if link:
            entry.append(f"   🔗 {link}")
        lines.append("\n".join(entry))
    lines.append(
        "\n승인: 이 메시지에 답장으로 \"DG-YYYY-NNNN 승인\" 을 보내거나, "
        "옵시디언에서 카드 approval_status를 approved로 바꾸세요. "
        "승인하면 기본 예약 시각(21:00)에 자동 발행됩니다."
    )
    return "\n".join(lines)


def run(count: int = DIGEST_COUNT, dry_run: bool = False) -> str:
    store.require_backend()
    cards = collect_waiting_cards()
    if not cards:
        log("발행 승인 대기 카드 없음 — 다이제스트 생략")
        return ""
    picks = rank_cards(cards, count)
    message = build_digest(picks, waiting_total=len(cards), dry_run=dry_run)
    if dry_run:
        log("[dry-run] 발송 생략:\n" + message)
        return message
    try:
        from vault_pipeline import telegram_notify
        telegram_notify.send(message)
        log(f"다이제스트 발송: 추천 {len(picks)}건 / 대기 {len(cards)}건")
    except Exception as e:  # noqa: BLE001
        log(f"텔레그램 발송 실패: {e}")
    return message


if __name__ == "__main__":
    count = DIGEST_COUNT
    if "--count" in sys.argv:
        count = int(sys.argv[sys.argv.index("--count") + 1])
    run(count=count, dry_run="--dry-run" in sys.argv)
