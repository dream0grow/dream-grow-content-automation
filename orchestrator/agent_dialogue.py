"""병렬 에이전트 토론 루프 (설계 결정 #5)

작가 → 비평가 → (수정) 작가 → 교육윤리 검수가 제한된 라운드 안에서
서로의 산출물에 피드백을 주고받으며 초안을 업그레이드한다.
검수가 revise를 내면 그 피드백을 작가에게 되먹여 다시 재작성·재검수한다.

원칙:
- 라운드 제한(DIALOGUE_MAX_ROUNDS, 기본 2)으로 비평가 토론의 끝없는 대화 방지
- 검수 되먹임도 라운드 제한(ETHICS_MAX_ROUNDS, 기본 2)으로 무한 재작성 방지
- 모든 발언은 transcript로 반환되어 노션 카드 본문에 기록된다
"""
import json
from pathlib import Path

from orchestrator import llm, prompts
from orchestrator.config import DIALOGUE_MAX_ROUNDS, ETHICS_MAX_ROUNDS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_benchmark(channel: str, limit: int = 9000) -> str:
    """채널별 고성과 과거 글(벤치마킹용)을 읽는다. thread만 해당."""
    if channel != "thread":
        return ""
    path = DATA_DIR / "benchmark_posts.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:limit]


def load_hooks(limit: int = 4000) -> str:
    """후킹 패턴 파일을 읽는다 (작가 hook_examples 주입용)."""
    path = DATA_DIR / "hook_patterns.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:limit]


def run_draft_dialogue(brief: dict, fmt: str, style_context: str = "",
                       hook_examples: str = "", extra_directive: str = "",
                       benchmark: str = "") -> dict:
    """브리프 → 토론을 거친 초안을 생성한다.

    hook_examples/benchmark: 후킹 패턴·고성과 벤치마킹(수 KB). 첫 집필에만 주입하고
      비평/윤리 재작성 호출에서는 뺀다 — 재작성엔 직전 초안+피드백이면 충분하고,
      매 라운드 13KB+를 다시 실어 보내는 토큰 낭비를 없앤다(B5).
    extra_directive: 사람이 남긴 수정 지시(재초안 시). 첫 집필부터 반드시 반영한다.
    Returns: {"draft": str, "review": dict, "transcript": str, "rounds": int}
    """
    transcript: list[str] = []
    brief_text = json.dumps(brief, ensure_ascii=False, indent=2)
    brief_summary = f"{brief.get('core_message', '')} / CTA: {brief.get('cta', '')}"
    # 채널 스타일(학습 문체·수정 패턴)은 작아서 모든 호출에 유지한다.
    style_block = f"[채널 스타일 가이드]\n{style_context}" if style_context else ""
    directive_block = (
        f"[사람의 수정 지시 - 최우선 반영]\n{extra_directive}" if extra_directive.strip() else ""
    )
    # 첫 집필에만 붙이는 무거운 참고 자료(후킹 예시 + 벤치마킹).
    first_draft_parts = []
    if hook_examples:
        first_draft_parts.append(f"[후킹 예시 - 첫 글 작성 시 참고]\n{hook_examples}")
    if benchmark:
        first_draft_parts.append(f"[고성과 벤치마킹 - 첫 글 작성 시 참고]\n{benchmark}")
    first_draft_block = "\n\n".join(first_draft_parts)
    # 뉴스레터는 3,000~6,000자 심화 콘텐츠라 토큰 예산을 크게 잡는다
    write_tokens = 16000 if fmt == "newsletter" else 8000

    draft = llm.call_writing(
        prompts.WRITER.format(
            format=fmt, brief=brief_text, style_context=style_block,
            hook_examples=first_draft_block, feedback_block=directive_block,
        ),
        system=prompts.get_system(),
        max_tokens=write_tokens,
    )
    transcript.append(f"[작가 v1]\n{draft}")

    rounds = 0
    for rounds in range(1, DIALOGUE_MAX_ROUNDS + 1):
        critique = llm.call_json(
            prompts.CRITIC.format(brief_summary=brief_summary, draft=draft),
            system=prompts.get_system(),
        )
        transcript.append(
            f"[비평가 r{rounds}] verdict={critique.get('verdict')}\n"
            + json.dumps(critique, ensure_ascii=False, indent=2)
        )
        if critique.get("verdict") == "pass":
            break
        feedback = "\n".join(
            critique.get("issues", []) + critique.get("suggestions", [])
        )
        draft = llm.call_writing(
            prompts.WRITER.format(
                format=fmt, brief=brief_text, style_context=style_block,
                hook_examples="",  # 재작성엔 무거운 후킹·벤치마킹 재주입 안 함(B5)
                feedback_block=(
                    "[비평가 피드백 - 반드시 반영하되 브리프의 핵심 메시지는 유지]\n"
                    f"{feedback}\n\n[직전 초안]\n{draft}"
                ),
            ),
            system=prompts.get_system(),
            max_tokens=write_tokens,
        )
        transcript.append(f"[작가 v{rounds + 1}]\n{draft}")

    review = llm.call_json(
        prompts.ETHICS_REVIEW.format(draft=draft),
        system=prompts.get_system(),
    )
    transcript.append(
        f"[교육윤리 검수] {review.get('review_status')} / risk={review.get('risk_level')}\n"
        + json.dumps(review, ensure_ascii=False, indent=2)
    )

    # 교육윤리 검수 되먹임 재작성 루프.
    # 검수가 revise면 검수 피드백(issues/revision_suggestions)을 작가에게 되먹여
    # 재작성 후 재검수한다. 이렇게 해야 revise 카드가 사람 손을 안 거치고도
    # approved로 넘어가 발행 승인 게이트까지 자동으로 도달한다.
    # hold/risk(더 심각)는 재작성하지 않고 사람에게 넘긴다. approved면 즉시 종료.
    for ethics_round in range(1, ETHICS_MAX_ROUNDS + 1):
        if review.get("review_status") != "revise":
            break
        ethics_feedback = "\n".join(
            review.get("issues", []) + review.get("revision_suggestions", [])
        ).strip()
        if not ethics_feedback:
            break  # 되먹일 구체적 피드백이 없으면 재작성 불가 → 사람에게
        draft = llm.call_writing(
            prompts.WRITER.format(
                format=fmt, brief=brief_text, style_context=style_block,
                hook_examples="",  # 재작성엔 무거운 후킹·벤치마킹 재주입 안 함(B5)
                feedback_block=(
                    "[교육윤리 검수 피드백 - 반드시 반영. 부모 죄책감/공포 유발, "
                    "아이 낙인 표현, 효과 과장·미검증 통계를 제거하되 "
                    "브리프의 핵심 메시지와 후킹은 유지]\n"
                    f"{ethics_feedback}\n\n[직전 초안]\n{draft}"
                ),
            ),
            system=prompts.get_system(),
            max_tokens=write_tokens,
        )
        transcript.append(f"[작가 - 윤리수정 v{ethics_round}]\n{draft}")
        review = llm.call_json(
            prompts.ETHICS_REVIEW.format(draft=draft),
            system=prompts.get_system(),
        )
        transcript.append(
            f"[교육윤리 재검수 r{ethics_round}] {review.get('review_status')} / "
            f"risk={review.get('risk_level')}\n"
            + json.dumps(review, ensure_ascii=False, indent=2)
        )

    return {
        "draft": draft,
        "review": review,
        "transcript": "\n\n---\n\n".join(transcript),
        "rounds": rounds,
    }


def get_style_context(channel: str) -> str:
    """Honcho에서 채널 스타일 + 누적 수정 패턴을 가져온다 (기존 시스템 통합, 결정 #2).

    벤치마킹(수 KB)은 여기 넣지 않는다 — 매 재작성 호출에 실려 낭비되므로
    run_draft_dialogue(benchmark=...)로 넘겨 첫 집필에만 주입한다(B5).
    """
    parts = []
    try:
        from memory_manager import get_honcho_client, get_style_context as honcho_style
        client = get_honcho_client()
        if client:
            style = honcho_style(client, channel)
            if style:
                parts.append(style)
    except Exception:
        pass
    try:
        from orchestrator.style_learn import get_corrections_context
        corrections = get_corrections_context(channel)
        if corrections:
            parts.append(f"[사람 수정에서 학습된 패턴 - 반드시 반영]\n{corrections}")
    except Exception:
        pass
    return "\n\n".join(parts)
