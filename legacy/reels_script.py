"""릴스 스크립트 자동 생성기 - Claude API 기반"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import claude_client; claude_client.patch_anthropic()
import anthropic

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

REELS_SYSTEM_PROMPT = """당신은 인스타그램 릴스/숏폼 영상 전문 스크립트 작가입니다.
규칙:
- 총 길이: 30초~90초 분량
- 구성: 훅(3초) → 본문 → CTA
- 훅은 시청자가 스크롤을 멈추게 만드는 강력한 한 문장
- 자막 텍스트와 내레이션을 구분해서 작성
- 화면 연출 지시도 포함
- 한국어로 작성

출력 형식:
## 릴스 스크립트

**컨셉:** (한 줄 요약)
**예상 길이:** N초
**BGM 분위기:** (추천)

| 시간 | 화면 | 자막/텍스트 | 내레이션 |
|------|------|-------------|----------|
| 0-3초 | ... | ... | ... |
| ... | ... | ... | ... |

**해시태그 추천:** #태그1 #태그2 ...
"""


def generate_reels_script(topic: str, style: str = "정보 전달형") -> str:
    """주제와 스타일을 받아 릴스 스크립트를 생성합니다."""
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=REELS_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"주제: {topic}\n스타일: {style}\n\n위 주제로 릴스 스크립트를 작성해주세요.",
            }
        ],
    )
    return message.content[0].text


def save_script(content: str, topic: str, script_type: str = "reels"):
    """생성된 스크립트를 파일로 저장합니다."""
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = topic.replace(" ", "_")[:30]
    filename = f"output/{script_type}_{safe_topic}_{timestamp}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# 주제: {topic}\n# 생성일: {datetime.now().isoformat()}\n\n")
        f.write(content)
    print(f"저장 완료: {filename}")
    return filename


def main():
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = input("릴스 주제를 입력하세요: ")

    print("스타일 선택:")
    print("  1. 정보 전달형 (기본)")
    print("  2. 스토리텔링형")
    print("  3. Before/After형")
    print("  4. 리스트형 (Top 3, 5가지 등)")
    style_map = {"1": "정보 전달형", "2": "스토리텔링형", "3": "Before/After형", "4": "리스트형"}
    choice = input("번호 선택 (기본: 1): ").strip()
    style = style_map.get(choice, "정보 전달형")

    print(f"\n'{topic}' 주제로 릴스 스크립트 생성 중...\n")
    script = generate_reels_script(topic, style)
    print(script)
    print()
    save_script(script, topic)


if __name__ == "__main__":
    main()
