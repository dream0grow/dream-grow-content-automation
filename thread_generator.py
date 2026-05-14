"""스레드 글 자동 생성기 - Claude API + Honcho 메모리 기반

Dream_Grow(@dream_grow_lee) 스레드 자동 생성기.
Honcho에 저장된 스타일 패턴을 기반으로 일관된 톤의 스레드를 생성합니다.
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import claude_client; claude_client.patch_anthropic()
import anthropic
from memory_manager import get_honcho_client, get_style_context, get_brand_context, save_content_feedback

load_dotenv()

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

THREAD_SYSTEM_PROMPT = """당신은 Dream_Grow(@dream_grow_lee)의 SNS 스레드 전문 작가입니다.
현직 초등교사의 관점에서, 초등 자녀를 둔 부모를 위한 교육 스레드를 작성합니다.

## 필수 규칙
- 작성 전 먼저 주제 성격을 판단하고, 그 주제에 맞는 구조를 선택
- 같은 구조 반복 금지. 이전 글과 비슷한 뼈대가 되면 후킹/전개 방식을 바꿀 것
- 첫 번째 글은 주제에 맞는 훅으로 시작 (대사/질문/관찰/경고/고백/개념 반전/대상 직접 호명 중 선택)
- 각 글은 280자 이내
- 총 분량은 주제에 맞게 조절. 1파트 단문, 5~8개 연결 글 모두 가능
- 마지막 글은 자연스러운 기원문 + 브랜드로 마무리
- 이모지/이모티콘 절대 사용 금지
- 한국어로 작성
- 각 글 사이에 "---"로 구분

## 구조 선택 원칙
- 상담/대화법: 아이/부모 대사 -> 의미 재해석 -> 잘못된 반응 -> 더 나은 질문/반응
- 수학/개념: 부모 오해 -> 개념 충돌 지점 -> 구체물/생활 예시 -> 단계별 이해
- 훈육/미디어: 악순환 장면 -> 접근 방향 재설정 -> 아이 상태별 단계 -> 가정 규칙
- 감정/심리: 대상 직접 호명 또는 아이 대사 -> 1차 감정/신호 해석 -> 부모 반응 교정
- 놀이/독서/자연: 계절/일상 장면 -> 경험 가치 -> 관찰/상상/관계 확장
- 학교생활/공동체: 교실에서 보이는 고민 -> 부모가 놓치는 기준 -> 짧은 경고형 단문 가능
- AI/크리에이터: 시대 변화 경고 -> 자기반성/사용 경험 -> 핵심 개념 재정의 -> 아이에게 필요한 방향
- 위 구조는 예시다. 주제에 따라 새 구조를 만들어도 된다.

## 문체
- 존댓말 기반에 구어체를 자연스럽게 섞기: ~거든요, ~잖아요, ~해요, ~입니다
- 짧은 문장과 자연스럽게 이어지는 문장을 섞어 리듬 만들기
- 감정은 문장형 고백과 장면으로 표현. 이모지/이모티콘은 금지
- 이론/연구는 필요할 때만 1개 깊게 설명. 학자명 나열 금지
- 'A가 아니라 B이다'는 선택 가능한 논증 재료이지 고정 템플릿이 아님

## 마무리
- "아이가 건강하게 자라길 바랍니다."
- "아이와 부모의 꿈을 키웁니다." -Dream_Grow-

## 금지
- 이모지/이모티콘 절대 금지
- 가짜 통계(출처 없는 %) 금지
- 과장 표현(무려/놀랍게도) 금지
- '돕습니다' 마무리 금지

## 출력 형식
[1/N] 첫 번째 글 내용
---
[2/N] 두 번째 글 내용
---
...
"""


def generate_thread(topic: str, tone: str = "전문적이면서 친근한", category: str = "") -> str:
    """주제와 톤을 받아 스레드를 생성합니다. Honcho 스타일 컨텍스트를 활용합니다."""

    # Honcho에서 스타일 + 수정학습 컨텍스트 조회
    honcho = get_honcho_client()
    style_context = get_style_context(honcho, "thread")
    brand_context = get_brand_context(honcho)

    # 사용자 수정 패턴 반영 (diff_learner가 저장한 학습 데이터)
    from diff_learner import get_correction_context
    correction_context = get_correction_context(honcho, "thread")

    # 시스템 프롬프트에 Honcho 컨텍스트 추가
    system = THREAD_SYSTEM_PROMPT
    if style_context or brand_context:
        system += "\n\n## Honcho 메모리 기반 스타일 가이드\n"
        if style_context:
            system += f"\n### 스레드 스타일\n{style_context}\n"
        if brand_context:
            system += f"\n### 브랜드 정보\n{brand_context}\n"
        if correction_context:
            system += f"\n### 사용자 수정 학습 (과거 AI 초안에서 사용자가 수정한 패턴)\n{correction_context}\n"

    user_msg = f"주제: {topic}\n톤: {tone}"
    if category:
        user_msg += f"\n카테고리: {category}"
    user_msg += "\n\n위 주제로 스레드를 작성해주세요."

    message = claude.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return message.content[0].text


def save_thread(content: str, topic: str):
    """생성된 스레드를 파일로 저장합니다."""
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = topic.replace(" ", "_")[:30]
    filename = f"output/thread_{safe_topic}_{timestamp}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# 주제: {topic}\n# 생성일: {datetime.now().isoformat()}\n\n")
        f.write(content)
    print(f"저장 완료: {filename}")
    return filename


def main():
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = input("스레드 주제를 입력하세요: ")

    tone = input("톤을 입력하세요 (기본: 전문적이면서 친근한): ").strip()
    if not tone:
        tone = "전문적이면서 친근한"

    category = input("카테고리 (훈육/수학/독서/미디어/놀이/감정): ").strip()

    print(f"\n'{topic}' 주제로 스레드 생성 중...\n")
    thread = generate_thread(topic, tone, category)
    print(thread)
    print()
    filepath = save_thread(thread, topic)

    # 피드백 루프
    feedback = input("\n피드백이 있으면 입력하세요 (없으면 Enter): ").strip()
    if feedback:
        honcho = get_honcho_client()
        save_content_feedback(honcho, "thread", topic, feedback)


if __name__ == "__main__":
    main()
