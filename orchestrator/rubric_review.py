"""평가표 기반 AI 검토 + 2차안(줄바꿈 교정) 생성.

인플루언서 본인 글 기준 평가표(data/thread_rubric.md, prompts.RUBRIC_REVIEW)에 대비해
카드의 '✍️ 초안'을 채점하고, 약점을 고친 '✍️ 2차안'을 새 토글로 카드에 기록한다.
실패해도 파이프라인을 멈추지 않도록 호출부에서 try/except로 감싼다.
"""
from orchestrator import llm, prompts
from orchestrator import state as store


def _fmt_eval(r: dict) -> str:
    """평가표 채점 결과를 읽기 좋은 마크다운으로."""
    scores = r.get("scores", {}) or {}
    parts = [
        f"## 총점 {r.get('total', '?')}/100 (문체 40·구조 30·논리성 30)",
        f"- 문체: {scores.get('문체', '?')}/40",
        f"- 구조: {scores.get('구조', '?')}/30",
        f"- 논리성: {scores.get('논리성', '?')}/30",
        f"\n**항목 상세**: {r.get('breakdown', '')}",
        f"**가장 약한 부분**: {r.get('weakest', '')}",
    ]
    fixes = r.get("fixes") or []
    if fixes:
        parts.append("**2차안에서 고친 점**\n" + "\n".join(f"- {x}" for x in fixes))
    return "\n".join(parts)


def review(draft: str, fmt: str) -> dict:
    """초안을 평가표로 채점하고 2차안을 담은 dict를 반환한다."""
    return llm.call_json(
        prompts.RUBRIC_REVIEW.format(
            format=fmt, draft=draft, line_break_rule=prompts.LINE_BREAK_RULE,
        ),
        system=prompts.get_system(),
        max_tokens=8000,
    )


def run_for_card(page_id: str, fmt: str, *, skip_if_exists: bool = True) -> bool:
    """'✍️ 초안 (fmt)'을 평가표로 검토해 '📐 평가표 점검'과 '✍️ 2차안 (fmt)'을 추가한다.

    Returns: 2차안을 추가했으면 True. (초안 없음/이미 2차안 있음/빈 결과는 False)
    """
    if skip_if_exists and store.read_latest_section(
        page_id, f"✍️ 2차안 ({fmt})"
    ).strip():
        return False  # 이미 2차안이 있으면 건너뛴다 (idempotent)

    draft = (
        store.read_latest_section(page_id, f"✍️ 초안 ({fmt})")
        or store.read_latest_section(page_id, "✍️ 초안")
    )
    if not draft.strip():
        return False

    result = review(draft, fmt)
    store.append_formatted_section(
        page_id,
        f"📐 평가표 점검 ({fmt}) - 총 {result.get('total', '?')}/100",
        _fmt_eval(result),
    )
    revised = (result.get("revised") or "").strip()
    if revised:
        store.append_section(page_id, f"✍️ 2차안 ({fmt})", revised)
    return bool(revised)
