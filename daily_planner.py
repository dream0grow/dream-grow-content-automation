"""오늘 할 일 정리 - Google Calendar 연동"""
import os
import pickle
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import claude_client; claude_client.patch_anthropic()
import anthropic

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_calendar_service():
    """Google Calendar API 서비스를 인증하고 반환합니다."""
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                print("⚠️  credentials.json 파일이 없습니다!")
                print()
                print("설정 방법:")
                print("1. https://console.cloud.google.com/ 접속")
                print("2. 프로젝트 생성 → API 라이브러리 → Google Calendar API 활성화")
                print("3. 사용자 인증 정보 → OAuth 2.0 클라이언트 ID 만들기")
                print("   (애플리케이션 유형: '데스크톱 앱')")
                print("4. 다운로드한 JSON 파일을 이 폴더에 credentials.json으로 저장")
                return None
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("calendar", "v3", credentials=creds)


def get_today_events(service) -> list[dict]:
    """오늘의 캘린더 이벤트를 가져옵니다."""
    now = datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start_of_day.isoformat() + "Z",
            timeMax=end_of_day.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return events_result.get("items", [])


def format_events(events: list[dict]) -> str:
    """이벤트 목록을 읽기 좋은 텍스트로 변환합니다."""
    if not events:
        return "오늘 캘린더에 등록된 일정이 없습니다."

    lines = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        if "T" in start:
            time_str = datetime.fromisoformat(start).strftime("%H:%M")
        else:
            time_str = "종일"
        summary = event.get("summary", "(제목 없음)")
        lines.append(f"  - {time_str} | {summary}")
    return "\n".join(lines)


def generate_daily_plan(events_text: str) -> str:
    """AI가 오늘 할 일을 정리하고 우선순위를 제안합니다."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "여기에_API_키를_붙여넣으세요":
        return f"📅 오늘의 일정:\n{events_text}\n\n(AI 분석을 위해 .env에 ANTHROPIC_API_KEY를 설정하세요)"

    client = anthropic.Anthropic(api_key=api_key)
    today = datetime.now().strftime("%Y년 %m월 %d일 %A")

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": f"""오늘은 {today}입니다.

오늘의 캘린더 일정:
{events_text}

위 일정을 바탕으로:
1. 오늘 할 일을 시간순으로 정리해주세요
2. 일정 사이 빈 시간에 할 수 있는 작업을 제안해주세요
3. 가장 중요한 일 3가지를 뽑아주세요
4. 간단한 오늘의 한마디를 덧붙여주세요

깔끔하게 정리해주세요.""",
            }
        ],
    )
    return message.content[0].text


def main():
    print("📅 오늘 할 일 정리기\n")

    service = get_calendar_service()
    if not service:
        print("\nGoogle Calendar 연동 없이 수동 모드로 실행합니다.")
        events_text = input("오늘 할 일을 쉼표로 구분해서 입력하세요: ")
        events_text = "\n".join(f"  - {item.strip()}" for item in events_text.split(","))
    else:
        events = get_today_events(service)
        events_text = format_events(events)
        print(f"캘린더에서 {len(events)}개 일정을 가져왔습니다.\n")

    plan = generate_daily_plan(events_text)
    print(plan)

    # 결과 저장
    os.makedirs("output", exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    filename = f"output/daily_plan_{today_str}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# 오늘의 계획 - {datetime.now().strftime('%Y년 %m월 %d일')}\n\n")
        f.write(plan)
    print(f"\n저장 완료: {filename}")


if __name__ == "__main__":
    main()
