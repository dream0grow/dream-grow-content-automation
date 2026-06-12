"""릴스 스크립트 자동 생성기 (스레드 변환 + 주제 직접 입력)

검토완료된 스레드를 기반으로:
1. 45초 릴스 스크립트 자동 생성
2. B-roll 장면 목록 생성 (Pexels/Pixabay 검색 키워드 포함)
3. 05 제작/52 원고/에 저장

주제만으로 새 릴스 스크립트 생성도 가능 (구 reels_script.py 통합).

사용법:
  python3 auto_reels_from_thread.py "스레드파일경로.md"
  python3 auto_reels_from_thread.py --batch          # 최근 발행된 스레드 전체 변환
  python3 auto_reels_from_thread.py --topic "주제"   # 주제만으로 새 릴스 생성
"""
import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv
import claude_client; claude_client.patch_anthropic()
import anthropic
from memory_manager import get_honcho_client, get_style_context

load_dotenv()

SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
THREAD_DIR = os.path.join(SNS_SYSTEM, "07 스레드")
REELS_DIR = os.path.join(SNS_SYSTEM, "05 제작/52 원고")

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

REELS_SYSTEM_PROMPT = """당신은 Dream_Grow(@dream_grow_lee)의 릴스 스크립트 작가입니다.
스레드 글을 35~45초 릴스 스크립트로 변환합니다.

## 필수 규칙
- 이모지/이모티콘 절대 사용 금지
- 가짜 통계 금지
- '돕습니다' 마무리 금지

## 릴스 구조
[0~3초] 후킹 - 반전형/충격형 한 문장 (스레드의 핵심 훅 압축)
[3~10초] 문제 공감 - 부모가 공감할 상황
[10~25초] 핵심 인사이트 - 스레드의 핵심 이론/주장 1가지만 압축
[25~38초] 실천법 - 가정에서 바로 할 수 있는 것 1~2가지
[38~45초] 마무리 + CTA

## 톤
- 스레드보다 구어체 허용 (~거든요, ~잖아요)
- 짧은 문장, 빠른 리듬
- (화면: ) 으로 B-roll 연출 지시 포함

## 마무리 + 리드마그넷 CTA
- 핵심 내용 요약 한 문장
- "이외에도 OOO 더 알고 싶으신 분들은"
- "아무 댓글이나 남겨주세요."
- "OOO 자료 보내드릴게요."
- (화면: 리드마그넷 미리보기 이미지 + "댓글 남기면 무료 자료 전송" 텍스트)
- "아이가 건강하게 자라길 바랍니다."

중요: 마지막 CTA에서 제공할 리드마그넷의 구체적인 이름을 명시할 것.
예시: "초등수학 영역별 로드맵 자료", "훈육 실천 체크리스트", "독서 습관 가이드"

## B-roll 장면 목록
스크립트 아래에 별도 섹션으로 B-roll 장면 목록을 작성:
- 각 타임코드별 필요한 영상 장면 설명
- Pexels/Pixabay 검색 키워드 (영어)
- 대체 가능한 장면 옵션
"""


def read_thread_file(filepath: str) -> dict:
    """스레드 파일을 읽어 파싱합니다."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # frontmatter
    fm = {}
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if match:
        for line in match.group(1).split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                fm[key.strip()] = val.strip().strip('"').strip("'")
        body = content[match.end():].strip()
    else:
        body = content.strip()

    return {'frontmatter': fm, 'body': body, 'filepath': filepath}


KNOWN_CATEGORIES = ('훈육', '수학', '독서', '미디어', '놀이', '감정', '학습', '학교', '크리에이터')

OUTPUT_FORMAT = """## 출력 형식

### 릴스 스크립트
(타임코드 + 대사 + 화면 지시)
마지막에 반드시 리드마그넷 CTA 포함:
"OOO 더 알고 싶으신 분들은 아무 댓글이나 남겨주세요. OOO 자료 보내드릴게요."

### 리드마그넷 제안
- 리드마그넷 이름: (예: "초등수학 영역별 개념 로드맵")
- 리드마그넷 유형: (체크리스트/개념지도/실천가이드/워크시트/로드맵 중 택1)
- 핵심 내용 3줄 요약:

### B-roll 장면 목록
| 타임코드 | 장면 설명 | 검색 키워드 (영어) | 대체 옵션 |
|----------|-----------|-------------------|-----------|
| 0~3초 | ... | ... | ... |
"""


def detect_category(content: str, filename: str) -> str:
    """파일에서 카테고리를 추출합니다."""
    # 경로에서 카테고리 추출 시도
    path_parts = filename.replace('\\', '/').split('/')
    for part in path_parts:
        if part in KNOWN_CATEGORIES:
            return part
    return '학습'


def build_system_prompt() -> str:
    """기본 프롬프트 + Honcho 릴스 스타일 가이드."""
    honcho = get_honcho_client()
    reels_style = get_style_context(honcho, "reels")

    system = REELS_SYSTEM_PROMPT
    if reels_style:
        system += f"\n\n## Honcho 릴스 스타일 가이드\n{reels_style}\n"
    return system


def generate_reels_from_thread(thread_content: str, category: str) -> str:
    """스레드 내용을 기반으로 릴스 스크립트 + B-roll을 생성합니다."""
    prompt = f"""아래 스레드 글을 45초 릴스 스크립트로 변환해주세요.
카테고리: {category}

## 원본 스레드
{thread_content[:3000]}

{OUTPUT_FORMAT}"""

    message = claude.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        system=build_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def generate_reels_from_topic(topic: str, category: str, style: str = "정보 전달형") -> str:
    """주제만으로 릴스 스크립트 + B-roll을 생성합니다 (구 reels_script.py)."""
    prompt = f"""아래 주제로 45초 릴스 스크립트를 새로 작성해주세요.
주제: {topic}
카테고리: {category}
스타일: {style}

{OUTPUT_FORMAT}"""

    message = claude.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=build_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def make_reels_filename(thread_filename: str, category: str) -> str:
    """스레드 파일명에서 릴스 파일명을 생성합니다."""
    name = os.path.splitext(thread_filename)[0]
    # 기존 키워드 추출
    words = re.sub(r'[^\w\s가-힣]', '', name).strip()
    keywords = '+'.join(words.split()[:3])
    return f"원고_릴스_{category}_{keywords}.md"


def save_reels_script(content: str, filename: str, source: str) -> str:
    """릴스 스크립트를 저장합니다. source는 frontmatter 원본 필드에 그대로 기록."""
    now = datetime.now().strftime('%Y-%m-%d')
    filepath = os.path.join(REELS_DIR, filename)

    full_content = f"""---
type: 릴스스크립트
상태: 초안
생성일: {now}
원본: {source}
채널: Instagram Reels
길이: 45초
---

{content}
"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(full_content)

    print(f"  저장: {filename}")
    return filepath


def process_single_thread(filepath: str):
    """단일 스레드 파일을 릴스로 변환합니다."""
    print(f"\n--- 릴스 변환: {os.path.basename(filepath)} ---")
    thread = read_thread_file(filepath)
    category = detect_category(thread['body'], filepath)

    print(f"  카테고리: {category}")
    print("  릴스 스크립트 생성 중...")

    reels_content = generate_reels_from_thread(thread['body'], category)
    reels_filename = make_reels_filename(os.path.basename(filepath), category)

    source = f'"[[{os.path.splitext(os.path.basename(filepath))[0]}]]"'
    saved = save_reels_script(reels_content, reels_filename, source)
    return saved


def process_topic(topic: str, category: str = "", style: str = "정보 전달형"):
    """주제만으로 릴스 스크립트를 생성합니다."""
    category = category or next((c for c in KNOWN_CATEGORIES if c in topic), '학습')

    print(f"\n--- 릴스 생성 (주제 직접 입력): {topic} ---")
    print(f"  카테고리: {category} / 스타일: {style}")
    print("  릴스 스크립트 생성 중...")

    reels_content = generate_reels_from_topic(topic, category, style)
    reels_filename = make_reels_filename(topic, category)

    saved = save_reels_script(reels_content, reels_filename, f"주제 직접 입력 - {topic}")
    return saved


def topic_main():
    """대화형 주제 입력 모드 (main.py 메뉴에서 호출)."""
    topic = input("릴스 주제를 입력하세요: ").strip()
    if not topic:
        print("주제가 입력되지 않았습니다.")
        return

    print("스타일 선택:")
    print("  1. 정보 전달형 (기본)")
    print("  2. 스토리텔링형")
    print("  3. Before/After형")
    print("  4. 리스트형 (Top 3, 5가지 등)")
    style_map = {"1": "정보 전달형", "2": "스토리텔링형", "3": "Before/After형", "4": "리스트형"}
    choice = input("번호 선택 (기본: 1): ").strip()
    style = style_map.get(choice, "정보 전달형")

    process_topic(topic, style=style)


def batch_process():
    """최근 발행완료된 스레드를 일괄 변환합니다."""
    print("일괄 변환 모드 - 발행완료 스레드 검색 중...")
    targets = []

    for category in os.listdir(THREAD_DIR):
        cat_dir = os.path.join(THREAD_DIR, category)
        if not os.path.isdir(cat_dir) or category.startswith('.') or category == '초안':
            continue
        for fname in os.listdir(cat_dir):
            if not fname.endswith('.md'):
                continue
            filepath = os.path.join(cat_dir, fname)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            if '상태: 발행완료' in content or '상태: 검토완료' in content:
                # 이미 릴스가 있는지 확인
                reels_name = make_reels_filename(fname, category)
                if not os.path.exists(os.path.join(REELS_DIR, reels_name)):
                    targets.append(filepath)

    if not targets:
        print("변환 대상이 없습니다.")
        return

    print(f"변환 대상: {len(targets)}개\n")
    for filepath in targets:
        process_single_thread(filepath)


def main():
    if '--batch' in sys.argv:
        batch_process()
    elif '--topic' in sys.argv:
        idx = sys.argv.index('--topic')
        if idx + 1 >= len(sys.argv):
            print('사용법: python3 auto_reels_from_thread.py --topic "주제"')
            return
        process_topic(sys.argv[idx + 1])
    elif len(sys.argv) > 1:
        filepath = sys.argv[1]
        if not os.path.exists(filepath):
            # 07 스레드 하위에서 검색
            for cat in os.listdir(THREAD_DIR):
                candidate = os.path.join(THREAD_DIR, cat, filepath)
                if os.path.exists(candidate):
                    filepath = candidate
                    break
        if os.path.exists(filepath):
            process_single_thread(filepath)
        else:
            print(f"파일을 찾을 수 없습니다: {sys.argv[1]}")
    else:
        print("사용법:")
        print('  python3 auto_reels_from_thread.py "스레드파일.md"')
        print("  python3 auto_reels_from_thread.py --batch")
        print('  python3 auto_reels_from_thread.py --topic "주제"')


if __name__ == "__main__":
    main()
