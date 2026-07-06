"""문체 diff 학습 - AI 원본과 사람 수정본을 비교해 Honcho에 패턴 저장 (결정 #6)

흐름:
  1. 초안 생성 시 '🗄️ AI 원본 (채널)' 토글에 원본을 보존한다
  2. 사람이 노션에서 '✍️ 초안 (채널)' 토글을 직접 수정한다
  3. 발행 직전 두 버전을 비교 → 수정 패턴을 Claude가 추출
  4. 기존 diff_learner와 같은 Honcho 세션({channel}-corrections)에 저장
     → 다음 초안부터 작가 에이전트 프롬프트에 자동 반영된다
"""
from orchestrator import llm, prompts
from orchestrator import state as notion_state


def get_corrections_context(channel: str) -> str:
    """Honcho에 누적된 수정 패턴을 읽는다 (작가 프롬프트 주입용)."""
    try:
        from memory_manager import get_honcho_client
        client = get_honcho_client()
        if not client:
            return ""
        user = client.peer("content-creator")
        text = user.chat(
            f"{channel}-corrections 세션에 저장된 문체 수정 패턴을 요약해줘. "
            "없으면 '없음'이라고만 답해."
        )
        return "" if not text or text.strip().startswith("없음") else text
    except Exception:
        return ""


def learn_from_edits(page_id: str, channel: str) -> int:
    """AI 원본과 현재 초안을 비교해 수정 패턴을 학습한다.

    Returns: 저장된 패턴 수 (수정이 없거나 학습 불가면 0)
    """
    ai_original = notion_state.read_latest_section(page_id, f"🗄️ AI 원본 ({channel})")
    edited = notion_state.read_latest_section(page_id, f"✍️ 초안 ({channel})")
    if not ai_original.strip() or not edited.strip():
        return 0
    if ai_original.strip() == edited.strip():
        return 0

    analysis = llm.call_json(
        prompts.STYLE_DIFF.format(
            channel=channel, ai_original=ai_original[:12000], edited=edited[:12000],
        ),
        system=prompts.get_system(),
    )
    patterns = analysis.get("patterns", [])
    if not patterns:
        return 0

    saved = 0
    try:
        from memory_manager import get_honcho_client
        client = get_honcho_client()
        if client:
            user = client.peer("content-creator")
            session = client.session(f"{channel}-corrections")
            for p in patterns:
                session.add_messages([user.message(str(p))])
                saved += 1
    except Exception as e:
        print(f"Honcho 저장 실패 (학습 기록은 노션에만 남김): {e}")

    notion_state.append_section(
        page_id, f"🧠 문체 학습 ({channel})",
        f"사람 수정을 감지해 {len(patterns)}개 패턴을 추출했습니다 "
        f"(Honcho 저장 {saved}건). 다음 초안부터 반영됩니다.\n\n"
        + "\n".join(f"- {p}" for p in patterns),
    )
    return saved
