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
- 첫 번째 글은 강력한 훅(hook)으로 시작 (반전/질문/도발: 상식 뒤집기 + 간결한 1문장)
- 각 글은 280자 이내
- 총 5~8개의 연결된 글로 구성
- 마지막 글은 자연스러운 기원문 + 브랜드로 마무리
- 이모지/이모티콘 절대 사용 금지
- 한국어로 작성
- 각 글 사이에 "---"로 구분

## 구조
1: 훅 (상식 뒤집기)
2: 공감/문제 제기
3~5: 핵심 인사이트 (교육학/심리학 이론 + 예시)
6~7: 가정에서 바로 할 수 있는 실천법
8: 마무리 + CTA

## 문체
- ~입니다/~됩니다 기본 어미. 강조 시 ~인 거죠/~거든요
- 짧은 문장 위주(15자 이내). 긴 설명 후 짧은 단언으로 리듬
- 감정은 절제. 팩트와 논리로 감정을 유발하는 스타일
- 교육학/심리학 이론 인용 필수 (학자명+이론명 명시)
- 'A가 아니라 B이다' 논증 구조 활용

## 마무리
- "아이가 건강하게 자라길 바랍니다."
- "아이와 부모의 꿈을 키웁니다." -Dream_Grow-

## 금지
- 이모지/이모티콘 절대 금지
- ~해요/~했어요 체 금지
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
