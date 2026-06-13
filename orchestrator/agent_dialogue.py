"""병렬 에이전트 토론 루프 (설계 결정 #5)

작가 → 비평가 → (수정) 작가 → 교육윤리 검수가 제한된 라운드 안에서
서로의 산출물에 피드백을 주고받으며 초안을 업그레이드한다.

원칙:
- 라운드 제한(DIALOGUE_MAX_ROUNDS, 기본 2)으로 끝없는 대화 방지
- 모든 발언은 transcript로 반환되어 노션 카드 본문에 기록된다
"""
import json
from pathlib import Path

from orchestrator import llm, prompts
from orchestrator.config import DIALOGUE_MAX_ROUNDS

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
                       hook_examples: str = "") -> dict:
    """브리프 → 토론을 거친 초안을 생성한다.

    hook_examples: 후킹 DB에서 가져온 후킹 패턴/예시 (없으면 일반 지침만 적용)
    Returns: {"draft": str, "review": dict, "transcript": str, "rounds": int}
    """
    transcript: list[str] = []
    brief_text = json.dumps(brief, ensure_ascii=False, indent=2)
    brief_summary = f"{brief.get('core_message', '')} / CTA: {brief.get('cta', '')}"
    style_block = f"[채널 스타일 가이드]\n{style_context}" if style_context else ""
    hook_block = f"[후킹 예시 - 첫 글 작성 시 참고]\n{hook_examples}" if hook_examples else ""

    draft = llm.call_writing(
        prompts.WRITER.format(
            format=fmt, brief=brief_text, style_context=style_block,
            hook_examples=hook_block, feedback_block="",
        ),
        system=prompts.get_system(),
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
                hook_examples=hook_block,
                feedback_block=(
                    "[비평가 피드백 - 반드시 반영하되 브리프의 핵심 메시지는 유지]\n"
                    f"{feedback}\n\n[직전 초안]\n{draft}"
                ),
            ),
            system=prompts.get_system(),
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

    return {
        "draft": draft,
        "review": review,
        "transcript": "\n\n---\n\n".join(transcript),
        "rounds": rounds,
    }


def get_style_context(channel: str) -> str:
    """Honcho에서 채널 스타일 + 누적 수정 패턴을 가져온다 (기존 시스템 통합, 결정 #2)."""
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
    bench = load_benchmark(channel)
    if bench:
        parts.append(bench)
    return "\n\n".join(parts)
