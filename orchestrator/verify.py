"""발행 심사관 — 초안을 만든 대화와 분리된 fresh context 검증 (P1)

작가↔비평가 토론은 같은 맥락 안에서 돌기 때문에 자기가 만든 편향을 그대로
물려받는다. 이 모듈은 초안 생성이 끝난 뒤 **완성 원고만** 새 LLM 호출에 넣어
제3자 시점에서 검사한다:

  - 루브릭 점수 (훅/가독성/실천성/브랜드핏/공감, 총 50)
  - AI 티 잔존 (HUMANIZE_RULES 위반 구간 인용)
  - 사실·수치 위험 문장 (출처 없는 통계, 단정적 효과 주장)
  - 브랜드 보이스 일치도 (10)
  - 종합 판정: recommend(그대로 발행 가능) / conditional(한두 곳만 고치면 됨)
    / needs_review(사람이 전문을 읽어야 함)

결과는 카드 본문 `## 🔍 발행 심사` 섹션과 frontmatter(verify_score/verify_verdict)에
남고, 텔레그램 승인 요청 알림에 요약이 붙는다. **발행 승인은 항상 사람이 한다** —
심사는 사람이 전문을 읽지 않고도 결재할 수 있게 근거를 만드는 참고 자료다.

실행 (기존 대기 카드 소급 심사):
    python3 -m orchestrator.verify --backfill [--limit N]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import llm, prompts
from orchestrator import state as store
from orchestrator.config import VERIFY_ENABLED

VERIFY_SECTION = "🔍 발행 심사"

_VERDICT_LABEL = {
    "recommend": "✅ 승인 추천 — 그대로 발행해도 됩니다",
    "conditional": "🟡 조건부 — 아래 한두 곳만 고치면 발행 가능",
    "needs_review": "🔍 확인 필요 — 전문을 읽고 판단해 주세요",
}


def _bullets(items) -> str:
    lines = [f"- {x}" for x in (items or []) if str(x).strip()]
    return "\n".join(lines) if lines else "- 없음"


def run_verification(card: dict, fmt: str) -> dict | None:
    """카드의 최종 원고(fmt)를 fresh context로 심사한다. 원고가 없으면 None."""
    draft = store.read_final_draft(card["page_id"], fmt)
    if not draft.strip():
        return None
    brief = store.read_latest_section(card["page_id"], "📝 브리프")
    # 브리프에서 핵심 메시지 줄만 뽑는다(없으면 주제로 대체).
    core = ""
    for line in brief.splitlines():
        if "핵심 메시지" in line:
            core = line.split(":", 1)[-1].strip().strip("*")
            break
    result = llm.call_json(
        prompts.VERIFY.format(
            format=fmt, topic=card.get("topic", ""),
            keyword=card.get("approved_keyword", ""),
            core_message=core or card.get("topic", ""),
            humanize_rules=prompts.HUMANIZE_RULES,
            draft=draft[:20000],
        ),
        system=prompts.get_system(),
    )
    result["format"] = fmt
    return result


def format_result(r: dict) -> str:
    """심사 결과 dict → 카드 본문용 마크다운."""
    verdict = str(r.get("verdict", ""))
    label = _VERDICT_LABEL.get(verdict, verdict)
    rows = [("훅", "hook"), ("가독성", "readability"), ("실천성", "actionability"),
            ("브랜드핏", "brand_fit"), ("공감", "empathy")]
    scores = " / ".join(f"{name} {r.get(key, '?')}" for name, key in rows)
    parts = [
        f"## {label}",
        f"**총점 {r.get('total', '?')}/50** ({scores}) · 보이스 일치 {r.get('voice_match', '?')}/10",
        f"**판정 이유**: {r.get('verdict_reason', '')}",
        f"### AI 티 잔존\n{_bullets(r.get('ai_tell_issues'))}",
        f"### 사실·수치 위험\n{_bullets(r.get('fact_risk_sentences'))}",
    ]
    if str(r.get("fix_first") or "").strip():
        parts.append(f"### 먼저 고칠 곳\n{r['fix_first']}")
    parts.append(
        "> 이 심사는 초안을 만든 에이전트와 분리된 검증 호출의 결과입니다. "
        "발행 승인(approval_status: approved)은 사람이 합니다."
    )
    return "\n\n".join(parts)


def summary_line(r: dict) -> str:
    """텔레그램 알림용 한 줄 요약."""
    emoji = {"recommend": "✅", "conditional": "🟡", "needs_review": "🔍"}.get(
        str(r.get("verdict", "")), "🔍")
    risks = len(r.get("fact_risk_sentences") or [])
    tells = len(r.get("ai_tell_issues") or [])
    return (f"{emoji} 심사 {r.get('total', '?')}/50 · 위험 {risks}건 · "
            f"AI 티 {tells}건 — {r.get('verdict_reason', '')[:80]}")


# verdict 심각도 — 여러 포맷 중 가장 나쁜 판정을 카드 frontmatter에 남긴다.
_VERDICT_RANK = {"recommend": 0, "conditional": 1, "needs_review": 2}


def verify_card(card: dict) -> list[dict]:
    """카드의 지원 포맷 전부를 심사하고 섹션+frontmatter에 기록한다."""
    if not VERIFY_ENABLED:
        return []
    formats = [f.strip() for f in str(card.get("format", "")).split(",") if f.strip()]
    supported = [f for f in formats if f in ("thread", "newsletter")] or ["thread"]
    results = []
    for fmt in supported:
        r = run_verification(card, fmt)
        if r is None:
            continue
        store.append_formatted_section(
            card["page_id"], f"{VERIFY_SECTION} ({fmt})", format_result(r),
        )
        results.append(r)
    if results:
        worst = max(results, key=lambda r: _VERDICT_RANK.get(str(r.get("verdict")), 2))
        total = min((r.get("total") for r in results
                     if isinstance(r.get("total"), (int, float))), default="")
        store.update_card(
            card["page_id"],
            verify_score=f"{total}/50" if total != "" else "",
            verify_verdict=str(worst.get("verdict", "")),
        )
    return results


def backfill(limit: int = 10) -> int:
    """발행 승인 대기 중인데 심사가 없는 카드를 오래된 것부터 심사한다(소급).

    한 번에 limit건만 처리해 API 폭주를 막는다 — cron/수동 실행을 반복하면
    전체 백로그가 순차 소화된다.
    """
    done = 0
    for card in store.query_cards(stage="approval", page_size=100):
        if card.get("approval_status") not in ("requested", "blocked"):
            continue
        if str(card.get("verify_verdict", "")).strip():
            continue  # 이미 심사됨
        try:
            results = verify_card(card)
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 전체를 막으면 안 됨
            print(f"[verify] {card.get('content_id')} 심사 실패: {e}", flush=True)
            continue
        if results:
            done += 1
            print(f"[verify] {card.get('content_id')} 심사 완료 "
                  f"({results[0].get('verdict')})", flush=True)
        if done >= limit:
            break
    print(f"[verify] 소급 심사 {done}건 완료", flush=True)
    return done


if __name__ == "__main__":
    store.require_backend()
    if "--backfill" in sys.argv:
        n = 10
        if "--limit" in sys.argv:
            n = int(sys.argv[sys.argv.index("--limit") + 1])
        backfill(n)
    else:
        print("사용법: python3 -m orchestrator.verify --backfill [--limit N]")
