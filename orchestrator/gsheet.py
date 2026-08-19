"""구글 시트 직접 읽기/쓰기 — 썸네일 벤치마킹 시트 연동.

인증: 구글 서비스 계정(Service Account) JSON을 환경변수 `GSHEET_SA_JSON`
(GitHub Secret)으로 받는다. 시트는 서비스 계정 이메일(client_email)에
"편집자"로 공유돼 있어야 한다.

시트 지정: `DG_THUMB_SHEET_ID`(스프레드시트 ID), `DG_THUMB_SHEET_GID`(탭 gid).
기본값은 사용자의 벤치마킹 시트(분석 탭).

의존성: google-auth (토큰 발급), requests (REST 호출).
"""
import json
import os
import urllib.parse

import requests

API = "https://sheets.googleapis.com/v4/spreadsheets"

SHEET_ID_DEFAULT = "1Vy6_9gn3nNovUUdTqYOmkuc4ZamNbj-5tlvZ1fHmN24"
SHEET_GID_DEFAULT = "787785781"


def sheet_id() -> str:
    return os.getenv("DG_THUMB_SHEET_ID", "").strip() or SHEET_ID_DEFAULT


def sheet_gid() -> int:
    try:
        return int(os.getenv("DG_THUMB_SHEET_GID", "").strip() or SHEET_GID_DEFAULT)
    except ValueError:
        return int(SHEET_GID_DEFAULT)


def available() -> bool:
    return bool(os.getenv("GSHEET_SA_JSON", "").strip())


def _token() -> str:
    """서비스 계정 JSON으로 OAuth 액세스 토큰을 발급한다."""
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    info = json.loads(os.environ["GSHEET_SA_JSON"])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    creds.refresh(Request())
    return creds.token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


def resolve_title(gid: int | None = None) -> str:
    """gid → 탭 이름. 범위 주소(A1 notation)에 탭 이름이 필요하다."""
    gid = sheet_gid() if gid is None else gid
    r = requests.get(f"{API}/{sheet_id()}", headers=_headers(),
                     params={"fields": "sheets.properties"}, timeout=30)
    r.raise_for_status()
    for s in r.json().get("sheets", []):
        p = s.get("properties", {})
        if p.get("sheetId") == gid:
            return p.get("title", "")
    raise RuntimeError(f"gid={gid} 탭을 찾을 수 없습니다")


def _quote_range(title: str, a1: str) -> str:
    return urllib.parse.quote(f"'{title}'!{a1}", safe="")


def read(a1: str, title: str | None = None) -> list[list[str]]:
    """범위의 셀 값을 2차원 리스트로 읽는다 (빈 행 뒤는 잘려 올 수 있음)."""
    title = title or resolve_title()
    r = requests.get(f"{API}/{sheet_id()}/values/{_quote_range(title, a1)}",
                     headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json().get("values", [])


def update(a1: str, values: list[list], title: str | None = None):
    """범위에 값을 쓴다 (덮어쓰기)."""
    title = title or resolve_title()
    r = requests.put(
        f"{API}/{sheet_id()}/values/{_quote_range(title, a1)}",
        headers=_headers(), params={"valueInputOption": "USER_ENTERED"},
        json={"values": values}, timeout=60)
    r.raise_for_status()
    return r.json()


def append(a1: str, values: list[list], title: str | None = None):
    """표 아래에 행을 추가한다 (기존 데이터 다음 빈 행부터)."""
    title = title or resolve_title()
    r = requests.post(
        f"{API}/{sheet_id()}/values/{_quote_range(title, a1)}:append",
        headers=_headers(),
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"values": values}, timeout=60)
    r.raise_for_status()
    return r.json()
