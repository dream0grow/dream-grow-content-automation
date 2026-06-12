"""발행 캘린더 자동 스케줄러

리뷰완료 콘텐츠에 발행시간을 자동 배정합니다.
- 카테고리 균형: 같은 카테고리 연일 배치 금지
- 최적 시간대: 07:00, 12:00, 19:00, 21:00 (KST)
- 하루 1~2개, 향후 7일 빈 슬롯 채움
- 주간 캘린더 요약 자동 생성

사용법:
  python3 calendar_scheduler.py              # 미배정 파일에 발행시간 자동 배정
  python3 calendar_scheduler.py --preview    # 배정 계획만 보기 (파일 수정 안 함)
  python3 calendar_scheduler.py --calendar   # 현재 주간 캘린더 출력
"""
import os
import re
import sys
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_client; claude_client.patch_anthropic()
from dotenv import load_dotenv
load_dotenv()

# === 경로 ===
SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
REVIEW_DONE_DIR = os.path.join(SNS_SYSTEM, "05 리뷰/완료")
REVIEW_WAIT_DIR = os.path.join(SNS_SYSTEM, "05 리뷰/대기")
CALENDAR_DIR = os.path.join(SNS_SYSTEM, "06 제작/54 발행 캘린더")
PUBLISHED_DIR = os.path.join(SNS_SYSTEM, "06 제작/64 발행완료")

# === 설정 ===
# 하루 중 발행 가능한 시간대 (KST)
PUBLISH_HOURS = [(7, 10), (17, 50), (20, 50)]  # (시, 분) 튜플
# 하루 최대 발행 수
MAX_PER_DAY = 6
# 스케줄링 대상 기간 (일)
SCHEDULE_DAYS = 7

WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]

# 카테고리 정규화 맵 (publish_calendar.py와 동일)
CATEGORY_MAP = {
    "독서읽기": "독서", "독서": "독서",
    "수학": "수학", "수학연산": "수학",
    "훈육": "훈육", "훈육지도": "훈육", "훈육, 감정": "훈육",
    "감정/심리": "감정", "뇌발달심리": "감정", "감정": "감정",
    "학습": "학습", "습관루틴": "학습", "수학, 학습": "학습",
    "미디어/AI": "미디어", "미디어": "미디어", "영어": "학습",
    "놀이": "놀이",
    "학교생활": "학교", "학부모소통": "학교", "학교": "학교",
    "크리에이터": "크리에이터",
}

ALL_CATEGORIES = ["훈육", "수학", "독서", "미디어", "놀이", "감정", "학습", "학교", "크리에이터"]


# === 파일 파싱 ===

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
    fm["_content"] = content
    fm["_filepath"] = filepath
    fm["_filename"] = os.path.basename(filepath)
    return fm


def normalize_category(raw: str) -> str:
    """카테고리를 표준 이름으로 정규화."""
    return CATEGORY_MAP.get(raw, raw)


def parse_publish_time(time_str: str) -> datetime | None:
    """발행시간 문자열을 datetime으로 변환."""
    if not time_str or time_str.strip() == "":
        return None
    time_str = time_str.strip()
    for fmt in [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    return None


# === 파일 스캔 ===

def find_unscheduled_files() -> list:
    """발행시간이 없는 리뷰완료 파일을 찾는다."""
    unscheduled = []
    if not os.path.isdir(REVIEW_DONE_DIR):
        return unscheduled

    for fname in sorted(os.listdir(REVIEW_DONE_DIR)):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(REVIEW_DONE_DIR, fname)
        fm = parse_frontmatter(filepath)
        status = fm.get("상태", "")
        pub_time = parse_publish_time(fm.get("발행시간", ""))

        # 리뷰완료 상태이고 발행시간이 없는 파일만 대상
        if status == "리뷰완료" and pub_time is None:
            fm["_category"] = normalize_category(fm.get("카테고리", "기타"))
            unscheduled.append(fm)

    return unscheduled


def find_already_scheduled() -> list:
    """이미 발행시간이 배정된 파일을 찾는다 (05 리뷰/완료/)."""
    scheduled = []
    if not os.path.isdir(REVIEW_DONE_DIR):
        return scheduled

    for fname in sorted(os.listdir(REVIEW_DONE_DIR)):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(REVIEW_DONE_DIR, fname)
        fm = parse_frontmatter(filepath)
        pub_time = parse_publish_time(fm.get("발행시간", ""))
        if pub_time:
            fm["_pub_time"] = pub_time
            fm["_category"] = normalize_category(fm.get("카테고리", "기타"))
            scheduled.append(fm)

    return scheduled


def find_recently_published() -> list:
    """최근 발행완료된 파일에서 카테고리 정보를 가져온다."""
    published = []
    if not os.path.isdir(PUBLISHED_DIR):
        return published

    for fname in sorted(os.listdir(PUBLISHED_DIR)):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(PUBLISHED_DIR, fname)
        fm = parse_frontmatter(filepath)
        pub_time = parse_publish_time(fm.get("발행시간", ""))
        if pub_time:
            fm["_pub_time"] = pub_time
            fm["_category"] = normalize_category(fm.get("카테고리", "기타"))
            published.append(fm)

    return published


# === 스케줄링 엔진 ===

def build_occupied_slots(scheduled: list, published: list) -> dict:
    """이미 점유된 슬롯을 날짜별로 정리한다.

    반환: { 'YYYY-MM-DD': [{'hour': int, 'minute': int, 'category': str, 'filename': str}, ...] }
    """
    slots = defaultdict(list)
    for fm in scheduled + published:
        pt = fm["_pub_time"]
        date_key = pt.strftime("%Y-%m-%d")
        slots[date_key].append({
            "hour": pt.hour,
            "minute": pt.minute,
            "category": fm.get("_category", "기타"),
            "filename": fm["_filename"],
        })
    return slots


def get_previous_day_categories(slots: dict, date_key: str) -> set:
    """전날 발행된 카테고리 집합을 반환."""
    prev_date = datetime.strptime(date_key, "%Y-%m-%d") - timedelta(days=1)
    prev_key = prev_date.strftime("%Y-%m-%d")
    return {s["category"] for s in slots.get(prev_key, [])}


def get_day_categories(slots: dict, date_key: str) -> set:
    """해당 날짜에 이미 배정된 카테고리 집합."""
    return {s["category"] for s in slots.get(date_key, [])}


def get_available_hours(slots: dict, date_key: str) -> list:
    """해당 날짜에서 아직 비어있는 발행 시간대를 반환. (시, 분) 튜플 리스트."""
    used_hm = {(s["hour"], s.get("minute", 0)) for s in slots.get(date_key, [])}
    return [hm for hm in PUBLISH_HOURS if hm not in used_hm]


def schedule_files(unscheduled: list, scheduled: list, published: list) -> list:
    """미배정 파일에 발행시간을 배정한다.

    반환: [(fm, assigned_datetime), ...]

    배정 규칙:
    1. 오늘+1일부터 SCHEDULE_DAYS일 동안의 슬롯을 채운다
    2. 하루 최대 MAX_PER_DAY개
    3. 같은 카테고리를 연일 배치하지 않는다
    4. 같은 날에 같은 카테고리를 배치하지 않는다
    5. 카테고리 다양성을 최대화한다
    """
    if not unscheduled:
        return []

    slots = build_occupied_slots(scheduled, published)
    assignments = []

    # 내일부터 시작 (오늘은 급하게 넣지 않음)
    now = datetime.now()
    start_date = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # 카테고리별로 그룹핑하여 라운드 로빈 배정
    by_category = defaultdict(list)
    for fm in unscheduled:
        by_category[fm["_category"]].append(fm)

    # 카테고리 순환 큐 생성 (재고가 많은 순서)
    cat_queue = sorted(by_category.keys(), key=lambda c: -len(by_category[c]))
    remaining = list(unscheduled)  # 아직 배정 안 된 파일

    for day_offset in range(SCHEDULE_DAYS):
        target_date = start_date + timedelta(days=day_offset)
        date_key = target_date.strftime("%Y-%m-%d")

        available_hours = get_available_hours(slots, date_key)
        day_count = len(slots.get(date_key, []))

        if day_count >= MAX_PER_DAY or not available_hours:
            continue

        prev_cats = get_previous_day_categories(slots, date_key)
        day_cats = get_day_categories(slots, date_key)
        slots_to_fill = min(MAX_PER_DAY - day_count, len(available_hours))

        for _ in range(slots_to_fill):
            if not remaining:
                break
            if not available_hours:
                break

            # 최적 파일 선택: 전날/당일 카테고리와 겹치지 않는 것 우선
            best = None
            best_idx = -1

            # 1차: 전날+당일 카테고리와 모두 겹치지 않는 파일
            for i, fm in enumerate(remaining):
                cat = fm["_category"]
                if cat not in prev_cats and cat not in day_cats:
                    best = fm
                    best_idx = i
                    break

            # 2차: 당일 카테고리와만 겹치지 않는 파일
            if best is None:
                for i, fm in enumerate(remaining):
                    cat = fm["_category"]
                    if cat not in day_cats:
                        best = fm
                        best_idx = i
                        break

            # 3차: 아무거나 (카테고리 균형 포기)
            if best is None:
                best = remaining[0]
                best_idx = 0

            # 시간 배정
            hour, minute = available_hours.pop(0)
            assigned_dt = target_date.replace(hour=hour, minute=minute)

            assignments.append((best, assigned_dt))

            # 슬롯 업데이트
            slots[date_key].append({
                "hour": hour,
                "minute": minute,
                "category": best["_category"],
                "filename": best["_filename"],
            })
            day_cats.add(best["_category"])

            remaining.pop(best_idx)

    return assignments


# === 파일 수정 ===

def update_frontmatter_publish_time(filepath: str, publish_time: datetime) -> bool:
    """파일의 frontmatter에 발행시간을 기록한다."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    time_str = publish_time.strftime("%Y-%m-%d %H:%M")

    # frontmatter 내 발행시간 필드 업데이트
    match = re.match(r"^(---\n)(.*?)(\n---)", content, re.DOTALL)
    if not match:
        print(f"  [경고] frontmatter 없음: {os.path.basename(filepath)}")
        return False

    fm_block = match.group(2)

    # 발행시간 필드가 있으면 업데이트, 없으면 추가
    if re.search(r"^발행시간\s*:", fm_block, re.MULTILINE):
        new_fm = re.sub(
            r"^(발행시간\s*:).*$",
            f"\\g<1> {time_str}",
            fm_block,
            flags=re.MULTILINE,
        )
    else:
        new_fm = fm_block + f"\n발행시간: {time_str}"

    new_content = match.group(1) + new_fm + match.group(3) + content[match.end():]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True


# === 캘린더 요약 생성 ===

def generate_calendar_summary(scheduled: list, published: list, new_assignments: list) -> str:
    """주간 캘린더 요약 마크다운을 생성한다."""
    now = datetime.now()
    # 이번 주 월요일~일요일
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6)
    # 다음 주까지 포함
    next_sunday = sunday + timedelta(days=7)

    lines = []
    lines.append("---")
    lines.append(f"생성일: {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"기간: {monday.strftime('%Y-%m-%d')} ~ {next_sunday.strftime('%Y-%m-%d')}")
    lines.append("유형: 자동 스케줄링 결과")
    lines.append("---")
    lines.append("")
    lines.append(f"# 발행 스케줄 ({monday.strftime('%m/%d')}~{next_sunday.strftime('%m/%d')})")
    lines.append("")

    # 모든 스케줄 항목 통합
    all_items = []
    for fm in scheduled:
        all_items.append({
            "datetime": fm["_pub_time"],
            "category": fm.get("_category", "기타"),
            "filename": fm["_filename"],
            "source": "기존",
        })
    for fm in published:
        if fm["_pub_time"] >= monday:
            all_items.append({
                "datetime": fm["_pub_time"],
                "category": fm.get("_category", "기타"),
                "filename": fm["_filename"],
                "source": "발행완료",
            })
    for fm, dt in new_assignments:
        all_items.append({
            "datetime": dt,
            "category": fm.get("_category", "기타"),
            "filename": fm["_filename"],
            "source": "신규배정",
        })

    all_items.sort(key=lambda x: x["datetime"])

    # 일별 그룹핑
    by_date = defaultdict(list)
    for item in all_items:
        date_key = item["datetime"].strftime("%Y-%m-%d")
        by_date[date_key].append(item)

    # 2주간 캘린더 출력
    lines.append("## 일별 발행 계획")
    lines.append("")

    current = monday
    while current <= next_sunday:
        date_key = current.strftime("%Y-%m-%d")
        weekday = WEEKDAYS_KR[current.weekday()]
        is_today = current.date() == now.date()
        today_mark = " [오늘]" if is_today else ""

        lines.append(f"### {weekday} {current.strftime('%m/%d')}{today_mark}")
        lines.append("")

        items = by_date.get(date_key, [])
        if items:
            for item in sorted(items, key=lambda x: x["datetime"]):
                time_str = item["datetime"].strftime("%H:%M")
                status = ""
                if item["source"] == "발행완료":
                    status = " (발행완료)"
                elif item["source"] == "신규배정":
                    status = " (신규)"
                fname = item["filename"].replace(".md", "")
                lines.append(f"- {time_str} | [{item['category']}] {fname}{status}")
        else:
            lines.append("- (비어 있음)")

        lines.append("")
        current += timedelta(days=1)

    # 카테고리 분포 요약
    lines.append("## 카테고리 분포")
    lines.append("")
    cat_count = defaultdict(int)
    for item in all_items:
        cat_count[item["category"]] += 1

    if cat_count:
        lines.append("| 카테고리 | 수량 |")
        lines.append("|----------|------|")
        for cat in sorted(cat_count.keys()):
            lines.append(f"| {cat} | {cat_count[cat]}개 |")
        lines.append("")
    else:
        lines.append("스케줄된 콘텐츠가 없습니다.")
        lines.append("")

    # 신규 배정 목록
    if new_assignments:
        lines.append("## 이번 배정 내역")
        lines.append("")
        lines.append("| 파일 | 카테고리 | 발행시간 |")
        lines.append("|------|----------|----------|")
        for fm, dt in new_assignments:
            fname = fm["_filename"].replace(".md", "")
            lines.append(f"| {fname} | {fm['_category']} | {dt.strftime('%m/%d %H:%M')} |")
        lines.append("")

    return "\n".join(lines)


# === 메인 커맨드 ===

def cmd_schedule(preview: bool = False):
    """미배정 파일에 발행시간을 자동 배정한다."""
    now = datetime.now()
    print(f"[{now.strftime('%Y-%m-%d %H:%M')}] 발행 캘린더 자동 스케줄러\n")

    # 스캔
    unscheduled = find_unscheduled_files()
    scheduled = find_already_scheduled()
    published = find_recently_published()

    print(f"스캔 결과:")
    print(f"  리뷰완료 (미배정): {len(unscheduled)}개")
    print(f"  리뷰완료 (배정됨): {len(scheduled)}개")
    print(f"  발행완료 (참고용): {len(published)}개")
    print()

    if not unscheduled:
        print("배정할 파일이 없습니다.")
        print("팁: 05 리뷰/완료/ 에서 상태가 '리뷰완료'이고 발행시간이 비어있는 파일이 대상입니다.")
        return

    # 스케줄링
    assignments = schedule_files(unscheduled, scheduled, published)

    if not assignments:
        print("배정 가능한 슬롯이 없습니다.")
        print(f"팁: 향후 {SCHEDULE_DAYS}일 내 슬롯이 모두 차 있습니다.")
        return

    # 결과 출력
    print(f"배정 계획 ({len(assignments)}개):")
    print()
    for fm, dt in assignments:
        weekday = WEEKDAYS_KR[dt.weekday()]
        print(f"  {dt.strftime('%m/%d')} ({weekday}) {dt.strftime('%H:%M')} | [{fm['_category']}] {fm['_filename']}")

    if preview:
        print()
        print("[미리보기 모드] 파일은 수정되지 않았습니다.")
        return

    # 파일 수정
    print()
    print("frontmatter 업데이트 중...")
    success = 0
    for fm, dt in assignments:
        if update_frontmatter_publish_time(fm["_filepath"], dt):
            print(f"  완료: {fm['_filename']} -> {dt.strftime('%Y-%m-%d %H:%M')}")
            success += 1
        else:
            print(f"  실패: {fm['_filename']}")

    print(f"\n배정 완료: {success}/{len(assignments)}개")

    # 캘린더 요약 생성
    os.makedirs(CALENDAR_DIR, exist_ok=True)
    monday = now - timedelta(days=now.weekday())
    cal_filename = f"{monday.strftime('%Y-%m-%d')} 자동 스케줄.md"
    cal_path = os.path.join(CALENDAR_DIR, cal_filename)

    # 배정 후 다시 스캔하여 최신 상태 반영
    scheduled_updated = find_already_scheduled()
    cal_content = generate_calendar_summary(scheduled_updated, published, [])
    with open(cal_path, "w", encoding="utf-8") as f:
        f.write(cal_content)

    print(f"\n캘린더 저장: {cal_filename}")
    print(f"경로: {cal_path}")


def cmd_calendar():
    """현재 주간 캘린더를 출력한다."""
    now = datetime.now()
    print(f"[{now.strftime('%Y-%m-%d %H:%M')}] 주간 발행 캘린더\n")

    scheduled = find_already_scheduled()
    published = find_recently_published()
    unscheduled = find_unscheduled_files()

    # 이번 주 범위
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    next_sunday = monday + timedelta(days=13)

    # 일별 출력
    all_items = []
    for fm in scheduled:
        all_items.append((fm["_pub_time"], fm.get("_category", "기타"), fm["_filename"], "예정"))
    for fm in published:
        all_items.append((fm["_pub_time"], fm.get("_category", "기타"), fm["_filename"], "완료"))

    all_items.sort(key=lambda x: x[0])

    by_date = defaultdict(list)
    for dt, cat, fname, status in all_items:
        by_date[dt.strftime("%Y-%m-%d")].append((dt, cat, fname, status))

    current = monday
    while current <= next_sunday:
        date_key = current.strftime("%Y-%m-%d")
        weekday = WEEKDAYS_KR[current.weekday()]
        is_today = current.date() == now.date()
        today_mark = " <<" if is_today else ""

        items = by_date.get(date_key, [])
        if items:
            for dt, cat, fname, status in items:
                mark = "[v]" if status == "완료" else "[ ]"
                fname_short = fname.replace(".md", "")
                print(f"  {current.strftime('%m/%d')} ({weekday}){today_mark} {dt.strftime('%H:%M')} {mark} [{cat}] {fname_short}")
        else:
            print(f"  {current.strftime('%m/%d')} ({weekday}){today_mark} -- 비어 있음 --")

        current += timedelta(days=1)

    print()
    print(f"미배정 리뷰완료: {len(unscheduled)}개")
    if unscheduled:
        print("  팁: python3 calendar_scheduler.py 로 자동 배정하세요.")


def main():
    if "--calendar" in sys.argv:
        cmd_calendar()
    elif "--preview" in sys.argv:
        cmd_schedule(preview=True)
    else:
        cmd_schedule(preview=False)


if __name__ == "__main__":
    main()
