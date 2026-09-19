"""풀링 영상 만들기 탭 — 열 위치 해석 + B/C(조회수·구독자) 셀 문자열 규칙.

2026-09-19 개편: A(날짜 및 키워드)와 영상 URL 사이에 두 열이 들어갔다.
  B 조회수 (게시일) : "441.1만회\\n게시 2019-08-09\\n검색일 기준 2,597일 · 일평균 1,698회"
  C 구독자 수       : "37.1만명\\n조회/구독 11.9배"
열 문자를 코드에 박지 말고 헤더 행을 읽어 이름으로 위치를 잡는다(resolve_pool_columns).
viewtrap_keywords(새 행 추가)·pool_enrich(빈 칸 채우기)·thumbnail/youtube_body(분석)가 같은 규칙을 쓴다.
"""
from __future__ import annotations

import re
from datetime import date, datetime

# 헤더 이름(공백 제거, startswith) → 키. 위에서부터 우선.
POOL_HEADER_PATTERNS: list[tuple[str, str]] = [
    ("date_kw", "날짜"),
    ("views", "조회수"),
    ("subs", "구독자"),
    ("url", "영상URL"),
    ("thumb", "썸네일이미지"),
    ("title", "영상제목"),
    ("my_keyword", "내가만들"),
]
# 헤더를 못 읽었을 때의 폴백 (2026-09-19 배치)
POOL_COL_DEFAULT = {"date_kw": 0, "views": 1, "subs": 2, "url": 3, "thumb": 4, "title": 5,
                    "my_keyword": 13}


def resolve_pool_columns(header: list[str]) -> dict[str, int]:
    cols = dict(POOL_COL_DEFAULT)
    found: set[str] = set()
    for idx, cell in enumerate(header or []):
        name = re.sub(r"\s+", "", str(cell or ""))
        if not name:
            continue
        for key, pat in POOL_HEADER_PATTERNS:
            if key not in found and name.startswith(pat):
                cols[key] = idx
                found.add(key)
                break
    return cols


def col_letter(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{11})", url or "")
    if m:
        return m.group(1)
    return url.strip() if re.fullmatch(r"[\w-]{11}", (url or "").strip()) else ""


def man(n) -> str:
    """12345678 → '1234.6만', 3774006 → '377.4만', 8637 → '8,637'."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    if n >= 1e8:
        s = f"{n / 1e8:.2f}".rstrip("0").rstrip(".")
        return f"{s}억"
    if n >= 1e4:
        s = f"{n / 1e4:.1f}".rstrip("0").rstrip(".")
        return f"{s}만"
    return f"{int(round(n)):,}"


def parse_date(s) -> date | None:
    """'2019-08-09T…', '2026.9.18.', '2025. 3. 11', datetime → date."""
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    m = re.search(r"(\d{4})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})", str(s or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def search_date_from_label(label: str) -> date | None:
    """A열 '2026.9.18. \\n\\n장난감' → 2026-09-18."""
    return parse_date(label)


def views_cell(views, published_at, search_date=None) -> str:
    pub = parse_date(published_at)
    sd = parse_date(search_date) if search_date else None
    lines = [f"{man(views)}회"]
    if pub:
        lines.append(f"게시 {pub.isoformat()}")
    if pub and sd:
        days = max(1, (sd - pub).days)
        try:
            per_day = float(views) / days
        except (TypeError, ValueError):
            per_day = 0
        lines.append(f"검색일 기준 {days:,}일 · 일평균 {int(round(per_day)):,}회")
    return "\n".join(lines)


def subs_cell(subs, views=None) -> str:
    line = f"{man(subs)}명"
    try:
        ratio = float(views) / float(subs)
    except (TypeError, ValueError, ZeroDivisionError):
        ratio = None
    if ratio is not None:
        r = f"{ratio:.0f}" if ratio >= 100 else f"{ratio:.1f}"
        line += f"\n조회/구독 {r}배"
    return line


def parse_views_cell(text: str) -> int | None:
    """B셀 첫 줄 '441.1만회' → 4411000 (검증·정렬용)."""
    m = re.match(r"\s*([\d,.]+)\s*(억|만)?", str(text or ""))
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    return int(n * {"억": 1e8, "만": 1e4}.get(m.group(2) or "", 1))
