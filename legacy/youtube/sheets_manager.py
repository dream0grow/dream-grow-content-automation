"""Google Sheets 트리거 스캔 + 부트스트랩 + 성과/인사이트 기록.

사용 흐름:
1. bootstrap(): 빈 스프레드시트에 SC_트리거/SC_성과/SC_인사이트 탭 자동 생성
2. scan_trigger(): 상태가 '대기'인 행을 찾아 파이프라인 트리거
3. record_metrics(): 영상 성과를 SC_성과 탭에 기록
4. record_insights(): 주간 AI 분석을 SC_인사이트에 기록
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# ============================================================
# 컬럼 스키마 (순서 중요)
# ============================================================

TRIGGER_HEADERS = [
    "상태",            # A
    "생성일",          # B
    "채널브랜드",      # C  (DG/SM/SC, 기본 SC)
    "분류",            # D
    "핵심키워드",      # E  (사용자 필수 입력)
    "현상",            # F  (AI)
    "고민",            # G  (AI)
    "욕구",            # H  (AI)
    "계획",            # I  (AI)
    "제목_수동",       # J  (사용자 선택)
    "도입부_수동",     # K  (사용자 선택)
    "썸네일_기대",     # L  (AI)
    "썸네일_증거",     # M
    "썸네일_의문",     # N
    "썸네일_공감",     # O
    "최종_썸네일문구", # P
    "논문소스",        # Q
    "제텔카스텐메모",  # R
    "원고경로",        # S
    "MP4경로",         # T
    "youtube_video_id",# U
    "YouTube_URL",     # V
    "에러로그",        # W
]

METRICS_HEADERS = [
    "영상제목", "업로드일", "조회수", "노출수", "CTR(%)",
    "평균시청시간", "시청지속율(%)", "좋아요", "댓글수", "구독전환",
    "댓글핵심정리", "셀프피드백", "사용자피드백", "다음영상방향", "youtube_video_id",
]

INSIGHTS_HEADERS = [
    "주차", "상위영상TOP3", "하위영상BOTTOM3",
    "공통패턴_잘됨", "공통패턴_안됨", "다음주추천주제", "사용자방향",
]


def get_service():
    """Sheets API 서비스 객체 반환. 최초 실행 시 OAuth 플로우 진행."""
    creds = None
    if config.SHEETS_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(config.SHEETS_TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not config.SHEETS_CREDENTIALS.exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials not found at {config.SHEETS_CREDENTIALS}. "
                    "Download OAuth 2.0 client from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.SHEETS_CREDENTIALS), SCOPES
            )
            creds = flow.run_local_server(port=0)
        config.SHEETS_TOKEN.write_text(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def _tab_exists(service, spreadsheet_id: str, title: str) -> bool:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta.get("sheets", []):
        if s.get("properties", {}).get("title") == title:
            return True
    return False


def _add_tab(service, spreadsheet_id: str, title: str, headers: list[str]) -> None:
    """탭 생성 + 헤더 행 입력."""
    body = {
        "requests": [
            {"addSheet": {"properties": {"title": title}}}
        ]
    }
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body=body
    ).execute()
    # 헤더 쓰기
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{title}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers]},
    ).execute()


def bootstrap(spreadsheet_id: str | None = None) -> None:
    """빈 스프레드시트에 3개 탭과 헤더 자동 생성. 이미 있으면 건너뜀."""
    sid = spreadsheet_id or config.YOUTUBE_SPREADSHEET_ID
    service = get_service()

    for title, headers in [
        (config.TAB_TRIGGER, TRIGGER_HEADERS),
        (config.TAB_METRICS, METRICS_HEADERS),
        (config.TAB_INSIGHTS, INSIGHTS_HEADERS),
    ]:
        if _tab_exists(service, sid, title):
            print(f"[skip] 탭 이미 존재: {title}")
            continue
        _add_tab(service, sid, title, headers)
        print(f"[created] 탭 생성: {title}")


def _read_all(service, sid: str, tab: str) -> list[list[str]]:
    result = service.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{tab}!A:Z"
    ).execute()
    return result.get("values", [])


def scan_trigger(spreadsheet_id: str | None = None) -> list[dict[str, Any]]:
    """SC_트리거 탭에서 상태가 '대기'인 행을 반환.

    Returns:
        각 행을 dict로 변환한 리스트. 'row_index'(1-based)와 각 헤더 키 포함.
    """
    sid = spreadsheet_id or config.YOUTUBE_SPREADSHEET_ID
    service = get_service()
    rows = _read_all(service, sid, config.TAB_TRIGGER)

    if not rows or len(rows) < 2:
        return []

    headers = rows[0]
    pending: list[dict[str, Any]] = []
    for i, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        entry: dict[str, Any] = {"row_index": i}
        for j, h in enumerate(headers):
            entry[h] = row[j] if j < len(row) else ""
        if (entry.get("상태") or "").strip() == "대기":
            if (entry.get("핵심키워드") or "").strip():
                pending.append(entry)
    return pending


def update_trigger_row(
    row_index: int,
    updates: dict[str, str],
    spreadsheet_id: str | None = None,
) -> None:
    """트리거 탭의 특정 행에서 주어진 컬럼만 업데이트."""
    sid = spreadsheet_id or config.YOUTUBE_SPREADSHEET_ID
    service = get_service()

    # 각 컬럼별 개별 업데이트 (batchUpdate)
    data = []
    for col_name, value in updates.items():
        if col_name not in TRIGGER_HEADERS:
            continue
        col_idx = TRIGGER_HEADERS.index(col_name)
        col_letter = _col_letter(col_idx)
        data.append({
            "range": f"{config.TAB_TRIGGER}!{col_letter}{row_index}",
            "values": [[value]],
        })

    if not data:
        return

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=sid,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()


def _col_letter(idx: int) -> str:
    """0-based index → A, B, ..., Z, AA."""
    result = ""
    n = idx
    while True:
        result = chr(ord("A") + n % 26) + result
        n = n // 26 - 1
        if n < 0:
            break
    return result


def append_metrics_row(row: dict[str, Any], spreadsheet_id: str | None = None) -> None:
    """SC_성과 탭에 새 행 추가."""
    sid = spreadsheet_id or config.YOUTUBE_SPREADSHEET_ID
    service = get_service()
    values = [row.get(h, "") for h in METRICS_HEADERS]
    service.spreadsheets().values().append(
        spreadsheetId=sid,
        range=f"{config.TAB_METRICS}!A:Z",
        valueInputOption="USER_ENTERED",
        body={"values": [values]},
    ).execute()


def append_insight_row(row: dict[str, Any], spreadsheet_id: str | None = None) -> None:
    """SC_인사이트 탭에 새 행 추가."""
    sid = spreadsheet_id or config.YOUTUBE_SPREADSHEET_ID
    service = get_service()
    values = [row.get(h, "") for h in INSIGHTS_HEADERS]
    service.spreadsheets().values().append(
        spreadsheetId=sid,
        range=f"{config.TAB_INSIGHTS}!A:Z",
        valueInputOption="USER_ENTERED",
        body={"values": [values]},
    ).execute()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "bootstrap":
        bootstrap()
        print("부트스트랩 완료")
    elif len(sys.argv) > 1 and sys.argv[1] == "scan":
        pending = scan_trigger()
        print(f"대기 건수: {len(pending)}")
        for p in pending:
            print(f"  [{p['row_index']}] {p.get('핵심키워드')}")
    else:
        print("Usage: python -m youtube.sheets_manager {bootstrap|scan}")
