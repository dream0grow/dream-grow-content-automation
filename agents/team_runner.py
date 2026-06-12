"""Dream_Grow 팀 에이전트 자동 실행기

3개 팀 + skill-updater를 launchd에서 자동 실행.
각 팀은 Claude API를 호출하여 순차적으로 teammate 역할을 수행.

Teams:
  1. 콘텐츠-생산 (매일 04:00) - 스레드 + 릴스 + 리드마그넷
  2. 지식-관리 (금 11:00) - 제텔카스텐 + 백링크 + wiki
  3. 책-프로젝트 (토 05:00) - 콘텐츠 → 책 원고

실행:
  python3 agents/team_runner.py content   # Team 1
  python3 agents/team_runner.py knowledge # Team 2
  python3 agents/team_runner.py book      # Team 3
  python3 agents/team_runner.py skill     # skill-updater (각 팀 후 자동)
"""
import os
import sys
import json
import re
import random
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import claude_client; claude_client.patch_anthropic()
import anthropic
from memory_manager import (
    get_honcho_client, get_full_context, get_style_context,
    get_brand_context, save_team_learning
)

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# 경로
SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
OBSIDIAN_ROOT = "/Users/lhg/Documents/obsidian/초생산"
WIKI_DIR = os.path.join(OBSIDIAN_ROOT, "wiki")
ZETTEL_DIR = os.path.join(OBSIDIAN_ROOT, "제텔카스텐/5. 제텔카스텐")
REVIEW_DIR = os.path.join(SNS_SYSTEM, "05 리뷰/대기")
LIBRARY_DIR = os.path.join(SNS_SYSTEM, "03 라이브러리/38 주제별 콘텐츠")
REELS_DIR = os.path.join(SNS_SYSTEM, "05 리뷰/대기")  # 릴스도 리뷰대기로
LEADMAGNET_DIR = os.path.join(SNS_SYSTEM, "09 리드마그넷")
AI_DRAFTS_DIR = os.path.join(str(PROJECT_ROOT), ".ai_drafts")
LOG_DIR = os.path.join(str(PROJECT_ROOT), "scheduled/logs")

CATEGORIES = ["훈육", "수학", "독서", "미디어", "놀이", "감정", "학습", "학교"]


def log(msg: str, team: str = ""):
    """로그 출력 + 파일 기록."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{team}] {msg}" if team else f"[{timestamp}] {msg}"
    print(line)
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"team-{team or 'general'}.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def call_claude(system: str, user_msg: str, max_tokens: int = 4000, model: str = "claude-sonnet-4-6") -> str:
    """Claude API 호출. 글쓰기는 opus, 유틸리티는 sonnet."""
    message = claude.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return message.content[0].text


def call_claude_opus(system: str, user_msg: str, max_tokens: int = 4000) -> str:
    """Opus 4.6으로 글쓰기 품질 최대화. 스레드/릴스/뉴스레터/제텔카스텐/책 원고용."""
    return call_claude(system, user_msg, max_tokens, model="claude-opus-4-6")


def read_file(path: str) -> str:
    """파일 읽기 (없으면 빈 문자열)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def save_to_review(content: str, filename: str, frontmatter: dict):
    """05 리뷰/대기/에 저장 + AI 원본 백업."""
    os.makedirs(REVIEW_DIR, exist_ok=True)
    os.makedirs(AI_DRAFTS_DIR, exist_ok=True)

    fm_lines = ["---"]
    for k, v in frontmatter.items():
        fm_lines.append(f"{k}: {v}")
    fm_lines.append("발행시간:")
    fm_lines.append("---")
    full = "\n".join(fm_lines) + "\n\n" + content

    filepath = os.path.join(REVIEW_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full)

    # AI 원본 백업
    backup = os.path.join(AI_DRAFTS_DIR, filename)
    with open(backup, "w", encoding="utf-8") as f:
        f.write(full)

    return filepath


def pick_topics(n: int = 3) -> list:
    """wiki + 제텔카스텐에서 콘텐츠 주제 후보를 뽑는다."""
    topics = []

    # 기존 리뷰대기 파일의 카테고리 분포 확인 → 부족한 카테고리 우선
    cat_count = {}
    if os.path.isdir(REVIEW_DIR):
        for f in os.listdir(REVIEW_DIR):
            if f.endswith(".md"):
                content = read_file(os.path.join(REVIEW_DIR, f))
                for cat in CATEGORIES:
                    if f"카테고리: {cat}" in content or f"_{cat}_" in f:
                        cat_count[cat] = cat_count.get(cat, 0) + 1
                        break

    # 부족한 카테고리 찾기
    min_count = min(cat_count.values()) if cat_count else 0
    weak_cats = [c for c in CATEGORIES if cat_count.get(c, 0) <= min_count + 2]
    if not weak_cats:
        weak_cats = CATEGORIES

    # wiki에서 주제 소재 수집
    wiki_topics = []
    if os.path.isdir(WIKI_DIR):
        for f in os.listdir(WIKI_DIR):
            if f.endswith(".md") and not f.startswith("."):
                name = f.replace(".md", "").replace("C_", "").replace("S_", "")
                wiki_topics.append(name)

    # 카테고리별 주제 아이디어를 Claude에게 요청
    cat_sample = random.sample(weak_cats, min(n, len(weak_cats)))
    wiki_sample = random.sample(wiki_topics, min(10, len(wiki_topics))) if wiki_topics else []

    prompt = f"""Dream_Grow는 초등 자녀 부모 대상 교육 콘텐츠 크리에이터입니다.
아래 카테고리에서 스레드 주제를 각 1개씩, 총 {n}개 제안해주세요.

카테고리: {', '.join(cat_sample)}

참고할 수 있는 wiki 주제들: {', '.join(wiki_sample)}

형식 (JSON 배열):
[{{"topic": "주제", "category": "카테고리"}}]

주제는 부모가 궁금해할 구체적이고 실용적인 것으로.
이모지 금지. JSON만 출력."""

    result = call_claude("주제 제안 전문가", prompt, max_tokens=500)
    try:
        match = re.search(r'\[.*\]', result, re.DOTALL)
        if match:
            topics = json.loads(match.group())
    except (json.JSONDecodeError, AttributeError):
        # fallback
        for cat in cat_sample:
            topics.append({"topic": f"초등 {cat} 핵심 가이드", "category": cat})

    return topics[:n]


# ============================================================
# Team 1: 콘텐츠-생산
# ============================================================
def run_content_team():
    """Team 1: 스레드 + 릴스 + 리드마그넷 세트 생산."""
    team = "content"
    log("=== Team 콘텐츠-생산 시작 ===", team)

    honcho = get_honcho_client()
    ctx = get_full_context(honcho, "thread") if honcho else {}

    # 1. 주제 선정
    log("Step 1: 주제 선정", team)
    topics = pick_topics(3)
    log(f"  선정된 주제: {json.dumps(topics, ensure_ascii=False)}", team)

    for i, t in enumerate(topics, 1):
        topic = t["topic"]
        category = t["category"]
        log(f"\n--- [{i}/{len(topics)}] {topic} ({category}) ---", team)

        # 2. thread-writer: 스레드 초안 작성
        log("  Teammate 1: thread-writer 실행", team)
        thread_system = read_file(str(PROJECT_ROOT / "thread_generator.py"))
        # 시스템 프롬프트에서 THREAD_SYSTEM_PROMPT 추출 대신 직접 임포트
        from thread_generator import THREAD_SYSTEM_PROMPT, generate_thread
        thread_content = generate_thread(topic, category=category)
        log(f"  스레드 생성 완료 ({len(thread_content)}자)", team)

        # 파일 저장
        safe_topic = topic.replace(" ", "+")[:40]
        filename = f"스레드_{category}_{safe_topic}.md"
        fm = {
            "주제": topic,
            "카테고리": category,
            "채널": "thread",
            "상태": "리뷰대기",
            "생성일": datetime.now().strftime("%Y-%m-%d"),
            "출처": "AI생성_Dream_Grow스타일",
        }
        saved = save_to_review(thread_content, filename, fm)
        log(f"  저장: {filename}", team)

        # 3. research-checker: 팩트체크
        log("  Teammate 2: research-checker 실행", team)
        check_prompt = f"""아래 스레드 초안의 팩트를 검증해주세요.

## 스레드
{thread_content[:3000]}

## 검증 항목
1. 인용된 학자/이론이 실제로 존재하는지
2. 통계 수치가 있다면 출처가 있는지
3. 교육학/심리학적으로 오류가 없는지
4. 과장된 표현이 없는지

## 출력
- 문제 있는 부분: (없으면 "없음")
- 수정 제안: (없으면 "없음")
- 추가할 wiki 개념: (없으면 "없음")"""

        check_result = call_claude(
            "교육학/심리학 팩트체크 전문가. 이모지 사용 금지.",
            check_prompt, max_tokens=1000
        )
        log(f"  팩트체크 완료", team)

        # 팩트체크에서 문제 발견 시 스레드 수정
        if "문제" in check_result and "없음" not in check_result.split("문제")[1][:50]:
            log("  팩트체크 이슈 발견 → 스레드 수정", team)
            fix_prompt = f"""아래 스레드에서 팩트체크 이슈를 수정해주세요.
기존 문체와 구조는 그대로 유지하고, 문제 부분만 수정.

## 원본 스레드
{thread_content[:3000]}

## 팩트체크 결과
{check_result}

수정된 스레드 전체를 출력해주세요. 이모지 금지."""
            thread_content = call_claude_opus(
                "스레드 수정 전문가. 문체 유지 필수. 이모지 금지.",
                fix_prompt, max_tokens=2500
            )
            # 수정본 덮어쓰기
            save_to_review(thread_content, filename, fm)
            log("  수정 완료", team)

        # 4. reels-magnet-producer: 릴스 + 리드마그넷
        log("  Teammate 3: reels-magnet-producer 실행", team)
        from auto_reels_from_thread import REELS_SYSTEM_PROMPT
        reels_style = get_style_context(honcho, "reels") if honcho else ""

        reels_system = REELS_SYSTEM_PROMPT
        if reels_style:
            reels_system += f"\n\n## Honcho 릴스 스타일\n{reels_style}\n"

        reels_prompt = f"""아래 스레드를 45초 릴스 스크립트로 변환해주세요.
카테고리: {category}

## 원본 스레드
{thread_content[:3000]}

## 출력
1. 릴스 스크립트 (타임코드 + 대사 + 화면 지시)
2. 마지막에 리드마그넷 CTA 필수
3. 리드마그넷 제안 (이름, 유형, 내용 3줄)
4. B-roll 장면 목록"""

        reels_content = call_claude_opus(reels_system, reels_prompt, max_tokens=1500)

        reels_filename = f"원고_릴스_{category}_{safe_topic}.md"
        reels_fm = {
            "주제": topic,
            "카테고리": category,
            "채널": "reels",
            "상태": "리뷰대기",
            "생성일": datetime.now().strftime("%Y-%m-%d"),
            "출처": "AI생성_Dream_Grow스타일",
            "영상상태": "원고작성",
        }
        save_to_review(reels_content, reels_filename, reels_fm)
        log(f"  릴스 저장: {reels_filename}", team)

        # 리드마그넷
        from lead_magnet_generator import generate_lead_magnet, save_lead_magnet, choose_magnet_type
        magnet_type = choose_magnet_type(category, topic)
        magnet_content = generate_lead_magnet(topic, category, magnet_type, reels_content)
        save_lead_magnet(magnet_content, topic, category, magnet_type)
        log(f"  리드마그넷 저장 ({magnet_type})", team)

        # Honcho 팀 학습
        if honcho:
            save_team_learning(honcho, "thread", "pattern",
                               f"주제 '{topic}' ({category}) 생성 완료. 팩트체크: {check_result[:100]}")

    # 5. 자동 검수 (content-review)
    log("  Step 4: content-review 자동 검수", team)
    try:
        from content_reviewer import review_all
        results = review_all(auto_fix=True)
        passed = sum(1 for r in results if r.passed)
        log(f"  검수 완료: {passed}/{len(results)} 통과", team)
    except Exception as e:
        log(f"  검수 실패: {e}", team)

    log(f"=== Team 콘텐츠-생산 완료: {len(topics)}개 세트 ===", team)
    return len(topics)


# ============================================================
# Team 2: 지식-관리
# ============================================================
def run_knowledge_team():
    """Team 2: 제텔카스텐 + 백링크 + wiki."""
    team = "knowledge"
    log("=== Team 지식-관리 시작 ===", team)

    honcho = get_honcho_client()

    # 1. zettelkasten-builder: 최근 콘텐츠에서 제텔카스텐 노트 추출
    log("Step 1: zettelkasten-builder", team)

    # 최근 리뷰대기 파일 읽기
    recent_contents = []
    if os.path.isdir(REVIEW_DIR):
        files = sorted(os.listdir(REVIEW_DIR), key=lambda f: os.path.getmtime(
            os.path.join(REVIEW_DIR, f)), reverse=True)
        for f in files[:10]:
            if f.endswith(".md"):
                content = read_file(os.path.join(REVIEW_DIR, f))
                recent_contents.append({"file": f, "content": content[:1500]})

    if not recent_contents:
        log("  최근 콘텐츠 없음 → 건너뜀", team)
        return

    # 기존 wiki 목록
    existing_wiki = []
    if os.path.isdir(WIKI_DIR):
        existing_wiki = [f.replace(".md", "") for f in os.listdir(WIKI_DIR) if f.endswith(".md")]

    zettel_prompt = f"""아래 최근 콘텐츠를 분석하여 제텔카스텐 노트를 추출해주세요.

## 최근 콘텐츠 (최대 10개)
{json.dumps([{"file": c["file"], "preview": c["content"][:500]} for c in recent_contents], ensure_ascii=False, indent=2)}

## 기존 wiki 페이지 (중복 방지)
{', '.join(existing_wiki[:50])}

## 출력 (JSON)
각 노트에 대해:
[{{
  "type": "K|O|P",
  "title": "노트 제목",
  "content": "노트 내용 (200~400자)",
  "links": ["연결할 기존 wiki 페이지명"],
  "source": "원본 파일명"
}}]

K=사실/인용, O=나의 해석, P=실천 원칙
이모지 금지. JSON만 출력."""

    zettel_result = call_claude_opus(
        "제텔카스텐 전문가. 교육학/심리학 지식 구조화.",
        zettel_prompt, max_tokens=3000
    )

    # 제텔카스텐 노트 저장
    try:
        match = re.search(r'\[.*\]', zettel_result, re.DOTALL)
        if match:
            notes = json.loads(match.group())
            os.makedirs(ZETTEL_DIR, exist_ok=True)
            for note in notes[:5]:
                note_type = note.get("type", "K")
                title = note.get("title", "untitled")
                content = note.get("content", "")
                links = note.get("links", [])

                link_text = "\n".join(f"- [[{l}]]" for l in links)
                note_content = f"""---
type: {note_type}
생성일: {datetime.now().strftime("%Y-%m-%d")}
출처: {note.get("source", "auto")}
---

# {title}

{content}

## 연결
{link_text}
"""
                safe_title = title.replace(" ", "_").replace("/", "_")[:40]
                note_path = os.path.join(ZETTEL_DIR, f"{note_type}-{safe_title}.md")
                with open(note_path, "w", encoding="utf-8") as f:
                    f.write(note_content)
                log(f"  제텔카스텐 저장: {note_type}-{safe_title}", team)
    except (json.JSONDecodeError, AttributeError) as e:
        log(f"  제텔카스텐 파싱 실패: {e}", team)

    # 2. wiki-creator: 누락된 wiki 페이지 생성
    log("Step 2: wiki-creator", team)
    wiki_prompt = f"""아래 콘텐츠에서 wiki 페이지로 만들어야 할 개념/인물/이론을 찾아주세요.

## 최근 콘텐츠 핵심 키워드
{json.dumps([c["file"] for c in recent_contents], ensure_ascii=False)}

## 이미 있는 wiki (중복 금지)
{', '.join(existing_wiki[:50])}

## 출력 (JSON)
[{{
  "filename": "C_개념명.md 또는 S_인물명.md",
  "title": "제목",
  "category": "S(인물)|C(개념)|E(출처)|A(주장)",
  "content": "wiki 내용 (300~500자)"
}}]

최대 3개. 이모지 금지. JSON만."""

    wiki_result = call_claude_opus(
        "교육학 wiki 전문가. 정확한 사실만 기록.",
        wiki_prompt, max_tokens=2000
    )

    try:
        match = re.search(r'\[.*\]', wiki_result, re.DOTALL)
        if match:
            pages = json.loads(match.group())
            os.makedirs(WIKI_DIR, exist_ok=True)
            for page in pages[:3]:
                fname = page.get("filename", "C_untitled.md")
                content = page.get("content", "")
                title = page.get("title", fname.replace(".md", ""))
                category = page.get("category", "C")

                wiki_content = f"""---
type: {category}
생성일: {datetime.now().strftime("%Y-%m-%d")}
---

# {title}

{content}
"""
                wiki_path = os.path.join(WIKI_DIR, fname)
                if not os.path.exists(wiki_path):
                    with open(wiki_path, "w", encoding="utf-8") as f:
                        f.write(wiki_content)
                    log(f"  wiki 생성: {fname}", team)
                else:
                    log(f"  wiki 이미 존재: {fname}", team)
    except (json.JSONDecodeError, AttributeError) as e:
        log(f"  wiki 파싱 실패: {e}", team)

    # 3. backlink-weaver: 백링크 연결 (간소화)
    log("Step 3: backlink-weaver (백링크 점검)", team)
    # wiki 페이지 목록으로 리뷰대기 파일에 [[링크]] 추가 제안
    if honcho:
        save_team_learning(honcho, "thread", "pattern",
                           f"지식관리 실행: 제텔카스텐+wiki 업데이트 완료 ({datetime.now().strftime('%Y-%m-%d')})")

    log("=== Team 지식-관리 완료 ===", team)


# ============================================================
# Team 3: 책-프로젝트
# ============================================================
def run_book_team():
    """Team 3: 기존 콘텐츠 → 책 원고 변환."""
    team = "book"
    log("=== Team 책-프로젝트 시작 ===", team)

    honcho = get_honcho_client()
    book_style = get_style_context(honcho, "book") if honcho else ""

    # 1. 기존 콘텐츠 스캔 (라이브러리 + 리뷰완료)
    log("Step 1: 콘텐츠 인벤토리 스캔", team)
    inventory = {}
    if os.path.isdir(LIBRARY_DIR):
        for cat in os.listdir(LIBRARY_DIR):
            cat_dir = os.path.join(LIBRARY_DIR, cat)
            if os.path.isdir(cat_dir):
                files = [f for f in os.listdir(cat_dir) if f.endswith(".md")]
                if files:
                    inventory[cat] = files

    if os.path.isdir(REVIEW_DIR):
        for f in os.listdir(REVIEW_DIR):
            if f.endswith(".md"):
                content = read_file(os.path.join(REVIEW_DIR, f))
                if "상태: 리뷰완료" in content or "상태: 발행완료" in content:
                    for cat in CATEGORIES:
                        if cat in f or f"카테고리: {cat}" in content:
                            inventory.setdefault(cat, []).append(f)
                            break

    if not inventory:
        log("  콘텐츠 인벤토리 비어있음 → 건너뜀", team)
        return

    log(f"  인벤토리: {', '.join(f'{k}({len(v)})' for k, v in inventory.items())}", team)

    # 2. 책 구조 설계/갱신
    log("Step 2: 책 구조 설계", team)
    book_dir = os.path.join(OBSIDIAN_ROOT, "책 프로젝트")
    os.makedirs(book_dir, exist_ok=True)

    structure_file = os.path.join(book_dir, "00 책 구조.md")
    existing_structure = read_file(structure_file)

    structure_prompt = f"""Dream_Grow(초등교사, 교육 크리에이터)가 기존 SNS 콘텐츠를 바탕으로
초등 자녀 부모를 위한 교육서를 쓰려고 합니다.

## 보유 콘텐츠 현황
{json.dumps({k: len(v) for k, v in inventory.items()}, ensure_ascii=False)}

## 기존 책 구조 (있다면)
{existing_structure[:2000] if existing_structure else "(아직 없음)"}

## 책 스타일 참고
{book_style[:1000] if book_style else "(없음)"}

## 요청
1. 책 제목 3개 후보
2. 10~12챕터 목차 (각 챕터: 제목 + 핵심 메시지 + 활용할 콘텐츠 카테고리)
3. 이번 주 작업할 챕터 1개 선택 + 이유
4. 선택한 챕터의 상세 구조 (소제목 3~5개)

이모지 금지."""

    structure_result = call_claude_opus(
        "교육서 기획 전문가. 이한결(Dream_Grow) 스타일. 이모지 금지.",
        structure_prompt, max_tokens=3000
    )

    with open(structure_file, "w", encoding="utf-8") as f:
        f.write(f"""---
생성일: {datetime.now().strftime("%Y-%m-%d")}
상태: 진행중
---

# Dream_Grow 책 프로젝트

{structure_result}
""")
    log(f"  책 구조 저장: {structure_file}", team)

    # 3. 챕터 초안 작성
    log("Step 3: 챕터 초안 작성", team)

    # 가장 콘텐츠가 많은 카테고리로 챕터 작성
    best_cat = max(inventory.items(), key=lambda x: len(x[1]))[0]
    source_files = inventory[best_cat][:5]

    # 소스 콘텐츠 읽기
    source_contents = []
    for fname in source_files:
        # 라이브러리에서 먼저 찾기
        for root_dir in [os.path.join(LIBRARY_DIR, best_cat), REVIEW_DIR]:
            fpath = os.path.join(root_dir, fname)
            if os.path.exists(fpath):
                source_contents.append(read_file(fpath)[:1500])
                break

    chapter_prompt = f"""아래 스레드/콘텐츠를 바탕으로 책의 한 챕터를 작성해주세요.

## 카테고리: {best_cat}
## 소스 콘텐츠 ({len(source_contents)}개)

{"---".join(source_contents[:3])}

## 챕터 작성 규칙
- 2000~3000자
- 도입: 교실 에피소드로 시작
- 본론: 이론적 근거 + 실제 사례 + 실천 방법
- 마무리: 부모에게 전하는 메시지
- 스레드의 짧은 문장 스타일이 아닌, 책에 맞는 서술체
- 이모지/이모티콘 절대 금지
- 가짜 통계 금지
- 'A가 아니라 B이다' 논증 구조 활용

## 책 스타일 참고
{book_style[:500] if book_style else "전문적이면서 따뜻한 톤. 교사의 경험에서 우러나오는 진정성."}

챕터 제목부터 시작해주세요."""

    chapter_content = call_claude_opus(
        "교육서 작가. 현직 초등교사 관점. 이모지 금지.",
        chapter_prompt, max_tokens=4000
    )

    chapter_filename = f"챕터_{best_cat}_{datetime.now().strftime('%Y%m%d')}.md"
    chapter_path = os.path.join(book_dir, chapter_filename)
    with open(chapter_path, "w", encoding="utf-8") as f:
        f.write(f"""---
카테고리: {best_cat}
생성일: {datetime.now().strftime("%Y-%m-%d")}
상태: 초안
소스: {', '.join(source_files[:3])}
---

{chapter_content}
""")
    log(f"  챕터 저장: {chapter_filename}", team)

    if honcho:
        save_team_learning(honcho, "book", "pattern",
                           f"챕터 '{best_cat}' 초안 완료. 소스 {len(source_files)}개 활용.")

    log("=== Team 책-프로젝트 완료 ===", team)


# ============================================================
# Skill Updater
# ============================================================
def run_skill_updater():
    """팀 작업 후 Honcho 메모리 업데이트 + diff 학습 + 스킬 갱신."""
    team = "skill"
    log("=== Skill Updater 시작 ===", team)

    honcho = get_honcho_client()

    # 1. diff 학습 실행
    log("Step 1: diff 학습", team)
    try:
        from diff_learner import process_reviewed_files
        results = process_reviewed_files()
        if results:
            log(f"  diff 학습 완료: {len(results)}개 파일 처리", team)
        else:
            log("  diff 학습: 처리할 파일 없음", team)
    except Exception as e:
        log(f"  diff 학습 실패: {e}", team)

    # 2. 팀 학습 데이터 정리
    log("Step 2: 팀 학습 데이터 정리", team)
    if honcho:
        for channel in ["thread", "reels", "book"]:
            learnings = ""
            try:
                from memory_manager import get_team_learnings
                learnings = get_team_learnings(honcho, channel)
            except Exception:
                pass

            if learnings and len(learnings) > 100:
                # 중복 제거 + 정리
                cleanup_prompt = f"""아래 팀 학습 데이터에서:
1. 중복 항목 제거
2. 모순되는 항목 표시
3. 핵심 패턴 5개 이내로 요약

## 팀 학습 데이터 ({channel})
{learnings[:2000]}

요약 결과만 출력. 이모지 금지."""

                summary = call_claude("데이터 정리 전문가", cleanup_prompt, max_tokens=500)
                save_team_learning(honcho, channel, "summary", summary)
                log(f"  {channel} 팀학습 정리 완료", team)

    # 3. 스킬 파일 갱신 점검
    log("Step 3: 스킬 파일 점검", team)
    skills_dir = os.path.join(str(PROJECT_ROOT).replace("content-automation", ""),
                               ".claude/skills")
    if os.path.isdir(skills_dir):
        skill_files = [f for f in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, f))]
        log(f"  등록된 스킬: {', '.join(skill_files)}", team)

    # 4. 주간 캘린더 갱신
    log("Step 4: 주간 캘린더 갱신", team)
    try:
        from calendar_scheduler import scan_pipeline, scan_video_tracking
        from calendar_scheduler import generate_weekly_calendar, get_week_dates, CALENDAR_DIR
        pipeline = scan_pipeline()
        videos = scan_video_tracking()
        content = generate_weekly_calendar(pipeline, videos)
        monday, _, _ = get_week_dates()
        filename = f"{monday.strftime('%Y-%m-%d')} 주간 발행 계획.md"
        filepath = os.path.join(CALENDAR_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        log(f"  캘린더 갱신: {filename}", team)
    except Exception as e:
        log(f"  캘린더 갱신 실패: {e}", team)

    log("=== Skill Updater 완료 ===", team)


# ============================================================
# Main
# ============================================================
def main():
    commands = {
        "content": run_content_team,
        "knowledge": run_knowledge_team,
        "book": run_book_team,
        "skill": run_skill_updater,
    }

    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print("Dream_Grow 팀 에이전트 실행기")
        print()
        print("사용법:")
        print("  python3 agents/team_runner.py content    # Team 1: 콘텐츠-생산 (매일 04:00)")
        print("  python3 agents/team_runner.py knowledge  # Team 2: 지식-관리 (금 11:00)")
        print("  python3 agents/team_runner.py book       # Team 3: 책-프로젝트 (토 05:00)")
        print("  python3 agents/team_runner.py skill      # Skill Updater (각 팀 후)")
        return

    cmd = sys.argv[1]
    log(f"팀 실행 시작: {cmd}")

    # 팀 실행
    commands[cmd]()

    # 팀 실행 후 skill-updater 자동 실행
    if cmd != "skill":
        log("skill-updater 자동 실행")
        run_skill_updater()

    log(f"팀 실행 완료: {cmd}")


if __name__ == "__main__":
    main()
