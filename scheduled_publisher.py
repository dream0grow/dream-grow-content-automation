"""발행시간 기반 Threads 자동 게시기

매시간 cron으로 실행되어:
1. 05 리뷰/완료/ 에서 '발행시간'이 지정된 파일 스캔
2. 현재 시간이 발행시간을 지났으면 Threads API로 발행
3. frontmatter 상태를 '발행완료'로 변경
4. 64 발행완료/ 폴더로 이동
5. 발행 기록 저장

사용법:
  python3 scheduled_publisher.py             # 발행 시간 도달한 것만 발행
  python3 scheduled_publisher.py --dry-run   # 미리보기
  python3 scheduled_publisher.py --list      # 발행 예정 목록
"""
import os
import re
import sys
import shutil
from datetime import datetime

SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
REVIEW_DONE_DIR = os.path.join(SNS_SYSTEM, "05 리뷰/완료")
PUBLISHED_DIR = os.path.join(SNS_SYSTEM, "06 제작/64 발행완료")
PUBLISH_LOG_DIR = os.path.join(SNS_SYSTEM, "07 운영/61 성과 기록")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()


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


def find_scheduled_files() -> list:
    """발행시간이 지정된 리뷰완료 파일을 찾습니다."""
    scheduled = []
    if not os.path.isdir(REVIEW_DONE_DIR):
        return scheduled

    for fname in os.listdir(REVIEW_DONE_DIR):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(REVIEW_DONE_DIR, fname)
        fm = parse_frontmatter(filepath)
        pub_time = parse_publish_time(fm.get("발행시간", ""))
        if pub_time:
            fm["_pub_time"] = pub_time
            scheduled.append(fm)

    return sorted(scheduled, key=lambda x: x["_pub_time"])


def publish_file(fm: dict, dry_run: bool = False) -> bool:
    """파일을 Threads에 발행합니다."""
    filepath = fm["_filepath"]
    filename = fm["_filename"]
    pub_time = fm["_pub_time"]

    print(f"  발행: {filename} (예정: {pub_time.strftime('%m/%d %H:%M')})")

    if dry_run:
        print(f"    [DRY RUN] 실제 발행하지 않음")
        return True

    # Threads API 발행
    from threads_publisher import parse_thread_file, publish_to_threads
    from threads_publisher import update_frontmatter_status, save_publish_log

    parsed = parse_thread_file(filepath)
    results = publish_to_threads(parsed["posts"])

    if not results:
        print(f"    발행 실패 (API 미설정 또는 오류)")
        return False

    # frontmatter 상태 업데이트
    update_frontmatter_status(filepath, "발행완료", results)

    # 64 발행완료/로 이동
    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    dest = os.path.join(PUBLISHED_DIR, filename)
    shutil.move(filepath, dest)
    print(f"    이동: → 64 발행완료/{filename}")

    # 발행 기록
    save_publish_log(filename, len(parsed["posts"]), results)

    return True


def list_scheduled():
    """발행 예정 목록을 보여줍니다."""
    files = find_scheduled_files()
    now = datetime.now()

    print(f"\n--- 발행 예정 ({len(files)}개) ---\n")
    if not files:
        print("발행 예정 파일이 없습니다.")
        print("팁: 05 리뷰/완료/ 에서 frontmatter 발행시간을 지정하세요.")
        print("  예: 발행시간: 2026-04-12 09:00")
        return

    for fm in files:
        pub_time = fm["_pub_time"]
        status = "지남" if pub_time <= now else f"{(pub_time - now).total_seconds() / 3600:.1f}시간 후"
        print(f"  {pub_time.strftime('%m/%d %H:%M')} | {fm['_filename']} | {status}")


def main():
    if "--list" in sys.argv:
        list_scheduled()
        return

    dry_run = "--dry-run" in sys.argv
    now = datetime.now()

    print(f"[{now.strftime('%Y-%m-%d %H:%M')}] 발행 스케줄 체크")

    files = find_scheduled_files()
    due = [f for f in files if f["_pub_time"] <= now]

    if not due:
        print(f"  발행 대상 없음 (예정: {len(files)}개)")
        return

    print(f"  발행 대상: {len(due)}개\n")

    success = 0
    for fm in due:
        if publish_file(fm, dry_run=dry_run):
            success += 1

    print(f"\n완료: {success}/{len(due)}개 발행")


if __name__ == "__main__":
    main()
