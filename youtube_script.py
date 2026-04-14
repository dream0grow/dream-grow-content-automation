"""유튜브 스크립트 자동 생성기 - Claude API 기반"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import claude_client; claude_client.patch_anthropic()
import anthropic

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

YOUTUBE_SYSTEM_PROMPT = """당신은 유튜브 영상 전문 스크립트 작가입니다.
규칙:
- 구성: 인트로(훅+주제소개) → 본문(3~5개 섹션) → 아웃트로(요약+CTA)
- 인트로 훅은 15초 이내로 시청자를 사로잡는 질문 또는 놀라운 사실
- 각 섹션은 자연스럽게 다음으로 연결
- 대본은 말하듯이 자연스럽게 작성
- 예상 영상 길이: 8~15분 분량
- 한국어로 작성

출력 형식:

## 유튜브 스크립트

**제목 후보 (3개):**
1. ...
2. ...
3. ...

**썸네일 텍스트 제안:** ...
**예상 길이:** N분

---

### 🎬 인트로 (0:00~0:30)
[훅]
...
[주제 소개]
...

### 📌 섹션 1: 제목
...

### 📌 섹션 2: 제목
...

(계속)

### 🎯 아웃트로
[요약]
...
[CTA]
...

---
**태그 추천:** 태그1, 태그2, ...
**설명란 문구:**
...
"""


def generate_youtube_script(topic: str, target_audience: str = "20~40대 일반") -> str:
    """주제와 타겟 오디언스를 받아 유튜브 스크립트를 생성합니다."""
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4000,
        system=YOUTUBE_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"주제: {topic}\n타겟 오디언스: {target_audience}\n\n위 주제로 유튜브 스크립트를 작성해주세요.",
            }
        ],
    )
    return message.content[0].text


def save_script(content: str, topic: str):
    """생성된 스크립트를 파일로 저장합니다."""
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = topic.replace(" ", "_")[:30]
    filename = f"output/youtube_{safe_topic}_{timestamp}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# 주제: {topic}\n# 생성일: {datetime.now().isoformat()}\n\n")
        f.write(content)
    print(f"저장 완료: {filename}")
    return filename


def main():
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = input("유튜브 영상 주제를 입력하세요: ")

    audience = input("타겟 오디언스 (기본: 20~40대 일반): ").strip()
    if not audience:
        audience = "20~40대 일반"

    print(f"\n'{topic}' 주제로 유튜브 스크립트 생성 중...\n")
    script = generate_youtube_script(topic, audience)
    print(script)
    print()
    save_script(script, topic)


if __name__ == "__main__":
    main()
