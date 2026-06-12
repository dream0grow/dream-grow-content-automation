"""발행 캘린더 생성기 - 파이프라인 스캔 → 주간 캘린더 + 영상 트래킹

사용법:
  python3 publish_calendar.py              # 이번 주 캘린더 생성
  python3 publish_calendar.py --next       # 다음 주 캘린더 생성
  python3 publish_calendar.py --month      # 이번 달 월간 캘린더 생성
"""
import os
import re
import sys
from datetime import datetime, timedelta
from collections import defaultdict

# 경로
SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
REVIEW_DIR = os.path.join(SNS_SYSTEM, "05 리뷰/대기")
CALENDAR_DIR = os.path.join(SNS_SYSTEM, "06 제작/54 발행 캘린더")
PUBLISHED_DIR = os.path.join(SNS_SYSTEM, "06 제작/64 발행완료")
LIBRARY_DIR = os.path.join(SNS_SYSTEM, "03 라이브러리/38 주제별 콘텐츠")

WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]

# 카테고리 정규화 맵
CATEGORY_MAP = {
    "독서읽기": "독서", "독서": "독서",
    "수학": "수학", "수학연산": "수학",
    "훈육": "훈육", "훈육지도": "훈육", "훈육, 감정": "훈육",
    "감정/심리": "감정", "뇌발달심리": "감정",
    "학습": "학습", "습관루틴": "학습", "수학, 학습": "학습",
    "미디어/AI": "미디어", "영어": "학습",
    "놀이": "놀이",
    "학교생활": "학교", "학부모소통": "학교",
    "크리에이터": "크리에이터",
}


def parse_frontmatter(filepath: str) -> dict:
    """frontmatter를 딕셔너리로 파싱."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = {}
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if match:
        for line in match.group(1).split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                fm[key.strip()] = val.strip().strip("\"'")
    fm["_filename"] = os.path.basename(filepath)
    fm["_filepath"] = filepath
    return fm


def scan_pipeline() -> dict:
    """파이프라인 전체를 스캔하여 상태별로 분류."""
    result = {"초안": [], "리뷰대기": [], "발행대기": [], "발행완료": []}

    # 05 리뷰/대기
    if os.path.isdir(REVIEW_DIR):
        for fname in os.listdir(REVIEW_DIR):
            if not fname.endswith(".md"):
                continue
            fm = parse_frontmatter(os.path.join(REVIEW_DIR, fname))
            status = fm.get("상태", "초안")
            if status in result:
                result[status].append(fm)
            else:
                result["초안"].append(fm)

    # 64 발행완료
    if os.path.isdir(PUBLISHED_DIR):
        for fname in os.listdir(PUBLISHED_DIR):
            if fname.endswith(".md"):
                fm = parse_frontmatter(os.path.join(PUBLISHED_DIR, fname))
                result["발행완료"].append(fm)

    return result


def scan_video_tracking() -> list:
    """영상(릴스/YT) 제작 상태를 스캔."""
    videos = []
    if os.path.isdir(REVIEW_DIR):
        for fname in os.listdir(REVIEW_DIR):
            if not fname.endswith(".md"):
                continue
            fm = parse_frontmatter(os.path.join(REVIEW_DIR, fname))
            channel = fm.get("채널", "")
            if channel in ("reels", "youtube") or "릴스" in fname or "YT" in fname:
                fm["_channel"] = "릴스" if channel == "reels" or "릴스" in fname else "YouTube"
                # 영상 제작 단계: 원고작성 → 촬영 → 편집 → 발행
                video_status = fm.get("영상상태", "원고작성")
                fm["_video_status"] = video_status
                videos.append(fm)
    return videos


def categorize(items: list) -> dict:
    """카테고리별로 그룹핑."""
    grouped = defaultdict(list)
    for item in items:
        raw_cat = item.get("카테고리", "기타")
        cat = CATEGORY_MAP.get(raw_cat, raw_cat)
        grouped[cat].append(item)
    return dict(grouped)


def get_week_dates(offset: int = 0) -> tuple:
    """이번 주(또는 offset 주) 월~일 날짜를 반환."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    sunday = monday + timedelta(days=6)
    dates = [monday + timedelta(days=i) for i in range(7)]
    return monday, sunday, dates


def generate_weekly_calendar(pipeline: dict, videos: list, offset: int = 0) -> str:
    """주간 발행 캘린더 마크다운 생성."""
    monday, sunday, dates = get_week_dates(offset)
    week_label = f"{monday.strftime('%Y-%m-%d')} ~ {sunday.strftime('%Y-%m-%d')}"
    week_num = monday.isocalendar()[1]

    ready = pipeline["리뷰대기"]
    ready_by_cat = categorize(ready)
    draft = pipeline["초안"]
    draft_by_cat = categorize(draft)

    lines = []
    lines.append("---")
    lines.append(f"주차: {monday.strftime('%Y')}년 {week_num}주차")
    lines.append(f"기간: {week_label}")
    lines.append(f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("상태: 진행중")
    lines.append("---")
    lines.append("")
    lines.append(f"# {monday.strftime('%m/%d')}~{sunday.strftime('%m/%d')} 발행 캘린더")
    lines.append("")

    # 파이프라인 현황
    lines.append("## 파이프라인 현황")
    lines.append("")
    lines.append(f"| 상태 | 수량 |")
    lines.append(f"|------|------|")
    lines.append(f"| 초안 | {len(pipeline['초안'])}개 |")
    lines.append(f"| 리뷰대기 | {len(pipeline['리뷰대기'])}개 |")
    lines.append(f"| 발행완료 | {len(pipeline['발행완료'])}개 |")
    lines.append("")

    # 주간 발행 계획 (일별 슬롯)
    lines.append("## 주간 발행 계획")
    lines.append("")

    # 리뷰대기 콘텐츠를 요일별로 배분 제안
    ready_list = list(ready)
    slot_idx = 0
    daily_plan = {i: [] for i in range(7)}

    # 기본 배분: 월~금 하루 1~2개
    for item in ready_list:
        day = slot_idx % 5  # 월~금에 배분
        daily_plan[day].append(item)
        slot_idx += 1

    for i, date in enumerate(dates):
        day_kr = WEEKDAYS_KR[i]
        date_str = date.strftime("%m/%d")
        lines.append(f"### {day_kr} ({date_str})")
        lines.append("")
        if daily_plan[i]:
            for item in daily_plan[i]:
                cat = CATEGORY_MAP.get(item.get("카테고리", ""), item.get("카테고리", ""))
                title = item.get("주제", item["_filename"].replace(".md", ""))
                status_mark = "리뷰대기" if item.get("상태") == "리뷰대기" else "초안"
                lines.append(f"- [ ] [{cat}] {title} ({status_mark})")
            lines.append("")
        else:
            lines.append("- (비어 있음)")
            lines.append("")

    # 카테고리별 재고
    lines.append("## 카테고리별 재고 (리뷰대기)")
    lines.append("")
    if ready_by_cat:
        for cat in sorted(ready_by_cat.keys()):
            items = ready_by_cat[cat]
            lines.append(f"### {cat} ({len(items)}개)")
            for item in items:
                title = item.get("주제", item["_filename"].replace(".md", ""))
                lines.append(f"- {title}")
            lines.append("")
    else:
        lines.append("리뷰대기 콘텐츠가 없습니다.")
        lines.append("")

    # 영상 제작 트래킹
    lines.append("## 영상 제작 트래킹")
    lines.append("")
    if videos:
        lines.append("| 파일 | 채널 | 상태 | 원고 | 촬영 | 편집 | 발행 |")
        lines.append("|------|------|------|------|------|------|------|")
        for v in videos:
            fname = v["_filename"].replace(".md", "")[:30]
            ch = v.get("_channel", "?")
            vs = v.get("_video_status", "원고작성")
            # 체크박스 상태
            stages = {"원고작성": 1, "촬영": 2, "편집": 3, "발행": 4}
            stage_num = stages.get(vs, 1)
            checks = []
            for s_name, s_num in [("원고", 1), ("촬영", 2), ("편집", 3), ("발행", 4)]:
                if stage_num > s_num:
                    checks.append("v")
                elif stage_num == s_num:
                    checks.append("->")
                else:
                    checks.append("")
            lines.append(f"| {fname} | {ch} | {vs} | {checks[0]} | {checks[1]} | {checks[2]} | {checks[3]} |")
        lines.append("")
    else:
        lines.append("영상 제작 파일이 없습니다. (채널: reels/youtube 또는 파일명에 릴스/YT 포함)")
        lines.append("")

    # 메모
    lines.append("## 메모")
    lines.append("")
    lines.append("- ")
    lines.append("")

    return "\n".join(lines)


def generate_monthly_calendar(pipeline: dict) -> str:
    """월간 캘린더 마크다운 생성."""
    today = datetime.now()
    month_label = today.strftime("%Y년 %m월")

    lines = []
    lines.append("---")
    lines.append(f"월: {month_label}")
    lines.append(f"생성일: {today.strftime('%Y-%m-%d %H:%M')}")
    lines.append("상태: 진행중")
    lines.append("---")
    lines.append("")
    lines.append(f"# {month_label} 발행 캘린더")
    lines.append("")

    # 주차별 요약
    lines.append("## 주차별 계획")
    lines.append("")
    lines.append("| 주차 | 월 | 화 | 수 | 목 | 금 | 비고 |")
    lines.append("|------|----|----|----|----|----|----|")

    # 이번 달 주차 계산
    first_day = today.replace(day=1)
    if today.month == 12:
        last_day = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last_day = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    current = first_day - timedelta(days=first_day.weekday())  # 첫 주 월요일
    week_num = 1
    while current <= last_day:
        week_end = current + timedelta(days=4)  # 금요일
        lines.append(f"| {week_num}주 ({current.strftime('%m/%d')}~) | | | | | | |")
        current += timedelta(weeks=1)
        week_num += 1
    lines.append("")

    # 파이프라인 요약
    lines.append("## 파이프라인 현황")
    lines.append("")
    lines.append(f"- 초안: {len(pipeline['초안'])}개")
    lines.append(f"- 리뷰대기: {len(pipeline['리뷰대기'])}개")
    lines.append(f"- 발행완료: {len(pipeline['발행완료'])}개")
    lines.append("")

    # 카테고리 분포
    all_items = pipeline["초안"] + pipeline["리뷰대기"]
    by_cat = categorize(all_items)
    lines.append("## 카테고리 분포")
    lines.append("")
    lines.append("| 카테고리 | 수량 |")
    lines.append("|----------|------|")
    for cat in sorted(by_cat.keys()):
        lines.append(f"| {cat} | {len(by_cat[cat])}개 |")
    lines.append("")

    return "\n".join(lines)


def main():
    is_next = "--next" in sys.argv
    is_month = "--month" in sys.argv

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 발행 캘린더 생성기\n")

    # 파이프라인 스캔
    pipeline = scan_pipeline()
    videos = scan_video_tracking()

    total = sum(len(v) for v in pipeline.values())
    print(f"파이프라인 스캔 완료: {total}개 콘텐츠")
    for status, items in pipeline.items():
        print(f"  {status}: {len(items)}개")
    print(f"  영상 제작: {len(videos)}개")
    print()

    os.makedirs(CALENDAR_DIR, exist_ok=True)

    if is_month:
        content = generate_monthly_calendar(pipeline)
        today = datetime.now()
        filename = f"{today.strftime('%Y-%m')} 발행 계획.md"
    else:
        offset = 1 if is_next else 0
        content = generate_weekly_calendar(pipeline, videos, offset)
        monday, sunday, _ = get_week_dates(offset)
        filename = f"{monday.strftime('%Y-%m-%d')} 주간 발행 계획.md"

    filepath = os.path.join(CALENDAR_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"생성 완료: {filename}")
    print(f"경로: {filepath}")


if __name__ == "__main__":
    main()
