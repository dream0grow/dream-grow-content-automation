"""Diff 학습기 - AI 초안과 사용자 수정본을 비교하여 스타일 패턴을 학습

지원 채널: thread, reels, youtube, blog, newsletter

워크플로우:
  1. AI가 08 리뷰/에 초안 생성 (frontmatter: 상태: 리뷰대기, AI원본 사본 저장)
  2. 사용자가 Obsidian에서 수정
  3. 사용자가 frontmatter 상태를 '리뷰완료'로 변경
  4. 이 스크립트가 감지하여:
     a. .ai_drafts/에 저장된 원본과 현재 파일의 diff 추출
     b. 변경 패턴을 분석하여 Honcho에 저장
     c. 채널별 대상 폴더로 이동:
        - thread → 07 스레드/[카테고리]/
        - reels/youtube/blog/newsletter → 05 제작/52 원고/ (그대로 유지)
"""
import os
import re
import difflib
from datetime import datetime
from dotenv import load_dotenv
import anthropic
from memory_manager import get_honcho_client

load_dotenv()

# 경로 설정
SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
REVIEW_DIR = os.path.join(SNS_SYSTEM, "08 리뷰")
THREAD_DIR = os.path.join(SNS_SYSTEM, "07 스레드")
SCRIPT_DIR = os.path.join(SNS_SYSTEM, "05 제작", "52 원고")
AI_DRAFTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".ai_drafts"
)

# 채널 감지 매핑: frontmatter type/채널 값 → Honcho 채널명
CHANNEL_MAP = {
    'thread': 'thread', '스레드': 'thread', 'Threads': 'thread',
    'reels': 'reels', '릴스': 'reels', '릴스스크립트': 'reels',
    'Instagram Reels': 'reels',
    'youtube': 'youtube', 'YT롱폼': 'youtube', '영상스크립트': 'youtube',
    '영상원고': 'youtube', 'YouTube': 'youtube',
    'blog': 'blog', '블로그': 'blog',
    'newsletter': 'newsletter', '뉴스레터': 'newsletter',
    'book': 'book', '책': 'book',
}

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def parse_frontmatter(content: str) -> dict:
    """Obsidian frontmatter를 파싱합니다."""
    fm = {}
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return fm
    for line in match.group(1).split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm


def save_ai_draft(filepath: str):
    """AI가 생성한 원본을 .ai_drafts/에 백업합니다.
    thread_generator.py 등에서 08 리뷰/에 파일 생성 시 호출.
    """
    os.makedirs(AI_DRAFTS_DIR, exist_ok=True)
    filename = os.path.basename(filepath)
    draft_path = os.path.join(AI_DRAFTS_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    with open(draft_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return draft_path


def compute_diff(original: str, edited: str) -> dict:
    """AI 원본과 수정본의 차이를 분석합니다."""
    orig_lines = original.splitlines()
    edit_lines = edited.splitlines()

    # 기본 diff 통계
    differ = difflib.unified_diff(orig_lines, edit_lines, lineterm='')
    diff_lines = list(differ)

    added = [l[1:] for l in diff_lines if l.startswith('+') and not l.startswith('+++')]
    removed = [l[1:] for l in diff_lines if l.startswith('-') and not l.startswith('---')]

    # frontmatter 제외한 본문만 비교
    def strip_fm(text):
        return re.sub(r'^---\n.*?\n---\n?', '', text, flags=re.DOTALL).strip()

    orig_body = strip_fm(original)
    edit_body = strip_fm(edited)

    # 문장 단위 비교
    orig_sentences = re.split(r'[.!?\n]+', orig_body)
    edit_sentences = re.split(r'[.!?\n]+', edit_body)

    return {
        'added_lines': added,
        'removed_lines': removed,
        'total_changes': len(added) + len(removed),
        'orig_length': len(orig_body),
        'edit_length': len(edit_body),
        'length_change': len(edit_body) - len(orig_body),
        'orig_sentences': len([s for s in orig_sentences if s.strip()]),
        'edit_sentences': len([s for s in edit_sentences if s.strip()]),
    }


def analyze_patterns(original: str, edited: str, diff_stats: dict) -> str:
    """Claude API로 수정 패턴을 분석합니다."""
    prompt = f"""두 버전의 글을 비교하여 수정 패턴을 분석해주세요.

## AI 원본
{original[:3000]}

## 사용자 수정본
{edited[:3000]}

## 변경 통계
- 추가된 줄: {len(diff_stats['added_lines'])}개
- 삭제된 줄: {len(diff_stats['removed_lines'])}개
- 길이 변화: {diff_stats['length_change']:+d}자

다음 항목을 분석해주세요 (한국어, 간결하게):

1. **삭제된 패턴**: AI가 썼지만 사용자가 삭제한 표현/구조 (앞으로 피해야 할 것)
2. **추가된 패턴**: 사용자가 새로 추가한 표현/구조 (앞으로 따라해야 할 것)
3. **수정된 패턴**: 같은 내용이지만 표현을 바꾼 것 (톤/어미 변화)
4. **구조 변화**: 글의 순서나 구조가 바뀐 부분
5. **핵심 교훈**: 다음 글 생성 시 반영해야 할 1~3가지 핵심 규칙

각 항목을 1~2문장으로 간결하게. 총 200자 이내."""

    message = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def store_learning(client, channel: str, topic: str, analysis: str, diff_stats: dict):
    """분석된 패턴을 Honcho에 저장합니다."""
    if not client:
        return

    user = client.peer("content-creator")
    session = client.session(f"{channel}-corrections")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = (
        f"[수정학습 {timestamp}] 주제: {topic}\n"
        f"변경량: {diff_stats['total_changes']}줄, "
        f"길이변화: {diff_stats['length_change']:+d}자\n"
        f"분석:\n{analysis}"
    )
    session.add_messages([user.message(msg)])
    print(f"  학습 패턴 Honcho 저장 완료 ({channel}-corrections)")


def get_correction_context(client, channel: str) -> str:
    """누적된 수정 패턴을 조회합니다. 글 생성 시 참고용."""
    if not client:
        return ""
    try:
        user = client.peer("content-creator")
        context = user.chat(
            f"{channel} 채널에서 사용자가 AI 초안을 수정한 패턴을 요약해줘. "
            f"AI가 반복적으로 범하는 실수, 사용자가 선호하는 표현, "
            f"삭제된 패턴, 추가된 패턴을 알려줘."
        )
        return context
    except Exception:
        return ""


def detect_category(content: str, filename: str) -> str:
    """파일 내용/제목에서 카테고리를 추정합니다."""
    text = (filename + " " + content).lower()
    categories = {
        '훈육': ['훈육', '엄하게', '안전', '경계', '비폭력', '형제', '갈등'],
        '수학': ['수학', '구구단', '나눗셈', '분수', '연산', 'cpa', '수감각'],
        '독서': ['독서', '책', '읽기', '그림책', '국어', '어휘'],
        '미디어': ['스마트폰', 'ai', '디지털', '미디어', '유튜브', '로봇'],
        '놀이': ['놀이', '놀', '장난감', '창의성', '체험'],
        '감정': ['자존감', '감정', '칭찬', '비교', '한숨', '스트레스'],
        '학습': ['공부', '학습', '메타인지', '학원', '영어', '습관'],
        '학교': ['학교', '입학', '개학', '통지표', '학년', '급식'],
        '크리에이터': ['유튜브', '스레드', '수익', '크리에이터', '콘텐츠'],
    }
    scores = {}
    for cat, keywords in categories.items():
        scores[cat] = sum(1 for kw in keywords if kw in text)
    if max(scores.values()) == 0:
        return '학습'  # 기본값
    return max(scores, key=scores.get)


def process_reviewed_files():
    """08 리뷰/ 에서 '리뷰완료' 상태의 파일을 처리합니다."""
    if not os.path.exists(REVIEW_DIR):
        print("08 리뷰/ 폴더가 없습니다.")
        return []

    processed = []
    honcho = get_honcho_client()

    for fname in os.listdir(REVIEW_DIR):
        if not fname.endswith('.md'):
            continue

        filepath = os.path.join(REVIEW_DIR, fname)
        with open(filepath, 'r', encoding='utf-8') as f:
            edited_content = f.read()

        fm = parse_frontmatter(edited_content)
        if fm.get('상태') != '리뷰완료':
            continue

        print(f"\n{'='*50}")
        print(f"처리 중: {fname}")

        # AI 원본 찾기
        draft_path = os.path.join(AI_DRAFTS_DIR, fname)
        if os.path.exists(draft_path):
            with open(draft_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            # Diff 분석
            diff_stats = compute_diff(original_content, edited_content)
            print(f"  변경: {diff_stats['total_changes']}줄, "
                  f"길이: {diff_stats['length_change']:+d}자")

            if diff_stats['total_changes'] > 0:
                # Claude로 패턴 분석
                print("  패턴 분석 중...")
                analysis = analyze_patterns(
                    original_content, edited_content, diff_stats
                )
                print(f"  분석 결과: {analysis[:100]}...")

                # 채널 감지
                raw_channel = fm.get('채널', fm.get('type', 'thread'))
                channel = CHANNEL_MAP.get(raw_channel, 'thread')

                topic = fm.get('주제', fname.replace('.md', ''))
                store_learning(honcho, channel, topic, analysis, diff_stats)
            else:
                print("  변경 없음 - 학습 건너뜀")
                raw_channel = fm.get('채널', fm.get('type', 'thread'))
                channel = CHANNEL_MAP.get(raw_channel, 'thread')
        else:
            print(f"  AI 원본 없음 (.ai_drafts/{fname}) - 학습 건너뜀")
            raw_channel = fm.get('채널', fm.get('type', 'thread'))
            channel = CHANNEL_MAP.get(raw_channel, 'thread')

        # 채널별 이동 대상 결정
        if channel == 'thread':
            # 스레드 → 07 스레드/[카테고리]/
            category = fm.get('카테고리', detect_category(edited_content, fname))
            dest_dir = os.path.join(THREAD_DIR, category)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, fname)
            os.rename(filepath, dest_path)
            print(f"  이동: 08 리뷰/ → 07 스레드/{category}/")
        else:
            # 릴스/유튜브/블로그/뉴스레터 → 05 제작/52 원고/
            os.makedirs(SCRIPT_DIR, exist_ok=True)
            dest_path = os.path.join(SCRIPT_DIR, fname)
            if os.path.exists(dest_path):
                # 이미 존재하면 덮어쓰기 (수정본이 최신)
                os.remove(dest_path)
            os.rename(filepath, dest_path)
            print(f"  이동: 08 리뷰/ → 05 제작/52 원고/ ({channel})")

        # AI 원본 정리
        if os.path.exists(draft_path):
            os.remove(draft_path)

        processed.append({
            'filename': fname,
            'channel': channel,
            'dest_path': dest_path,
        })

    return processed


def main():
    """리뷰 완료된 파일을 처리합니다."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Diff 학습기 실행")
    print(f"  리뷰 폴더: {REVIEW_DIR}")
    print(f"  AI 원본: {AI_DRAFTS_DIR}")
    print()

    results = process_reviewed_files()

    if results:
        print(f"\n{'='*50}")
        print(f"처리 완료: {len(results)}개 파일")
        for r in results:
            print(f"  - {r['filename']} → {r['dest_path']}")
    else:
        print("리뷰완료 상태의 파일이 없습니다.")

    return results


if __name__ == "__main__":
    main()
