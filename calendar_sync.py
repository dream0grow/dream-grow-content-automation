"""발행 캘린더 → Google Calendar 동기화

05 리뷰/대기/에 발행시간이 지정된 콘텐츠를 Google Calendar에 등록합니다.

사용법:
  python3 calendar_sync.py              # 발행 예정 → 캘린더 등록
  python3 calendar_sync.py --list       # 등록될 이벤트 미리보기
  python3 calendar_sync.py --clean      # 지난 DreamGrow 이벤트 정리
"""
import os
import re
import sys
import pickle
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
REVIEW_WAIT = os.path.join(SNS_SYSTEM, "05 리뷰", "대기")
REVIEW_DONE = os.path.join(SNS_SYSTEM, "05 리뷰", "완료")

CALENDAR_ID = "primary"
EVENT_PREFIX = "[DG]"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def get_calendar_service():
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    token_path = os.path.join(os.path.dirname(__file__), "token.pickle")
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")

    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                print("credentials.json 필요")
                print("1. https://console.cloud.google.com/")
                print("2. Google Calendar API 활성화")
                print("3. OAuth 2.0 클라이언트 → credentials.json 다운로드")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build("calendar", "v3", credentials=creds)


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
    fm["_filepath"] = filepath
    fm["_filename"] = os.path.basename(filepath)
    return fm


def parse_publish_time(time_str: str) -> datetime | None:
    if not time_str or time_str.strip() == "":
        return None
    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"]:
        try:
            return datetime.strptime(time_str.strip(), fmt)
        except ValueError:
            continue
    return None


def find_scheduled_content() -> list:
    """발행시간이 지정된 콘텐츠를 찾습니다."""
    scheduled = []
    for folder in [REVIEW_WAIT, REVIEW_DONE]:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.endswith(".md"):
                continue
            filepath = os.path.join(folder, fname)
            fm = parse_frontmatter(filepath)
            pub_time = parse_publish_time(fm.get("발행시간", ""))
            if pub_time and pub_time > datetime.now():
                fm["_pub_time"] = pub_time
                fm["_folder"] = os.path.basename(folder)
                scheduled.append(fm)
    return sorted(scheduled, key=lambda x: x["_pub_time"])


def create_event(service, fm: dict) -> str | None:
    """Google Calendar에 발행 이벤트를 등록합니다."""
    pub_time = fm["_pub_time"]
    topic = fm.get("주제", fm["_filename"].replace(".md", ""))
    category = fm.get("카테고리", "")
    channel = fm.get("채널", "thread")

    summary = f"{EVENT_PREFIX} {topic}"
    if category:
        summary = f"{EVENT_PREFIX} [{category}] {topic}"

    description = (
        f"채널: {channel}\n"
        f"상태: {fm.get('상태', '')}\n"
        f"파일: {fm['_filename']}\n"
        f"위치: 05 리뷰/{fm['_folder']}/\n"
        f"\nDream_Grow 자동 발행 예정"
    )

    event = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": pub_time.isoformat(),
            "timeZone": "Asia/Seoul",
        },
        "end": {
            "dateTime": (pub_time + timedelta(minutes=15)).isoformat(),
            "timeZone": "Asia/Seoul",
        },
        "colorId": "9",
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
            ],
        },
    }

    existing = find_existing_event(service, pub_time, topic)
    if existing:
        return None

    result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return result.get("id")


def find_existing_event(service, pub_time: datetime, topic: str) -> bool:
    """이미 등록된 이벤트인지 확인합니다."""
    time_min = (pub_time - timedelta(minutes=5)).isoformat() + "+09:00"
    time_max = (pub_time + timedelta(minutes=20)).isoformat() + "+09:00"

    events = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            q=EVENT_PREFIX,
            singleEvents=True,
        )
        .execute()
    )

    for event in events.get("items", []):
        if topic[:20] in event.get("summary", ""):
            return True
    return False


def sync_to_calendar():
    """발행 예정 콘텐츠를 Google Calendar에 동기화합니다."""
    service = get_calendar_service()
    if not service:
        return

    scheduled = find_scheduled_content()
    if not scheduled:
        print("발행시간이 지정된 콘텐츠가 없습니다.")
        return

    print(f"발행 예정: {len(scheduled)}개\n")

    created = 0
    skipped = 0
    for fm in scheduled:
        event_id = create_event(service, fm)
        if event_id:
            print(f"  등록: {fm['_pub_time'].strftime('%m/%d %H:%M')} | {fm['_filename'][:40]}")
            created += 1
        else:
            skipped += 1

    print(f"\n결과: 등록 {created}개, 중복 건너뜀 {skipped}개")


def list_preview():
    """등록될 이벤트를 미리봅니다."""
    scheduled = find_scheduled_content()
    print(f"\n--- 캘린더 등록 대상 ({len(scheduled)}개) ---\n")
    if not scheduled:
        print("발행시간이 지정된 콘텐츠가 없습니다.")
        return
    for fm in scheduled:
        topic = fm.get("주제", fm["_filename"])
        print(f"  {fm['_pub_time'].strftime('%m/%d %H:%M')} | {topic[:40]} | {fm['_folder']}")


def main():
    if "--list" in sys.argv:
        list_preview()
        return

    if "--clean" in sys.argv:
        service = get_calendar_service()
        if not service:
            return
        now = datetime.now()
        week_ago = (now - timedelta(days=7)).isoformat() + "+09:00"
        events = (
            service.events()
            .list(calendarId=CALENDAR_ID, timeMin=week_ago, q=EVENT_PREFIX, singleEvents=True)
            .execute()
        )
        items = events.get("items", [])
        print(f"최근 7일 DreamGrow 이벤트: {len(items)}개")
        return

    sync_to_calendar()


if __name__ == "__main__":
    main()
