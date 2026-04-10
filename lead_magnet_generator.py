"""리드마그넷 자동 생성기 - 릴스 CTA 연동

릴스 스크립트의 주제/카테고리를 기반으로 부모에게 제공할
리드마그넷(무료 자료)을 자동 생성합니다.

워크플로우:
  [1] 릴스 스크립트 작성 시 리드마그넷 CTA 포함
  [2] 릴스 주제 기반으로 리드마그넷 초안 자동 생성
  [3] 09 리드마그넷/에 저장 (상태: 리뷰대기)
  [4] 사용자 최종 확인 후 상태를 '확정'으로 변경
  [5] Google Drive 파일전송 폴더에 PDF 변환/복사

사용법:
  python3 lead_magnet_generator.py --topic "초등수학 곱셈 로드맵" --category 수학
  python3 lead_magnet_generator.py --from-reels "원고_릴스_수학_초등+수학+2가지.md"
  python3 lead_magnet_generator.py --batch  # 리드마그넷 없는 릴스 전체 처리

리드마그넷 유형:
  - 체크리스트: 부모가 집에서 확인할 항목 목록
  - 개념지도: 학습 영역별 연결 관계도 (텍스트 기반)
  - 실천가이드: 단계별 실천 방법 안내
  - 워크시트: 아이와 함께 할 수 있는 활동지
  - 로드맵: 학년별/시기별 학습 계획표
"""
import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv
import anthropic
from memory_manager import get_honcho_client, get_style_context, get_brand_context

load_dotenv()

SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
REELS_DIR = os.path.join(SNS_SYSTEM, "05 제작/52 원고")
LEADMAGNET_DIR = os.path.join(SNS_SYSTEM, "09 리드마그넷")
GDRIVE_SEND = "/Users/lhg/Library/CloudStorage/GoogleDrive-leehg0211@gmail.com/내 드라이브"

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# 카테고리별 리드마그넷 유형 매핑
CATEGORY_MAGNET_MAP = {
    "수학": ["개념지도", "로드맵", "체크리스트"],
    "훈육": ["실천가이드", "체크리스트", "워크시트"],
    "독서": ["로드맵", "체크리스트", "워크시트"],
    "미디어": ["실천가이드", "체크리스트"],
    "놀이": ["워크시트", "실천가이드"],
    "감정": ["실천가이드", "워크시트", "체크리스트"],
    "학습": ["로드맵", "체크리스트", "실천가이드"],
    "학교": ["체크리스트", "실천가이드"],
    "크리에이터": ["로드맵", "체크리스트"],
}

LEADMAGNET_SYSTEM_PROMPT = """당신은 Dream_Grow(@dream_grow_lee)의 리드마그넷 전문 작가입니다.
현직 초등교사가 부모에게 무료로 제공하는 교육 자료를 작성합니다.

## 리드마그넷이란
- 릴스/스레드에서 "댓글 남기면 자료 보내드릴게요"라고 안내하는 무료 자료
- 부모가 받아서 바로 활용할 수 있어야 함
- A4 1~3장 분량 (인쇄 가능)
- 전문성과 실용성을 동시에 보여주는 자료

## 유형별 구조

### 체크리스트
- 제목 + 대상 (예: "초등 3학년 부모를 위한 독서 습관 체크리스트")
- 10~15개 항목, 각 항목에 체크박스 [ ]
- 항목별 한 줄 설명
- 하단: 점수 해석 가이드

### 개념지도
- 중심 개념 → 하위 개념 연결 (텍스트 기반 다이어그램)
- 학년별 배우는 시기 표시
- 선수학습 ↔ 후속학습 관계 화살표
- 예: "1학년 덧셈 → 2학년 곱셈 → 3학년 나눗셈 → 5학년 약수/배수"

### 실천가이드
- "오늘부터 시작하는 OOO" 형식
- Step 1~5 단계별 안내
- 각 단계: 무엇을 / 어떻게 / 왜 / 주의점
- 하단: 자주 묻는 질문 2~3개

### 워크시트
- 아이와 부모가 함께 작성하는 활동지
- 빈칸 채우기, 선 긋기, 분류하기 등
- 예시 답안 포함 (별도 섹션)

### 로드맵
- 시기별 목표 + 활동 표
- | 시기 | 목표 | 구체적 활동 | 확인 |
- 주간/월간/학기별 단위
- 현실적이고 실천 가능한 수준

## 필수 규칙
- 이모지/이모티콘 절대 사용 금지
- 가짜 통계 금지
- 과장 표현 금지
- 인쇄 시 깔끔하게 보이도록 구조화
- 하단에 반드시: "Dream_Grow | @dream_grow_lee | 아이와 부모의 꿈을 키웁니다."

## 출력 형식
Markdown으로 작성. 인쇄용 PDF 변환을 고려한 깔끔한 포맷.
"""


def extract_reels_info(filepath: str) -> dict:
    """릴스 스크립트 파일에서 주제/카테고리 정보를 추출합니다."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

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

    # 파일명에서 카테고리 추출
    basename = os.path.basename(filepath)
    category = "학습"
    for cat in CATEGORY_MAGNET_MAP:
        if cat in basename or cat in content:
            category = cat
            break

    return {
        'frontmatter': fm,
        'body': body,
        'category': category,
        'filepath': filepath,
        'filename': basename,
    }


def choose_magnet_type(category: str, topic: str) -> str:
    """카테고리와 주제에 맞는 리드마그넷 유형을 선택합니다."""
    types = CATEGORY_MAGNET_MAP.get(category, ["체크리스트", "실천가이드"])

    # 주제 키워드로 유형 미세 조정
    topic_lower = topic.lower()
    if any(kw in topic_lower for kw in ["로드맵", "계열", "순서", "단계별"]):
        return "로드맵"
    if any(kw in topic_lower for kw in ["개념", "연결", "관계", "지도"]):
        return "개념지도"
    if any(kw in topic_lower for kw in ["방법", "실천", "시작", "가이드"]):
        return "실천가이드"
    if any(kw in topic_lower for kw in ["활동", "놀이", "함께", "워크"]):
        return "워크시트"

    return types[0]


def generate_lead_magnet(topic: str, category: str,
                         magnet_type: str = "",
                         reels_content: str = "") -> str:
    """리드마그넷 콘텐츠를 생성합니다."""
    honcho = get_honcho_client()
    brand = get_brand_context(honcho)

    if not magnet_type:
        magnet_type = choose_magnet_type(category, topic)

    system = LEADMAGNET_SYSTEM_PROMPT
    if brand:
        system += f"\n\n## 브랜드 정보\n{brand}\n"

    prompt = f"""아래 정보를 바탕으로 리드마그넷을 작성해주세요.

주제: {topic}
카테고리: {category}
리드마그넷 유형: {magnet_type}
"""
    if reels_content:
        prompt += f"""
## 연결된 릴스 스크립트 (이 릴스의 CTA로 제공되는 자료)
{reels_content[:2000]}
"""
    prompt += f"""
## 요청
- "{magnet_type}" 유형으로 A4 1~3장 분량의 리드마그넷을 작성해주세요.
- 부모가 받자마자 "이거 좋다!" 하고 저장할 수 있는 실용적인 자료여야 합니다.
- 릴스에서 다룬 핵심 내용을 더 깊고 체계적으로 정리해주세요.
- Markdown 형식으로, 인쇄 시 깔끔하게 보이도록 작성해주세요.
"""

    message = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def make_magnet_filename(topic: str, category: str, magnet_type: str) -> str:
    """리드마그넷 파일명을 생성합니다."""
    safe_topic = topic.replace(' ', '_')[:30]
    keywords = '+'.join(safe_topic.split('_')[:3])
    return f"리드마그넷_{magnet_type}_{category}_{keywords}.md"


def save_lead_magnet(content: str, topic: str, category: str,
                     magnet_type: str, source_reels: str = "") -> str:
    """리드마그넷을 파일로 저장합니다."""
    os.makedirs(LEADMAGNET_DIR, exist_ok=True)
    now = datetime.now().strftime('%Y-%m-%d')
    filename = make_magnet_filename(topic, category, magnet_type)
    filepath = os.path.join(LEADMAGNET_DIR, filename)

    source_ref = ""
    if source_reels:
        source_ref = f'\n원본릴스: "[[{os.path.splitext(os.path.basename(source_reels))[0]}]]"'

    full_content = f"""---
type: 리드마그넷
유형: {magnet_type}
상태: 리뷰대기
생성일: {now}
카테고리: {category}
주제: {topic}{source_ref}
---

{content}
"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(full_content)

    print(f"  저장: {filepath}")
    return filepath


def generate_from_reels(reels_filepath: str) -> str:
    """릴스 스크립트로부터 리드마그넷을 생성합니다."""
    info = extract_reels_info(reels_filepath)
    topic = info['frontmatter'].get('주제', '')

    # frontmatter에 주제가 없으면 파일명에서 추출
    if not topic:
        name = os.path.splitext(info['filename'])[0]
        parts = name.replace('원고_릴스_', '').split('_')
        topic = ' '.join(p.replace('+', ' ') for p in parts[1:]) if len(parts) > 1 else parts[0]

    category = info['category']
    magnet_type = choose_magnet_type(category, topic)

    print(f"\n--- 리드마그넷 생성 ---")
    print(f"  릴스: {info['filename']}")
    print(f"  주제: {topic}")
    print(f"  카테고리: {category}")
    print(f"  유형: {magnet_type}")
    print(f"  생성 중...")

    content = generate_lead_magnet(
        topic=topic,
        category=category,
        magnet_type=magnet_type,
        reels_content=info['body'],
    )

    filepath = save_lead_magnet(content, topic, category, magnet_type, reels_filepath)
    print(f"\n  다음 단계: Obsidian에서 확인 후 상태를 '확정'으로 변경하세요.")
    return filepath


def batch_generate():
    """리드마그넷이 없는 릴스를 찾아 일괄 생성합니다."""
    print("일괄 생성 모드 - 리드마그넷 미생성 릴스 검색 중...")

    if not os.path.exists(REELS_DIR):
        print("릴스 원고 폴더가 없습니다.")
        return

    existing_magnets = set()
    if os.path.exists(LEADMAGNET_DIR):
        for f in os.listdir(LEADMAGNET_DIR):
            if f.endswith('.md'):
                existing_magnets.add(f)

    targets = []
    for fname in os.listdir(REELS_DIR):
        if not fname.endswith('.md') or not fname.startswith('원고_릴스_'):
            continue
        filepath = os.path.join(REELS_DIR, fname)

        # 이미 리드마그넷이 있는지 확인 (파일명 키워드 기반)
        keywords = fname.replace('원고_릴스_', '').replace('.md', '')
        has_magnet = any(keywords.split('_')[0] in m for m in existing_magnets)
        if not has_magnet:
            targets.append(filepath)

    if not targets:
        print("생성 대상이 없습니다.")
        return

    print(f"생성 대상: {len(targets)}개\n")
    for filepath in targets:
        generate_from_reels(filepath)


def list_status():
    """리드마그넷 현황을 보여줍니다."""
    if not os.path.exists(LEADMAGNET_DIR):
        print("09 리드마그넷/ 폴더가 없습니다.")
        return

    files = [f for f in os.listdir(LEADMAGNET_DIR) if f.endswith('.md')]
    if not files:
        print("리드마그넷이 없습니다.")
        return

    review = []
    confirmed = []
    for f in files:
        filepath = os.path.join(LEADMAGNET_DIR, f)
        with open(filepath, 'r', encoding='utf-8') as fh:
            content = fh.read()
        if '상태: 리뷰대기' in content:
            review.append(f)
        elif '상태: 확정' in content:
            confirmed.append(f)

    print(f"\n--- 리드마그넷 현황 ---")
    print(f"  리뷰대기: {len(review)}개")
    for f in review:
        print(f"    - {f}")
    print(f"  확정: {len(confirmed)}개")
    for f in confirmed:
        print(f"    - {f}")


def main():
    import argparse

    if '--batch' in sys.argv:
        batch_generate()
        return

    if '--status' in sys.argv:
        list_status()
        return

    if '--from-reels' in sys.argv:
        idx = sys.argv.index('--from-reels')
        if idx + 1 < len(sys.argv):
            reels_path = sys.argv[idx + 1]
            if not os.path.exists(reels_path):
                # REELS_DIR에서 검색
                candidate = os.path.join(REELS_DIR, reels_path)
                if os.path.exists(candidate):
                    reels_path = candidate
            if os.path.exists(reels_path):
                generate_from_reels(reels_path)
            else:
                print(f"파일을 찾을 수 없습니다: {sys.argv[idx + 1]}")
        return

    parser = argparse.ArgumentParser(description='Dream_Grow 리드마그넷 생성기')
    parser.add_argument('--topic', required=True, help='리드마그넷 주제')
    parser.add_argument('--category', default='학습',
                       help='카테고리 (훈육/수학/독서/미디어/놀이/감정/학습/학교)')
    parser.add_argument('--type', default='',
                       help='유형 (체크리스트/개념지도/실천가이드/워크시트/로드맵)')
    args, _ = parser.parse_known_args()

    magnet_type = args.type or choose_magnet_type(args.category, args.topic)

    print(f"리드마그넷 생성: {args.topic}")
    print(f"  카테고리: {args.category}")
    print(f"  유형: {magnet_type}")

    content = generate_lead_magnet(args.topic, args.category, magnet_type)
    filepath = save_lead_magnet(content, args.topic, args.category, magnet_type)

    print(f"\n다음 단계: Obsidian에서 확인 후 상태를 '확정'으로 변경하세요.")


if __name__ == "__main__":
    main()
