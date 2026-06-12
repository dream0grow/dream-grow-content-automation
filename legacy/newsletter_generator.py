"""Dream_Grow 뉴스레터 자동 생성기

최근 발행 콘텐츠를 기반으로 뉴스레터 초안을 생성합니다.

구조: 인트로(이전 뉴스레터 연결) → 본론(교실 에피소드 + 단계별 방법)
     → [가정에서 연습하는 법] 대화 예시 → 유의할 점 → 정리 → 다음 뉴스레터 예고

사용법:
  python3 newsletter_generator.py --topic "주제" --category "카테고리"
  python3 newsletter_generator.py --from-threads      # 최근 스레드 기반 자동 생성
  python3 newsletter_generator.py --list               # 뉴스레터 현황
"""
import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv
import claude_client; claude_client.patch_anthropic()

load_dotenv()

SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
REVIEW_DIR = os.path.join(SNS_SYSTEM, "05 리뷰", "대기")
LIBRARY_DIR = os.path.join(SNS_SYSTEM, "03 라이브러리", "38 주제별 콘텐츠")
PUBLISHED_DIR = os.path.join(SNS_SYSTEM, "06 제작", "64 발행완료")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def parse_frontmatter(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = {}
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if match:
        for line in match.group(1).split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                fm[key.strip()] = val.strip().strip("\"'")
    fm["_content"] = content
    fm["_filepath"] = filepath
    fm["_filename"] = os.path.basename(filepath)
    return fm


def find_recent_threads(category: str = "", limit: int = 5) -> list:
    """최근 발행된 스레드를 찾습니다."""
    threads = []
    for folder in [PUBLISHED_DIR, LIBRARY_DIR]:
        if not os.path.isdir(folder):
            continue
        for root, dirs, files in os.walk(folder):
            for fname in files:
                if not fname.endswith(".md") or "스레드" not in fname:
                    continue
                filepath = os.path.join(root, fname)
                fm = parse_frontmatter(filepath)
                if category and fm.get("카테고리", "") != category:
                    continue
                threads.append(fm)

    threads.sort(key=lambda x: x.get("생성일", ""), reverse=True)
    return threads[:limit]


def find_existing_newsletters() -> list:
    """기존 뉴스레터를 찾습니다."""
    newsletters = []
    for folder in [REVIEW_DIR, PUBLISHED_DIR]:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if "뉴스레터" in fname and fname.endswith(".md"):
                filepath = os.path.join(folder, fname)
                fm = parse_frontmatter(filepath)
                newsletters.append(fm)
    return newsletters


def generate_newsletter(topic: str, category: str, reference_threads: list = None) -> str:
    """Claude API로 뉴스레터를 생성합니다."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    thread_context = ""
    if reference_threads:
        for t in reference_threads[:3]:
            body = t["_content"]
            match = re.match(r"^---\n.*?\n---\n?", body, re.DOTALL)
            if match:
                body = body[match.end():]
            thread_context += f"\n### {t.get('주제', t['_filename'])}\n{body[:1000]}\n"

    existing = find_existing_newsletters()
    prev_topics = [n.get("주제", "") for n in existing[:3]]
    prev_context = f"이전 뉴스레터 주제: {', '.join(prev_topics)}" if prev_topics else ""

    from memory_manager import get_honcho_client
    honcho = get_honcho_client()
    honcho_context = ""
    if honcho:
        from diff_learner import get_correction_context
        honcho_context = get_correction_context(honcho, "newsletter")

    prompt = f"""Dream_Grow 뉴스레터를 작성해주세요.

주제: {topic}
카테고리: {category}
{prev_context}

## 필수 규칙
- 이모지/이모티콘 절대 금지
- 출처 없는 % 수치 금지
- 'A가 아니라 B이다' 논증 구조
- 교실 경험 기반 에피소드 최소 1개
- 6000~7000자
- %name% 개인화 변수 사용 (인트로에서)

## 구조
1. 인트로 (이전 뉴스레터 연결, %name%님 호칭)
2. 본론 (교실 에피소드 + 단계별 방법 3~5단계)
3. [가정에서 연습하는 법] 부모-자녀 대화 예시 3개
4. 유의할 점 2~3개
5. 정리 (핵심 요약)
6. 다음 뉴스레터 예고
7. 마무리: 주제에 맞는 자연스러운 어미 + "아이와 부모의 꿈을 키웁니다. -Dream_Grow-"

## 톤
- 그로우써클 커뮤니티 명칭 사용
- 따뜻하지만 전문적, 교사의 관점
- 실천 가능한 구체적 방법 제시

{f"## 참고 스레드 콘텐츠{thread_context}" if thread_context else ""}
{f"## Honcho 학습 패턴{honcho_context}" if honcho_context else ""}

뉴스레터 본문만 작성해주세요 (frontmatter 제외)."""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def save_newsletter(content: str, topic: str, category: str):
    """뉴스레터를 05 리뷰/대기/에 저장합니다."""
    safe_topic = re.sub(r"[/\\:*?\"<>|]", "", topic)
    keywords = "+".join(safe_topic.split()[:3])
    filename = f"원고_뉴스레터_{category}_{keywords}.md"

    fm = f"""---
주제: {topic}
카테고리: {category}
채널: newsletter
상태: 리뷰대기
생성일: {datetime.now().strftime('%Y-%m-%d')}
출처: AI생성_Dream_Grow스타일
발행시간:
검수상태:
---

"""

    os.makedirs(REVIEW_DIR, exist_ok=True)
    filepath = os.path.join(REVIEW_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(fm + content)

    from diff_learner import save_ai_draft
    save_ai_draft(filepath)

    print(f"저장: {filepath}")
    print(f"AI 원본 백업: .ai_drafts/{filename}")
    return filepath


def list_newsletters():
    """뉴스레터 현황을 보여줍니다."""
    newsletters = find_existing_newsletters()
    print(f"\n--- 뉴스레터 현황 ({len(newsletters)}개) ---\n")
    if not newsletters:
        print("뉴스레터가 없습니다.")
        return
    for n in newsletters:
        status = n.get("상태", "?")
        topic = n.get("주제", n["_filename"])
        print(f"  [{status}] {topic[:40]}")


def main():
    if "--list" in sys.argv:
        list_newsletters()
        return

    if "--from-threads" in sys.argv:
        threads = find_recent_threads(limit=5)
        if not threads:
            print("최근 스레드가 없습니다.")
            return

        categories = {}
        for t in threads:
            cat = t.get("카테고리", "학습")
            categories.setdefault(cat, []).append(t)

        best_cat = max(categories, key=lambda c: len(categories[c]))
        cat_threads = categories[best_cat]
        topic = cat_threads[0].get("주제", "")

        print(f"카테고리: {best_cat} (스레드 {len(cat_threads)}개)")
        print(f"주제: {topic}")
        print(f"뉴스레터 생성 중...\n")

        content = generate_newsletter(topic, best_cat, cat_threads)
        save_newsletter(content, topic, best_cat)
        return

    topic = ""
    category = "학습"

    if "--topic" in sys.argv:
        idx = sys.argv.index("--topic")
        if idx + 1 < len(sys.argv):
            topic = sys.argv[idx + 1]

    if "--category" in sys.argv:
        idx = sys.argv.index("--category")
        if idx + 1 < len(sys.argv):
            category = sys.argv[idx + 1]

    if not topic:
        print("사용법:")
        print('  python3 newsletter_generator.py --topic "주제" --category "카테고리"')
        print("  python3 newsletter_generator.py --from-threads")
        print("  python3 newsletter_generator.py --list")
        return

    print(f"뉴스레터 생성: {topic} ({category})")
    threads = find_recent_threads(category=category, limit=3)
    content = generate_newsletter(topic, category, threads)
    save_newsletter(content, topic, category)


if __name__ == "__main__":
    main()
