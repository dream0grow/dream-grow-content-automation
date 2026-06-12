"""Honcho 메모리 매니저 - 채널별 콘텐츠 스타일 개인화

지원 채널: thread, reels, youtube, blog, book
Honcho 세션 구조:
  - {channel}-style: 채널별 스타일 패턴 (추출된 톤/구조/금지사항)
  - {channel}-feedback: 사용자 피드백 누적
  - brand-identity: 브랜드 공통 정보
"""
import os
from dotenv import load_dotenv
from honcho import Honcho

load_dotenv()

CHANNELS = ["thread", "reels", "youtube", "blog", "book", "newsletter"]


def get_honcho_client() -> Honcho | None:
    """Honcho 클라이언트를 초기화합니다."""
    api_key = os.getenv("HONCHO_API_KEY")
    if not api_key:
        print("Honcho API 키가 설정되지 않았습니다. 메모리 기능 비활성화.")
        return None
    return Honcho(api_key=api_key)


def save_content_feedback(client: Honcho, channel: str, topic: str, feedback: str):
    """생성된 콘텐츠에 대한 피드백을 저장합니다.

    예: save_content_feedback(client, "thread", "AI 트렌드", "톤이 너무 딱딱했어")
    """
    if not client:
        return

    user = client.peer("content-creator")
    session = client.session(f"{channel}-feedback")
    session.add_messages([
        user.message(f"주제: {topic}\n피드백: {feedback}\n채널: {channel}"),
    ])
    print(f"피드백 저장 완료 ({channel}: {topic})")


def get_style_context(client: Honcho, channel: str) -> str:
    """채널별 스타일 컨텍스트를 Honcho에서 조회합니다.

    {channel}-style 세션의 메시지를 읽어 스타일 가이드를 반환합니다.
    """
    if not client:
        return ""

    try:
        user = client.peer("content-creator")
        context = user.chat(
            f"{channel} 채널의 콘텐츠 스타일 가이드를 요약해줘. "
            f"톤, 구조, 금지사항, 훅 패턴을 포함해서 알려줘."
        )
        return context
    except Exception:
        return ""


def get_brand_context(client: Honcho) -> str:
    """브랜드 공통 정보를 Honcho에서 조회합니다."""
    if not client:
        return ""

    try:
        user = client.peer("content-creator")
        context = user.chat(
            "Dream_Grow 브랜드의 핵심 정보를 요약해줘. "
            "슬로건, 타겟, 카테고리, 고성과 공식을 포함해서."
        )
        return context
    except Exception:
        return ""


def save_team_learning(client: Honcho, channel: str, learning_type: str, content: str):
    """에이전트 팀 작업 중 발견한 학습 내용을 Honcho에 저장합니다.

    learning_type: 'style', 'correction', 'pattern', 'feedback'
    예: save_team_learning(client, "thread", "pattern", "후킹에 수치보다 반전 질문이 더 효과적")
    """
    if not client:
        return

    session_name = f"{channel}-team-learnings"
    user = client.peer("content-creator")
    session = client.session(session_name)
    session.add_messages([
        user.message(f"[{learning_type}] {content}"),
    ])
    print(f"  팀 학습 저장: {channel}/{learning_type}")


def get_team_learnings(client: Honcho, channel: str) -> str:
    """에이전트 팀이 축적한 학습 데이터를 조회합니다."""
    if not client:
        return ""

    try:
        user = client.peer("content-creator")
        context = user.chat(
            f"{channel} 채널의 에이전트 팀 학습 데이터를 요약해줘. "
            f"스타일 패턴, 수정 패턴, 효과적인 공식을 포함해서."
        )
        return context
    except Exception:
        return ""


def get_full_context(client: Honcho, channel: str) -> dict:
    """채널의 모든 Honcho 컨텍스트를 한번에 조회합니다.

    팀 에이전트가 사용할 통합 컨텍스트.
    Returns: {'style': str, 'brand': str, 'corrections': str, 'team_learnings': str}
    """
    if not client:
        return {'style': '', 'brand': '', 'corrections': '', 'team_learnings': ''}

    from diff_learner import get_correction_context

    return {
        'style': get_style_context(client, channel),
        'brand': get_brand_context(client),
        'corrections': get_correction_context(client, channel),
        'team_learnings': get_team_learnings(client, channel),
    }


def main():
    """메모리 기능 테스트"""
    client = get_honcho_client()
    if not client:
        print("\nHoncho를 사용하려면:")
        print("1. https://docs.honcho.dev 에서 API 키 발급")
        print("2. .env 파일에 HONCHO_API_KEY 설정")
        return

    print("Honcho 메모리 매니저 연결 완료!")
    print(f"지원 채널: {', '.join(CHANNELS)}")

    print("\n=== 스타일 컨텍스트 테스트 ===")
    for ch in CHANNELS:
        ctx = get_style_context(client, ch)
        preview = ctx[:100] + "..." if len(ctx) > 100 else ctx
        print(f"  {ch}: {preview if preview else '(없음)'}")

    brand = get_brand_context(client)
    preview = brand[:100] + "..." if len(brand) > 100 else brand
    print(f"  brand: {preview if preview else '(없음)'}")


if __name__ == "__main__":
    main()
