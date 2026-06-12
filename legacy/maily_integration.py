"""Maily (maily.so) API 연동 모듈 - Dream_Grow 구독자/뉴스레터 관리

Maily API를 통해 구독자 목록 다운로드, 뉴스레터 목록 조회,
자동화 이메일 트리거 등을 수행합니다.

사용법:
  python3 maily_integration.py --subscribers          # 구독자 CSV 다운로드
  python3 maily_integration.py --newsletters          # 발행된 뉴스레터 목록
  python3 maily_integration.py --export               # 구독자 이메일 목록 내보내기
  python3 maily_integration.py --trigger EXT_ID EMAIL # 자동화 이메일 트리거
  python3 maily_integration.py --stats                # 구독자 성장 요약

환경 변수 (.env):
  MAILY_API_TOKEN  — Maily API 인증 토큰
  MAILY_CIRCLE_SLUG — 서클 슬러그 (기본값: grow.circle)
"""
import argparse
import csv
import os
import sys
import time
from collections import Counter
from datetime import datetime

import requests
from dotenv import load_dotenv

# .env 로드 (content-automation/ 기준)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BASE_URL = "https://api.maily.so"
API_TOKEN = os.getenv("MAILY_API_TOKEN", "")
CIRCLE_SLUG = os.getenv("MAILY_CIRCLE_SLUG", "grow.circle")

# 출력 폴더
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _headers() -> dict:
    """인증 헤더를 반환합니다."""
    if not API_TOKEN:
        print("[오류] MAILY_API_TOKEN이 .env에 설정되지 않았습니다.")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }


def _api_get(endpoint: str, params: dict = None) -> dict:
    """GET 요청을 보내고 JSON을 반환합니다. 에러 시 종료."""
    url = f"{BASE_URL}/api/{CIRCLE_SLUG}/{endpoint}"
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"[API 오류] {resp.status_code}: {resp.text[:200]}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[네트워크 오류] {e}")
        sys.exit(1)


def _api_post(endpoint: str, data: dict = None) -> dict:
    """POST 요청을 보내고 JSON을 반환합니다."""
    url = f"{BASE_URL}/api/{CIRCLE_SLUG}/{endpoint}"
    try:
        resp = requests.post(url, headers=_headers(), json=data or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"[API 오류] {resp.status_code}: {resp.text[:200]}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[네트워크 오류] {e}")
        sys.exit(1)


# ── 구독자 전체 조회 (페이지네이션 처리) ──


def fetch_all_subscribers() -> list:
    """모든 구독자를 페이지네이션하여 가져옵니다.

    Maily API는 한 페이지당 최대 100명을 반환합니다.
    rate limit(20 req/s)을 고려해 페이지 간 0.1초 대기합니다.
    """
    all_subs = []
    page = 1
    while True:
        data = _api_get("subscriptions.json", params={"page": page})

        # 응답 구조: 구독자 배열 또는 {'subscriptions': [...]} 형태
        subs = data if isinstance(data, list) else data.get("subscriptions", [])

        if not subs:
            break

        all_subs.extend(subs)
        print(f"  페이지 {page}: {len(subs)}명 로드 (누적 {len(all_subs)}명)")

        # 100명 미만이면 마지막 페이지
        if len(subs) < 100:
            break

        page += 1
        time.sleep(0.1)  # rate limit 방지

    return all_subs


# ── 명령: --subscribers ──


def cmd_subscribers():
    """구독자 목록을 CSV로 다운로드합니다."""
    print("구독자 목록을 가져오는 중...")
    subs = fetch_all_subscribers()

    if not subs:
        print("구독자가 없습니다.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(OUTPUT_DIR, f"maily_subscribers_{today}.csv")

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["이름", "이메일", "구독일", "상태"])
        for s in subs:
            name = s.get("name", s.get("display_name", ""))
            email = s.get("email", "")
            # 구독일 필드: subscribed_at, created_at 등 API 응답에 따라 조정
            subscribed = s.get("subscribed_at", s.get("created_at", ""))
            status = s.get("status", s.get("state", "active"))
            writer.writerow([name, email, subscribed, status])

    print(f"\n총 {len(subs)}명의 구독자를 저장했습니다.")
    print(f"파일: {filepath}")


# ── 명령: --newsletters ──


def cmd_newsletters():
    """발행된 뉴스레터 목록과 통계를 조회합니다."""
    print("뉴스레터 목록을 가져오는 중...")

    # 발행된 뉴스레터 조회
    data = _api_get("notes.json", params={
        "status": "published",
        "order_by": "published_at",
    })

    notes = data if isinstance(data, list) else data.get("notes", [])

    if not notes:
        print("발행된 뉴스레터가 없습니다.")
        return

    print(f"\n--- 발행된 뉴스레터 ({len(notes)}개) ---\n")
    print(f"{'번호':>4}  {'발행일':<12}  {'조회수':>6}  {'전달':>6}  {'제목'}")
    print("-" * 80)

    for i, note in enumerate(notes, 1):
        title = note.get("title", note.get("subject", "제목 없음"))[:40]
        published = note.get("published_at", "")[:10]
        views = note.get("views_count", note.get("views", "-"))
        delivered = note.get("delivered_count", note.get("delivered", "-"))
        posting_type = note.get("posting_type", "")

        print(f"{i:>4}  {published:<12}  {str(views):>6}  {str(delivered):>6}  {title}")

    # 요약
    total_views = sum(
        n.get("views_count", n.get("views", 0)) or 0 for n in notes
    )
    print(f"\n총 뉴스레터: {len(notes)}개")
    print(f"총 조회수: {total_views}")


# ── 명령: --export ──


def cmd_export():
    """구독자 이메일을 텍스트 파일로 내보냅니다 (서비스 이전용)."""
    print("구독자 이메일을 내보내는 중...")
    subs = fetch_all_subscribers()

    if not subs:
        print("구독자가 없습니다.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    # CSV 형식 (이름, 이메일) - 대부분의 이메일 서비스에서 가져오기 가능
    filepath = os.path.join(OUTPUT_DIR, f"maily_export_{today}.csv")
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["email", "name", "subscribed_at"])
        for s in subs:
            email = s.get("email", "")
            name = s.get("name", s.get("display_name", ""))
            subscribed = s.get("subscribed_at", s.get("created_at", ""))
            if email:  # 이메일이 있는 구독자만
                writer.writerow([email, name, subscribed])

    active_count = sum(
        1 for s in subs
        if s.get("email") and s.get("status", s.get("state", "active")) == "active"
    )
    print(f"\n총 {len(subs)}명 중 이메일 있는 구독자를 내보냈습니다.")
    print(f"활성 구독자 (추정): {active_count}명")
    print(f"파일: {filepath}")
    print("이 파일은 Beehiiv, ConvertKit, Substack 등에서 가져오기 가능합니다.")


# ── 명령: --trigger ──


def cmd_trigger(ext_id: str, email: str):
    """특정 구독자에게 자동화 이메일을 트리거합니다.

    Args:
        ext_id: 자동화 이메일의 ext_id (Maily 대시보드에서 확인)
        email: 수신자 이메일 주소
    """
    print(f"자동화 이메일 트리거: {ext_id} -> {email}")

    endpoint = f"automated_emails/{ext_id}/trigger"
    data = {"email": email}

    result = _api_post(endpoint, data)

    print(f"트리거 완료: {result}")


# ── 명령: --stats ──


def cmd_stats():
    """구독자 성장 요약 통계를 보여줍니다."""
    print("구독자 통계를 분석하는 중...")
    subs = fetch_all_subscribers()

    if not subs:
        print("구독자가 없습니다.")
        return

    total = len(subs)

    # 상태별 집계
    status_counts = Counter()
    for s in subs:
        status = s.get("status", s.get("state", "active"))
        status_counts[status] += 1

    # 월별 구독자 증가 추이
    monthly = Counter()
    for s in subs:
        date_str = s.get("subscribed_at", s.get("created_at", ""))
        if date_str and len(date_str) >= 7:
            # "2026-04-12T..." 또는 "2026-04-12" 형태
            month_key = date_str[:7]  # YYYY-MM
            monthly[month_key] += 1

    print(f"\n--- 구독자 성장 요약 ---\n")
    print(f"총 구독자: {total}명")
    print()

    # 상태별
    print("상태별:")
    for status, count in status_counts.most_common():
        pct = count / total * 100
        print(f"  {status}: {count}명 ({pct:.1f}%)")

    # 월별 추이
    if monthly:
        print(f"\n월별 신규 구독자:")
        for month in sorted(monthly.keys()):
            bar = "#" * min(monthly[month], 50)  # 시각화 바
            print(f"  {month}: {monthly[month]:>4}명 {bar}")

    # 최근 7일, 30일 신규
    from datetime import timedelta
    now = datetime.now()
    recent_7d = 0
    recent_30d = 0
    for s in subs:
        date_str = s.get("subscribed_at", s.get("created_at", ""))
        if not date_str:
            continue
        try:
            # ISO 8601 파싱
            sub_date = datetime.fromisoformat(date_str.replace("Z", "+00:00").split("+")[0])
            delta = (now - sub_date).days
            if delta <= 7:
                recent_7d += 1
            if delta <= 30:
                recent_30d += 1
        except (ValueError, TypeError):
            continue

    print(f"\n최근 7일 신규: {recent_7d}명")
    print(f"최근 30일 신규: {recent_30d}명")
    if recent_30d > 0:
        daily_avg = recent_30d / 30
        print(f"일 평균 신규 (30일): {daily_avg:.1f}명")


# ── CLI 진입점 ──


def main():
    parser = argparse.ArgumentParser(
        description="Maily API 연동 - Dream_Grow 구독자/뉴스레터 관리",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python3 maily_integration.py --subscribers
  python3 maily_integration.py --newsletters
  python3 maily_integration.py --export
  python3 maily_integration.py --trigger abc123 user@example.com
  python3 maily_integration.py --stats
        """,
    )
    parser.add_argument("--subscribers", action="store_true",
                        help="구독자 목록을 CSV로 다운로드")
    parser.add_argument("--newsletters", action="store_true",
                        help="발행된 뉴스레터 목록과 통계 조회")
    parser.add_argument("--export", action="store_true",
                        help="구독자 이메일을 내보내기 (서비스 이전용)")
    parser.add_argument("--trigger", nargs=2, metavar=("EXT_ID", "EMAIL"),
                        help="자동화 이메일 트리거")
    parser.add_argument("--stats", action="store_true",
                        help="구독자 성장 요약 통계")

    args = parser.parse_args()

    # 인수가 없으면 도움말 출력
    if not any([args.subscribers, args.newsletters, args.export,
                args.trigger, args.stats]):
        parser.print_help()
        return

    if args.subscribers:
        cmd_subscribers()
    elif args.newsletters:
        cmd_newsletters()
    elif args.export:
        cmd_export()
    elif args.trigger:
        cmd_trigger(args.trigger[0], args.trigger[1])
    elif args.stats:
        cmd_stats()


if __name__ == "__main__":
    main()
