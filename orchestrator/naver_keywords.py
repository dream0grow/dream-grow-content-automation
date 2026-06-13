"""네이버 검색광고 API - 키워드 도구로 실제 검색량/경쟁도 조회

키워드 점수화 단계에서 Claude가 뽑은 후보에 실측 데이터를 붙인다.
NAVER_AD_API_KEY / NAVER_AD_SECRET / NAVER_AD_CUSTOMER_ID 미설정 시 조용히 건너뛴다.

키 발급: searchad.naver.com → 도구 → API 사용 관리
"""
import base64
import hashlib
import hmac
import os
import time

import requests

BASE_URL = "https://api.searchad.naver.com"
API_KEY = os.getenv("NAVER_AD_API_KEY", "")
API_SECRET = os.getenv("NAVER_AD_SECRET", "")
CUSTOMER_ID = os.getenv("NAVER_AD_CUSTOMER_ID", "")


def available() -> bool:
    return bool(API_KEY and API_SECRET and CUSTOMER_ID)


def _headers(method: str, path: str) -> dict:
    timestamp = str(round(time.time() * 1000))
    message = f"{timestamp}.{method}.{path}"
    signature = base64.b64encode(
        hmac.new(API_SECRET.encode(), message.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": API_KEY,
        "X-Customer": CUSTOMER_ID,
        "X-Signature": signature,
    }


def _to_int(value) -> int:
    """'< 10' 같은 문자열 응답을 정수로 정규화한다."""
    if isinstance(value, int):
        return value
    try:
        return int(str(value).replace("<", "").strip())
    except (ValueError, TypeError):
        return 0


def fetch_volumes(keywords: list[str]) -> dict[str, dict]:
    """키워드별 월간 검색량(PC/모바일)과 경쟁도를 조회한다.

    Returns: {원본 키워드: {"pc": int, "mobile": int, "total": int, "comp": str}}
    hintKeywords는 호출당 최대 5개, 공백 제거 필요.
    """
    if not available():
        return {}
    path = "/keywordstool"
    normalized = {k.replace(" ", ""): k for k in keywords if k.strip()}
    result: dict[str, dict] = {}
    hints = list(normalized.keys())
    for i in range(0, len(hints), 5):
        batch = hints[i:i + 5]
        resp = requests.get(
            f"{BASE_URL}{path}",
            headers=_headers("GET", path),
            params={"hintKeywords": ",".join(batch), "showDetail": "1"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"네이버 키워드도구 오류 {resp.status_code}: {resp.text[:200]}")
        for item in resp.json().get("keywordList", []):
            rel = item.get("relKeyword", "")
            if rel in normalized and normalized[rel] not in result:
                pc = _to_int(item.get("monthlyPcQcCnt"))
                mobile = _to_int(item.get("monthlyMobileQcCnt"))
                result[normalized[rel]] = {
                    "pc": pc,
                    "mobile": mobile,
                    "total": pc + mobile,
                    "comp": item.get("compIdx", "-"),
                }
        if i + 5 < len(hints):
            time.sleep(0.5)
    return result


def format_volume(vol: dict | None) -> str:
    if not vol:
        return "검색량 데이터 없음"
    return f"월 검색량 {vol['total']:,} (PC {vol['pc']:,} / 모바일 {vol['mobile']:,}), 경쟁도 {vol['comp']}"
