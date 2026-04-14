"""Threads Insights 수집기 - 발행 성과 추적 및 리포트

발행완료 콘텐츠의 성과 지표를 Threads API로 수집하고,
frontmatter를 업데이트하며, 주간 성과 리포트를 생성합니다.
댓글 수집, 핵심 키워드 추출, 댓글 반응 분석, 추가 주제 추천 포함.

사용법:
  python3 threads_insights.py                # 전체 실행 (수집 + 업데이트 + 리포트)
  python3 threads_insights.py --update       # 성과 지표 업데이트만
  python3 threads_insights.py --report       # 리포트 생성만
  python3 threads_insights.py --dry-run      # API 호출 없이 대상 파일 확인

필수 설정 (.env):
  THREADS_ACCESS_TOKEN=your_token
  THREADS_USER_ID=your_user_id

필요 권한: threads_basic, threads_manage_insights, threads_manage_replies
"""
import os
import re
import sys
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

# --- 경로 설정 ---
SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
PUBLISHED_DIR = os.path.join(SNS_SYSTEM, "06 제작", "64 발행완료")
REPORT_DIR = os.path.join(SNS_SYSTEM, "07 운영", "61 성과 기록")

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN")
THREADS_USER_ID = os.getenv("THREADS_USER_ID")
THREADS_API_BASE = "https://graph.threads.net/v1.0"

# 카테고리 목록 (파일명에서 추출 시 사용)
CATEGORIES = ["훈육", "수학", "독서", "미디어", "놀이", "감정", "학습", "학교", "크리에이터"]

# API 요청 간 대기 시간 (초) - 레이트 리밋 방지
API_DELAY = 1.0


# ============================================================
# 유틸리티
# ============================================================

def check_api_config() -> bool:
    """API 설정이 되어 있는지 확인합니다."""
    if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
        print("[오류] Threads API 설정이 필요합니다.")
        print("  .env 파일에 THREADS_ACCESS_TOKEN, THREADS_USER_ID를 설정하세요.")
        return False
    return True


def parse_frontmatter(filepath: str) -> dict:
    """파일의 frontmatter를 파싱합니다."""
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


def extract_category(filename: str) -> str:
    """파일명에서 카테고리를 추출합니다.

    파일명 형식: 스레드_카테고리_키워드.md
    frontmatter의 카테고리 필드가 우선, 없으면 파일명에서 추출.
    """
    for cat in CATEGORIES:
        if cat in filename:
            return cat
    return "기타"


def extract_posting_hour(fm: dict) -> int | None:
    """frontmatter에서 발행 시간(시)을 추출합니다."""
    time_str = fm.get("발행시간", "") or fm.get("발행일", "")
    if not time_str:
        return None
    # 시간 포함된 형식 시도
    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]:
        try:
            dt = datetime.strptime(time_str.strip(), fmt)
            return dt.hour
        except ValueError:
            continue
    return None


def parse_number(value: str) -> int:
    """숫자 문자열을 int로 변환합니다. 콤마 제거."""
    if not value:
        return 0
    return int(str(value).replace(",", "").strip())


# ============================================================
# Threads API 호출
# ============================================================

def api_get(url: str, params: dict) -> dict | None:
    """Threads API GET 요청을 수행합니다. 에러 처리 포함."""
    try:
        import requests
    except ImportError:
        print("[오류] requests 패키지가 필요합니다: pip3 install requests")
        sys.exit(1)

    params["access_token"] = THREADS_ACCESS_TOKEN

    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.exceptions.ConnectionError:
        print(f"  [네트워크 오류] 연결할 수 없습니다: {url}")
        return None
    except requests.exceptions.Timeout:
        print(f"  [타임아웃] 응답 없음: {url}")
        return None

    if resp.status_code == 401:
        print("[인증 오류] 토큰이 만료되었거나 유효하지 않습니다.")
        print("  새 토큰을 발급받아 .env를 업데이트하세요.")
        return None

    if resp.status_code == 429:
        print("[레이트 리밋] API 호출 한도에 도달했습니다. 잠시 후 다시 시도하세요.")
        return None

    if resp.status_code != 200:
        print(f"  [API 오류] {resp.status_code}: {resp.text[:200]}")
        return None

    return resp.json()


def fetch_post_insights(media_id: str) -> dict | None:
    """개별 게시물의 성과 지표를 가져옵니다.

    API: GET /{media-id}/insights?metric=views,likes,replies,reposts,quotes
    반환: {"views": N, "likes": N, "replies": N, "reposts": N, "quotes": N}
    """
    url = f"{THREADS_API_BASE}/{media_id}/insights"
    params = {"metric": "views,likes,replies,reposts,quotes"}

    data = api_get(url, params)
    if not data:
        return None

    metrics = {}
    for item in data.get("data", []):
        name = item.get("name", "")
        # values 배열의 첫 번째 value, 또는 total_value
        values = item.get("values", [])
        if values:
            metrics[name] = values[0].get("value", 0)
        elif "total_value" in item:
            metrics[name] = item["total_value"].get("value", 0)
        else:
            metrics[name] = 0

    return metrics


def fetch_account_insights(days: int = 7) -> dict | None:
    """계정 수준의 인사이트를 가져옵니다.

    API: GET /me/threads_insights?metric=views,likes,replies,reposts,quotes,followers_count
    """
    url = f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads_insights"

    since = int((datetime.now() - timedelta(days=days)).timestamp())
    until = int(datetime.now().timestamp())

    params = {
        "metric": "views,likes,replies,reposts,quotes,followers_count",
        "since": since,
        "until": until,
    }

    data = api_get(url, params)
    if not data:
        return None

    metrics = {}
    for item in data.get("data", []):
        name = item.get("name", "")
        values = item.get("values", [])
        if values:
            # 기간 내 합계
            total = sum(v.get("value", 0) for v in values)
            metrics[name] = total
        elif "total_value" in item:
            metrics[name] = item["total_value"].get("value", 0)

    return metrics


def fetch_post_replies(media_id: str) -> list:
    """개별 게시물의 댓글(답글)을 가져옵니다.

    API: GET /{media-id}/replies?fields=id,text,username,timestamp
    반환: [{"id": ..., "text": ..., "username": ..., "timestamp": ...}, ...]
    일부 게시물은 댓글이 없거나 API 오류가 발생할 수 있으므로 빈 리스트 반환.
    """
    url = f"{THREADS_API_BASE}/{media_id}/replies"
    params = {"fields": "id,text,username,timestamp"}

    data = api_get(url, params)
    if not data:
        return []

    replies = data.get("data", [])

    # 페이징: 다음 페이지가 있으면 추가 수집 (최대 100개)
    collected = list(replies)
    paging = data.get("paging", {})
    next_url = paging.get("next")
    page_count = 0

    while next_url and page_count < 5:  # 최대 5페이지
        try:
            import requests
            resp = requests.get(next_url, timeout=30)
            if resp.status_code != 200:
                break
            page_data = resp.json()
            page_replies = page_data.get("data", [])
            if not page_replies:
                break
            collected.extend(page_replies)
            next_url = page_data.get("paging", {}).get("next")
            page_count += 1
            time.sleep(API_DELAY)
        except Exception:
            break

    return collected


def collect_all_replies(published_files: list) -> dict:
    """발행완료 파일 전체의 댓글을 수집합니다.

    반환: {filename: {"replies": [...], "subject": ..., "category": ...}, ...}
    """
    all_replies = {}

    for fm in published_files:
        thread_id = fm.get("thread_id", "")
        if not thread_id:
            continue

        filename = fm["_filename"]
        print(f"  댓글 수집: {filename} ... ", end="", flush=True)

        replies = fetch_post_replies(thread_id)
        reply_texts = [r.get("text", "") for r in replies if r.get("text")]

        all_replies[filename] = {
            "replies": replies,
            "reply_texts": reply_texts,
            "subject": fm.get("주제", filename),
            "category": fm.get("_category", "기타"),
            "content": fm.get("_content", ""),
        }

        print(f"{len(replies)}건")
        time.sleep(API_DELAY)

    return all_replies


# ============================================================
# AI 분석 (Claude Sonnet)
# ============================================================

def _get_claude_client():
    """claude_client를 통한 Anthropic 호환 클라이언트를 반환합니다."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import claude_client
    claude_client.patch_anthropic()
    import anthropic
    return anthropic.Anthropic()


def extract_hooks_and_keywords(published_files: list) -> list:
    """각 게시물에서 후킹 포인트와 핵심 키워드를 추출합니다.

    반환: [{"filename": ..., "hook": ..., "keywords": [...]}, ...]
    """
    posts_info = []
    for fm in published_files:
        content = fm.get("_content", "")
        # frontmatter 이후의 본문만 추출
        body = re.sub(r"^---\n.*?\n---\n?", "", content, flags=re.DOTALL).strip()
        if not body:
            continue
        # 첫 문단 (후킹 포인트) 추출
        first_para = body.split("\n\n")[0].strip() if body else ""
        # 해시태그 제거
        first_para = re.sub(r"#\S+", "", first_para).strip()

        posts_info.append({
            "filename": fm["_filename"],
            "subject": fm.get("주제", fm["_filename"]),
            "category": fm.get("_category", "기타"),
            "first_para": first_para[:300],
            "body_preview": body[:800],
        })

    if not posts_info:
        return []

    # Claude Sonnet으로 일괄 분석
    client = _get_claude_client()

    post_summaries = []
    for i, p in enumerate(posts_info):
        post_summaries.append(
            f"[게시물 {i+1}] 제목: {p['subject']}\n"
            f"카테고리: {p['category']}\n"
            f"첫 문단: {p['first_para']}\n"
            f"본문 미리보기: {p['body_preview']}"
        )

    prompt = (
        "아래는 교육 크리에이터 Dream_Grow의 Threads 게시물 목록이다.\n"
        "각 게시물에 대해 다음을 추출하라:\n"
        "1. 후킹 포인트 (첫 문장에서 독자를 끌어들이는 핵심 한 줄, 원문 그대로)\n"
        "2. 핵심 키워드 3~5개\n\n"
        "출력 형식 (각 게시물마다):\n"
        "[게시물 N]\n"
        "후킹: (원문 후킹 한 줄)\n"
        "키워드: 키워드1, 키워드2, 키워드3\n\n"
        "이모티콘 사용 금지. 설명 없이 결과만 출력.\n\n"
        + "\n\n".join(post_summaries)
    )

    try:
        print("[AI 분석] 후킹 포인트 및 키워드 추출 중 ...")
        msg = client.messages.create(
            model="sonnet",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        ai_text = msg.content[0].text
    except Exception as e:
        print(f"  [AI 오류] 후킹/키워드 추출 실패: {e}")
        return []

    # 파싱
    results = []
    blocks = re.split(r"\[게시물\s*\d+\]", ai_text)
    for i, block in enumerate(blocks[1:]):  # 첫 번째는 빈 문자열
        hook_match = re.search(r"후킹:\s*(.+)", block)
        kw_match = re.search(r"키워드:\s*(.+)", block)
        hook = hook_match.group(1).strip() if hook_match else ""
        keywords = [k.strip() for k in kw_match.group(1).split(",") if k.strip()] if kw_match else []

        idx = i if i < len(posts_info) else len(posts_info) - 1
        results.append({
            "filename": posts_info[idx]["filename"],
            "subject": posts_info[idx]["subject"],
            "category": posts_info[idx]["category"],
            "hook": hook,
            "keywords": keywords,
        })

    return results


def analyze_comment_patterns(all_replies: dict) -> str:
    """댓글 반응의 공통점을 AI로 분석합니다.

    반환: 분석 결과 텍스트 (마크다운)
    """
    # 댓글이 있는 게시물만 필터링
    posts_with_comments = []
    total_comments = 0
    for fname, data in all_replies.items():
        if data["reply_texts"]:
            comments_preview = "\n".join(
                f"  - {t[:150]}" for t in data["reply_texts"][:20]
            )
            posts_with_comments.append(
                f"게시물: {data['subject']} (카테고리: {data['category']})\n"
                f"댓글 {len(data['reply_texts'])}건:\n{comments_preview}"
            )
            total_comments += len(data["reply_texts"])

    if not posts_with_comments or total_comments < 2:
        return (
            "댓글 데이터가 충분하지 않아 패턴 분석을 수행하지 못했다.\n"
            f"(총 댓글 수: {total_comments}건)"
        )

    client = _get_claude_client()

    prompt = (
        "아래는 초등 자녀 부모 대상 교육 크리에이터 Dream_Grow의 Threads 게시물과 댓글이다.\n\n"
        "다음을 분석하라:\n"
        "1. 부모들이 가장 많이 질문하거나 궁금해하는 주제\n"
        "2. 가장 큰 공감을 얻는 내용 (공감 표현, 경험 공유 등)\n"
        "3. 부모들이 더 알고 싶어하는 것 (추가 정보 요청, 후속 질문 등)\n"
        "4. 반복적으로 나타나는 고민이나 키워드\n\n"
        "분석 결과를 마크다운으로 작성하라. 각 항목은 구체적 댓글 내용을 근거로 들어라.\n"
        "이모티콘 사용 금지. 추측보다 데이터에서 직접 확인되는 패턴만 기술.\n\n"
        + "\n\n---\n\n".join(posts_with_comments)
    )

    try:
        print("[AI 분석] 댓글 반응 패턴 분석 중 ...")
        msg = client.messages.create(
            model="sonnet",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        print(f"  [AI 오류] 댓글 패턴 분석 실패: {e}")
        return f"댓글 패턴 분석 중 오류 발생: {e}"


def suggest_new_topics(all_replies: dict, hooks_data: list, cat_ranked: list) -> str:
    """댓글 패턴과 성과 데이터를 기반으로 새 콘텐츠 주제를 추천합니다.

    반환: 추천 주제 텍스트 (마크다운)
    """
    # 댓글 요약
    comment_summary = []
    for fname, data in all_replies.items():
        if data["reply_texts"]:
            comment_summary.append(
                f"- {data['subject']} ({data['category']}): "
                f"댓글 {len(data['reply_texts'])}건"
            )
            for t in data["reply_texts"][:5]:
                comment_summary.append(f"  - {t[:100]}")

    # 후킹/키워드 요약
    hook_summary = []
    for h in hooks_data:
        hook_summary.append(
            f"- {h['subject']}: 키워드 [{', '.join(h['keywords'])}]"
        )

    # 카테고리 성과 요약
    cat_summary = []
    for cat, stats in cat_ranked:
        avg_v = stats["views"] // max(stats["count"], 1)
        cat_summary.append(f"- {cat}: {stats['count']}개, 평균 조회 {avg_v:,}")

    client = _get_claude_client()

    prompt = (
        "Dream_Grow는 초등 자녀 부모(30~45세) 대상 교육 크리에이터이다.\n"
        "카테고리: 훈육, 수학, 독서, 미디어/AI, 놀이, 감정/심리, 학습, 학교생활, 크리에이터\n\n"
        "아래 데이터를 기반으로 새 Threads 콘텐츠 주제를 3~5개 추천하라.\n\n"
        "## 카테고리별 성과\n" + "\n".join(cat_summary) + "\n\n"
        "## 기존 게시물 키워드\n" + "\n".join(hook_summary) + "\n\n"
        "## 댓글 반응\n" + "\n".join(comment_summary[:50]) + "\n\n"
        "추천 형식:\n"
        "1. [카테고리] 주제명\n"
        "   - 추천 근거 (댓글/성과 데이터 기반)\n"
        "   - 예상 후킹 포인트 한 줄\n\n"
        "이모티콘 사용 금지. 댓글에서 실제 확인된 수요를 근거로 하라. "
        "기존에 다루지 않은 새로운 각도를 우선 추천하라."
    )

    try:
        print("[AI 분석] 새 콘텐츠 주제 추천 중 ...")
        msg = client.messages.create(
            model="sonnet",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        print(f"  [AI 오류] 주제 추천 실패: {e}")
        return f"주제 추천 중 오류 발생: {e}"


# ============================================================
# 발행완료 파일 스캔
# ============================================================

def find_published_files() -> list:
    """64 발행완료/ 폴더에서 thread_id가 있는 파일을 찾습니다."""
    files = []
    if not os.path.isdir(PUBLISHED_DIR):
        print(f"[경고] 발행완료 폴더가 없습니다: {PUBLISHED_DIR}")
        return files

    for fname in os.listdir(PUBLISHED_DIR):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(PUBLISHED_DIR, fname)
        fm = parse_frontmatter(filepath)
        thread_id = fm.get("thread_id", "")
        if thread_id:
            fm["_category"] = fm.get("카테고리", extract_category(fname))
            fm["_hour"] = extract_posting_hour(fm)
            files.append(fm)

    return files


# ============================================================
# Frontmatter 업데이트
# ============================================================

def update_file_metrics(fm: dict, metrics: dict) -> bool:
    """파일의 frontmatter에 성과 지표를 업데이트합니다."""
    filepath = fm["_filepath"]
    content = fm["_content"]

    views = metrics.get("views", 0)
    likes = metrics.get("likes", 0)
    replies = metrics.get("replies", 0)
    reposts = metrics.get("reposts", 0)
    quotes = metrics.get("quotes", 0)

    # 기존 값과 비교하여 변경이 없으면 건너뛰기
    old_views = parse_number(fm.get("조회수", "0"))
    old_likes = parse_number(fm.get("좋아요", "0"))
    if old_views == views and old_likes == likes:
        return False

    # frontmatter 내 각 지표 업데이트 또는 추가
    metric_map = {
        "조회수": f"{views:,}",
        "좋아요": str(likes),
        "답글": str(replies),
        "리포스트": str(reposts),
        "인용": str(quotes),
        "지표갱신일": datetime.now().strftime("%Y-%m-%d"),
    }

    for key, value in metric_map.items():
        pattern = rf"({re.escape(key)}:\s*).*"
        if re.search(pattern, content):
            content = re.sub(pattern, rf"\g<1>{value}", content)
        else:
            # frontmatter 닫는 --- 직전에 추가
            content = content.replace("\n---\n", f"\n{key}: {value}\n---\n", 1)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return True


# ============================================================
# 리포트 생성
# ============================================================

def generate_weekly_report(
    published_files: list,
    account_insights: dict | None = None,
    hooks_data: list | None = None,
    all_replies: dict | None = None,
    comment_analysis: str | None = None,
    topic_suggestions: str | None = None,
):
    """주간 성과 리포트를 생성합니다."""
    os.makedirs(REPORT_DIR, exist_ok=True)

    now = datetime.now()
    # 주간 범위 계산 (월요일 ~ 일요일)
    week_start = now - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=6)
    week_label = f"{week_start.strftime('%m/%d')}~{week_end.strftime('%m/%d')}"

    report_filename = f"주간성과_{now.strftime('%Y-%m-%d')}.md"
    report_path = os.path.join(REPORT_DIR, report_filename)

    # 데이터 수집
    posts_data = []
    for fm in published_files:
        views = parse_number(fm.get("조회수", "0"))
        likes = parse_number(fm.get("좋아요", "0"))
        replies = parse_number(fm.get("답글", "0"))
        reposts = parse_number(fm.get("리포스트", "0"))
        quotes = parse_number(fm.get("인용", "0"))
        category = fm.get("_category", "기타")
        hour = fm.get("_hour")
        engagement = likes + replies + reposts + quotes

        posts_data.append({
            "filename": fm["_filename"],
            "views": views,
            "likes": likes,
            "replies": replies,
            "reposts": reposts,
            "quotes": quotes,
            "engagement": engagement,
            "category": category,
            "hour": hour,
            "subject": fm.get("주제", fm["_filename"]),
        })

    if not posts_data:
        print("[리포트] 성과 데이터가 있는 파일이 없습니다.")
        return None

    # 조회수 기준 정렬
    posts_sorted = sorted(posts_data, key=lambda x: x["views"], reverse=True)

    # 카테고리별 집계
    cat_stats = defaultdict(lambda: {"count": 0, "views": 0, "engagement": 0})
    for p in posts_data:
        cat = p["category"]
        cat_stats[cat]["count"] += 1
        cat_stats[cat]["views"] += p["views"]
        cat_stats[cat]["engagement"] += p["engagement"]

    # 카테고리별 평균 조회수 기준 정렬
    cat_ranked = sorted(
        cat_stats.items(),
        key=lambda x: x[1]["views"] / max(x[1]["count"], 1),
        reverse=True,
    )

    # 시간대별 집계
    hour_stats = defaultdict(lambda: {"count": 0, "views": 0})
    for p in posts_data:
        if p["hour"] is not None:
            hour_stats[p["hour"]]["count"] += 1
            hour_stats[p["hour"]]["views"] += p["views"]

    hour_ranked = sorted(
        hour_stats.items(),
        key=lambda x: x[1]["views"] / max(x[1]["count"], 1),
        reverse=True,
    )

    # 전체 통계
    total_views = sum(p["views"] for p in posts_data)
    total_engagement = sum(p["engagement"] for p in posts_data)
    avg_views = total_views // max(len(posts_data), 1)
    avg_engagement = total_engagement // max(len(posts_data), 1)

    # --- 리포트 작성 ---
    lines = []
    lines.append("---")
    lines.append(f"생성일: {now.strftime('%Y-%m-%d')}")
    lines.append(f"기간: {week_label}")
    lines.append("유형: 주간성과리포트")
    lines.append("---")
    lines.append("")
    lines.append(f"# 주간 성과 리포트 ({week_label})")
    lines.append("")

    # 계정 인사이트 (있는 경우)
    if account_insights:
        lines.append("## 계정 전체 지표 (7일)")
        lines.append("")
        lines.append(f"- 총 조회수: {account_insights.get('views', 0):,}")
        lines.append(f"- 총 좋아요: {account_insights.get('likes', 0):,}")
        lines.append(f"- 총 답글: {account_insights.get('replies', 0):,}")
        lines.append(f"- 총 리포스트: {account_insights.get('reposts', 0):,}")
        followers = account_insights.get("followers_count", 0)
        if followers:
            lines.append(f"- 팔로워 수: {followers:,}")
        lines.append("")

    # 요약
    lines.append("## 요약")
    lines.append("")
    lines.append(f"- 총 게시물: {len(posts_data)}개")
    lines.append(f"- 총 조회수: {total_views:,}")
    lines.append(f"- 평균 조회수: {avg_views:,}")
    lines.append(f"- 총 참여(좋아요+답글+리포스트+인용): {total_engagement:,}")
    lines.append(f"- 평균 참여: {avg_engagement:,}")
    lines.append("")

    # Top 게시물
    lines.append("## 조회수 Top 게시물")
    lines.append("")
    top_n = min(10, len(posts_sorted))
    for i, p in enumerate(posts_sorted[:top_n], 1):
        lines.append(
            f"{i}. **{p['subject'][:40]}** - "
            f"조회 {p['views']:,} / 좋아요 {p['likes']} / "
            f"답글 {p['replies']} / 리포스트 {p['reposts']}"
        )
        lines.append(f"   - 파일: {p['filename']}")
        lines.append(f"   - 카테고리: {p['category']}")
    lines.append("")

    # 카테고리 분석
    lines.append("## 카테고리별 성과")
    lines.append("")
    lines.append("| 카테고리 | 게시물 수 | 총 조회수 | 평균 조회수 | 총 참여 | 평균 참여 |")
    lines.append("|---------|----------|----------|-----------|--------|---------|")
    for cat, stats in cat_ranked:
        count = stats["count"]
        avg_v = stats["views"] // max(count, 1)
        avg_e = stats["engagement"] // max(count, 1)
        lines.append(
            f"| {cat} | {count} | {stats['views']:,} | {avg_v:,} | "
            f"{stats['engagement']:,} | {avg_e:,} |"
        )
    lines.append("")

    # 시간대 분석
    if hour_ranked:
        lines.append("## 발행 시간대별 성과")
        lines.append("")
        lines.append("| 시간 | 게시물 수 | 총 조회수 | 평균 조회수 |")
        lines.append("|------|----------|----------|-----------|")
        for hour, stats in hour_ranked:
            count = stats["count"]
            avg_v = stats["views"] // max(count, 1)
            lines.append(f"| {hour:02d}:00 | {count} | {stats['views']:,} | {avg_v:,} |")
        lines.append("")

    # 추천
    lines.append("## 다음 주 추천")
    lines.append("")

    # 상위 카테고리 추천
    if cat_ranked:
        best_cat = cat_ranked[0][0]
        lines.append(f"- 최고 성과 카테고리: **{best_cat}** - 이 주제의 후속 콘텐츠 기획 권장")

    # 2위 카테고리도 추천 (다양성)
    if len(cat_ranked) >= 2:
        second_cat = cat_ranked[1][0]
        lines.append(f"- 차순위 카테고리: **{second_cat}** - 교차 기획으로 다양성 유지")

    # 저성과 카테고리 분석
    if len(cat_ranked) >= 3:
        worst_cat = cat_ranked[-1][0]
        worst_avg = cat_ranked[-1][1]["views"] // max(cat_ranked[-1][1]["count"], 1)
        lines.append(
            f"- 저조 카테고리: **{worst_cat}** (평균 조회 {worst_avg:,}) "
            f"- 후킹 강화 또는 주제 재설정 검토"
        )

    # 최적 시간대 추천
    if hour_ranked:
        best_hour = hour_ranked[0][0]
        lines.append(f"- 최적 발행 시간: **{best_hour:02d}:00** 전후 - 다음 주 발행 시간에 반영 권장")

    # Top 게시물 후속 콘텐츠 추천
    if posts_sorted:
        top_post = posts_sorted[0]
        lines.append(
            f"- 최고 조회 게시물({top_post['subject'][:20]}) 후속/심화 콘텐츠 기획 권장"
        )

    lines.append("")

    # --- 후킹 포인트 및 핵심 키워드 ---
    if hooks_data:
        lines.append("## 게시물별 후킹 포인트 및 핵심 키워드")
        lines.append("")
        for h in hooks_data:
            lines.append(f"### {h['subject'][:50]}")
            lines.append(f"- 카테고리: {h['category']}")
            lines.append(f"- 후킹: {h['hook']}")
            lines.append(f"- 키워드: {', '.join(h['keywords'])}")
            lines.append("")

    # --- 댓글 수집 현황 ---
    if all_replies:
        lines.append("## 댓글 수집 현황")
        lines.append("")
        total_reply_count = sum(len(d["reply_texts"]) for d in all_replies.values())
        posts_with_replies = sum(1 for d in all_replies.values() if d["reply_texts"])
        lines.append(f"- 총 댓글 수: {total_reply_count}건")
        lines.append(f"- 댓글이 있는 게시물: {posts_with_replies}개 / 전체 {len(all_replies)}개")
        lines.append("")

        # 댓글 많은 순 정렬
        sorted_by_replies = sorted(
            all_replies.items(),
            key=lambda x: len(x[1]["reply_texts"]),
            reverse=True,
        )
        lines.append("| 게시물 | 카테고리 | 댓글 수 |")
        lines.append("|--------|---------|--------|")
        for fname, data in sorted_by_replies[:10]:
            if data["reply_texts"]:
                lines.append(
                    f"| {data['subject'][:40]} | {data['category']} | "
                    f"{len(data['reply_texts'])} |"
                )
        lines.append("")

    # --- 댓글 반응 패턴 분석 ---
    if comment_analysis:
        lines.append("## 댓글 반응 패턴 분석")
        lines.append("")
        lines.append(comment_analysis)
        lines.append("")

    # --- 추가 주제 추천 ---
    if topic_suggestions:
        lines.append("## 댓글 기반 신규 주제 추천")
        lines.append("")
        lines.append(topic_suggestions)
        lines.append("")

    report_content = "\n".join(lines)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"[리포트] 저장 완료: {report_path}")
    return report_path


# ============================================================
# 메인 실행
# ============================================================

def run_update(dry_run: bool = False) -> list:
    """발행완료 파일의 성과 지표를 API로 업데이트합니다."""
    if not check_api_config():
        return []

    files = find_published_files()
    if not files:
        print("[업데이트] thread_id가 있는 발행완료 파일이 없습니다.")
        return []

    print(f"[업데이트] 대상: {len(files)}개 파일")

    updated = 0
    failed = 0
    skipped = 0

    for fm in files:
        thread_id = fm.get("thread_id", "")
        filename = fm["_filename"]

        if dry_run:
            print(f"  [DRY RUN] {filename} (ID: {thread_id})")
            continue

        print(f"  수집 중: {filename} ... ", end="", flush=True)
        metrics = fetch_post_insights(thread_id)

        if metrics is None:
            print("실패")
            failed += 1
            time.sleep(API_DELAY)
            continue

        # frontmatter에 지표 반영
        changed = update_file_metrics(fm, metrics)
        if changed:
            # fm dict도 갱신 (리포트용)
            fm["조회수"] = str(metrics.get("views", 0))
            fm["좋아요"] = str(metrics.get("likes", 0))
            fm["답글"] = str(metrics.get("replies", 0))
            fm["리포스트"] = str(metrics.get("reposts", 0))
            fm["인용"] = str(metrics.get("quotes", 0))
            print(f"갱신 (조회 {metrics.get('views', 0):,})")
            updated += 1
        else:
            print("변경 없음")
            skipped += 1

        time.sleep(API_DELAY)

    if not dry_run:
        print(f"\n[업데이트 완료] 갱신 {updated} / 변경없음 {skipped} / 실패 {failed}")

    # 업데이트된 데이터로 파일 목록 재읽기 (리포트용)
    return find_published_files()


def run_report(published_files: list = None):
    """주간 성과 리포트를 생성합니다.

    댓글 수집, 후킹/키워드 추출, 댓글 패턴 분석, 주제 추천을 포함합니다.
    """
    if published_files is None:
        published_files = find_published_files()

    if not published_files:
        print("[리포트] 발행완료 파일이 없습니다.")
        return

    print(f"[리포트] 대상: {len(published_files)}개 파일")

    # 계정 인사이트 수집 (가능한 경우)
    account_insights = None
    if check_api_config():
        print("[리포트] 계정 인사이트 수집 중 ...")
        account_insights = fetch_account_insights(days=7)
        if account_insights:
            print(f"  계정 7일 조회수: {account_insights.get('views', 0):,}")
        else:
            print("  계정 인사이트 수집 실패 (게시물 데이터로 리포트 생성)")

    # 댓글 수집
    all_replies = {}
    if check_api_config():
        print("\n[리포트] 댓글 수집 시작 ...")
        all_replies = collect_all_replies(published_files)
        total_comments = sum(len(d["reply_texts"]) for d in all_replies.values())
        print(f"  총 댓글: {total_comments}건")

    # 후킹 포인트 및 키워드 추출 (AI)
    hooks_data = []
    try:
        hooks_data = extract_hooks_and_keywords(published_files)
        print(f"  후킹/키워드 추출 완료: {len(hooks_data)}건")
    except Exception as e:
        print(f"  [경고] 후킹/키워드 추출 실패 (리포트는 계속 생성): {e}")

    # 카테고리 성과 (AI 분석에 전달용)
    cat_stats = defaultdict(lambda: {"count": 0, "views": 0, "engagement": 0})
    for fm in published_files:
        cat = fm.get("_category", "기타")
        cat_stats[cat]["count"] += 1
        cat_stats[cat]["views"] += parse_number(fm.get("조회수", "0"))
        likes = parse_number(fm.get("좋아요", "0"))
        replies = parse_number(fm.get("답글", "0"))
        reposts = parse_number(fm.get("리포스트", "0"))
        quotes = parse_number(fm.get("인용", "0"))
        cat_stats[cat]["engagement"] += likes + replies + reposts + quotes
    cat_ranked = sorted(
        cat_stats.items(),
        key=lambda x: x[1]["views"] / max(x[1]["count"], 1),
        reverse=True,
    )

    # 댓글 반응 패턴 분석 (AI)
    comment_analysis = None
    if all_replies:
        try:
            comment_analysis = analyze_comment_patterns(all_replies)
        except Exception as e:
            print(f"  [경고] 댓글 패턴 분석 실패 (리포트는 계속 생성): {e}")

    # 신규 주제 추천 (AI)
    topic_suggestions = None
    if all_replies or hooks_data:
        try:
            topic_suggestions = suggest_new_topics(all_replies, hooks_data, cat_ranked)
        except Exception as e:
            print(f"  [경고] 주제 추천 실패 (리포트는 계속 생성): {e}")

    generate_weekly_report(
        published_files,
        account_insights,
        hooks_data=hooks_data,
        all_replies=all_replies,
        comment_analysis=comment_analysis,
        topic_suggestions=topic_suggestions,
    )


def main():
    dry_run = "--dry-run" in sys.argv
    mode_update = "--update" in sys.argv
    mode_report = "--report" in sys.argv

    now = datetime.now()
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Threads Insights 수집기")
    if dry_run:
        print("  모드: DRY RUN")
    print()

    # 인자 없이 실행하면 전체 (업데이트 + 리포트)
    run_all = not mode_update and not mode_report

    files = None
    if mode_update or run_all:
        files = run_update(dry_run=dry_run)
        print()

    if mode_report or run_all:
        # 업데이트 직후라면 갱신된 파일 목록 사용
        run_report(files)

    print("\n완료.")


if __name__ == "__main__":
    main()
