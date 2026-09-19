"""뷰트랩 키워드 발굴 → 구글 시트 채점 → 풀링 영상 저장 (무인 실행용).

Aside 세션에서 손으로 검증한 절차(2026-09-18)를 그대로 옮긴 것. 하루 1회 GitHub Actions
(`.github/workflows/viewtrap-keywords.yml`) 또는 로컬/Orca에서 `python3 -m orchestrator.viewtrap_keywords`
로 실행한다. 브라우저 없이 뷰트랩 내부 API와 구글 시트 API만 쓴다.

흐름
  1. `viewtrap_keyword_queue.json`에서 status=pending 키워드를 `--limit`(기본 30)개 꺼낸다.
     이미 시트 C열에 있는 키워드는 `skipped_in_sheet`로 표시하고 건너뛴다.
  2. 뷰트랩 검색 내역에 같은 키워드가 있고 `--max-age-days` 이내면 검색 횟수를 쓰지 않고 재사용,
     아니면 새로 검색(POST request/keyword → round 생성 → 영상 수가 안정될 때까지 폴링).
  3. 지표 계산(시트 열과 1:1):
       F 조회수 합계(만) = Σviews/10000
       G 최근 영상 활발성 = 게시월 히스토그램 마지막 막대/최대 막대 ≥0.55 상, ≥0.25 중, 그 외 하
       H/I 기여도·성과도 normal 이상 비율 = 시트 수식(AB~AK 개수로 계산)
       J 조회수 중앙값, K 구독자수 중앙값 = API viewCount/subscriberCount로 직접 계산
         (뷰트랩 필터 패널의 두 중앙값 라벨은 서로 바뀌어 표시되므로 패널 값을 쓰지 않는다)
       M 결과 = N~S 기준 충족 개수 (시트 수식)
  4. "잠재고객키워드수요(풀링)" 탭(gid 949293824) 첫 빈 행부터 A~AK를 수식 포함으로 쓴다.
  5. 결과 5점 이상 키워드는 쇼츠 제외 조회수 상위 5개를 "풀링 영상 만들기" 탭(gid 787785781)에
     A(날짜+키워드)/B(URL)/C(IMAGE 수식)/D(제목)으로 추가하고 행 높이 150으로 맞춘다.
  6. 큐 파일 갱신 + 텔레그램 요약. 뷰트랩 로그인 만료(HTTP 401/412)면 즉시 알리고 종료한다.

필요 환경변수
  VIEWTRAP_COOKIE   브라우저 DevTools → Network → api.viewtrap.com 요청의 `cookie:` 헤더 값 전체
  GSHEET_SA_JSON    구글 서비스 계정 JSON (orchestrator/gsheet.py와 동일, 시트에 편집자로 공유돼 있어야 함)
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID  (선택) 요약 알림
선택
  DG_VT_SHEET_ID (기본: 벤치마킹 시트), DG_VT_KEYWORD_GID (기본 949293824), DG_VT_POOL_GID (기본 787785781)
  DG_VT_QUEUE (기본: 저장소 루트의 viewtrap_keyword_queue.json)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from orchestrator import gsheet

API = "https://api.viewtrap.com/api/v2"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")
KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).resolve().parent.parent

KEYWORD_GID_DEFAULT = 949293824
POOL_GID_DEFAULT = 787785781
LEVELS = ["매우 나쁨", "나쁨", "보통", "좋음", "매우 좋음"]  # AB..AF / AG..AK 순서


def log(msg: str) -> None:
    print(f"[viewtrap] {msg}", flush=True)


def norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s)).lower()


def kst_date(iso: str | None = None) -> str:
    if iso:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    else:
        dt = datetime.now(timezone.utc)
    return dt.astimezone(KST).strftime("%Y-%m-%d")


def date_cell(ymd: str) -> str:
    """'2026-09-18' → '2026. 9. 18' (시트 ko 로캘이 날짜로 인식하는 형식)."""
    y, m, d = ymd.split("-")
    return f"{y}. {int(m)}. {int(d)}"


# ---------------------------------------------------------------- Viewtrap API
class AuthError(RuntimeError):
    pass


def cookie_expiry(cookie: str) -> datetime | None:
    """VIEWTRAP_COOKIE 안의 `token=` JWT에서 만료 시각(KST)을 꺼낸다. 뷰트랩 세션 토큰은 발급 후 7일짜리다."""
    import base64
    try:
        tok = next(c.strip()[6:] for c in cookie.split(";") if c.strip().startswith("token="))
        payload = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))
        return datetime.fromtimestamp(int(payload["exp"]), KST)
    except Exception:
        return None


class Viewtrap:
    def __init__(self, cookie: str):
        if not cookie.strip():
            raise AuthError("VIEWTRAP_COOKIE 미설정")
        self.s = requests.Session()
        self.s.headers.update({
            "Cookie": cookie.strip(),
            "Origin": "https://app.viewtrap.com",
            "Referer": "https://app.viewtrap.com/video-search",
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
        })

    def _check(self, r: requests.Response) -> dict:
        if r.status_code in (401, 412):
            raise AuthError(f"뷰트랩 인증 실패 HTTP {r.status_code} — VIEWTRAP_COOKIE 갱신 필요")
        r.raise_for_status()
        return r.json()

    def get(self, path: str, **params) -> dict:
        r = self.s.get(f"{API}/{path}", params=params or None, timeout=60)
        return self._check(r)

    def remaining(self) -> int:
        """남은 영상 찾기 횟수 (`km_use_count`는 사용량이 아니라 잔여량이다)."""
        return int(self.get("auth/users")["data"]["user"]["km_use_count"])

    def histories(self) -> list[dict]:
        return self.get("contents/histories/keyword")["data"]["histories"]

    def videos(self, round_no: str) -> dict:
        return self.get("contents/videos", round_no=round_no)["data"]

    def request_search(self, keyword: str) -> None:
        body = {"keyword": urllib.parse.quote(keyword, safe="-_.!~*'()"),
                "lang": "ko", "country": "KR"}
        r = self.s.post(f"{API}/contents/videos/request/keyword", json=body, timeout=60)
        self._check(r)

    def search(self, keyword: str, poll_sec: float = 3.0, max_wait: int = 240) -> tuple[str, dict]:
        """새 검색을 걸고 (round_no, videos data)를 돌려준다. 검색 횟수 1회 차감."""
        self.request_search(keyword)
        round_no = None
        for _ in range(30):
            for h in self.histories()[:3]:
                if norm(h.get("keyword", "")) == norm(keyword):
                    round_no = str(h["round_no"])
                    break
            if round_no:
                break
            time.sleep(2)
        if not round_no:
            raise RuntimeError(f"검색 내역에 round가 생기지 않음: {keyword}")
        prev, stable, data = -1, 0, None
        deadline = time.time() + max_wait
        while time.time() < deadline:
            time.sleep(poll_sec)
            data = self.videos(round_no)
            n = len(data.get("videos", []))
            stable = stable + 1 if (n == prev and n > 0) else 0
            prev = n
            if stable >= 3:
                break
        return round_no, data


# ---------------------------------------------------------------- 지표
def _median(xs: list[float]) -> float:
    return statistics.median(xs) if xs else 0.0


def _round(x: float) -> int:
    """JS Math.round과 같은 반올림(.5 올림) — 시트 기존 값과 맞추기 위함."""
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def compute_metrics(keyword: str, data: dict) -> dict:
    vids = data.get("videos", [])
    n = len(vids)
    views = [float(v.get("viewCount") or 0) for v in vids]
    subs = [float(v.get("subscriberCount") or 0) for v in vids]
    c = [sum(1 for v in vids if v.get("contributionRateStr") == lv) for lv in LEVELS]
    p = [sum(1 for v in vids if v.get("performanceRateStr") == lv) for lv in LEVELS]
    par = (data.get("filter") or {}).get("publishedAtRange") or {}
    vals = par.get("values") or []
    last, mx = (vals[-1], max(vals)) if vals else (0, 1)
    ratio = last / mx if mx else 0
    g = "상" if ratio >= 0.55 else ("중" if ratio >= 0.25 else "하")
    f = _round(sum(views) / 10000)
    med_views, med_subs = _round(_median(views)), _round(_median(subs))
    h = (c[2] + c[3] + c[4]) / n if n else 0
    i = (p[2] + p[3] + p[4]) / n if n else 0
    score = int(f >= 10000) + int(g == "상") + int(h >= 0.3) + int(i >= 0.3) \
        + int(med_views >= 15000) + int(1 < med_subs <= 10000)
    search_dts = [v.get("search_dt") for v in vids if v.get("search_dt")]
    search_date = kst_date(max(search_dts)) if search_dts else kst_date()
    return {"keyword": keyword, "searchDate": search_date, "n": n, "F": f, "G": g,
            "last": last, "max": mx, "H": h, "I": i, "medViews": med_views,
            "medSubs": med_subs, "c": c, "p": p, "score": score}


def yt_suggest(q: str) -> list[str]:
    """YouTube 자동완성 연관검색어 (E열)."""
    try:
        r = requests.get("https://suggestqueries.google.com/complete/search",
                         params={"client": "youtube", "ds": "yt", "hl": "ko", "gl": "kr", "q": q},
                         timeout=15)
        m = re.match(r"^[^(]*\((.*)\)\s*;?\s*$", r.text, re.S)
        if not m:
            return []
        items = json.loads(m.group(1))[1]
        return [x[0] for x in items if x[0] != q][:8]
    except Exception as e:  # 연관검색어는 부가 정보 — 실패해도 진행
        log(f"연관검색어 실패({q}): {e}")
        return []


# ---------------------------------------------------------------- 시트 행
def keyword_row(r: int, m: dict, suggestions: list[str]) -> list:
    """잠재고객키워드수요(풀링) 탭 A~AK (37열) 한 행. 수식은 기존 행과 동일."""
    return [
        date_cell(m["searchDate"]), "", m["keyword"], "", "\n".join(suggestions), m["F"], m["G"],
        f"=(AD{r}+AE{r}+AF{r})/(AB{r}+AC{r}+AD{r}+AE{r}+AF{r})",
        f"=(AI{r}+AJ{r}+AK{r})/(AG{r}+AH{r}+AI{r}+AJ{r}+AK{r})",
        m["medViews"], m["medSubs"], "",
        f'=countif(N{r}:S{r},"Y")',
        f'=if(F{r}>=$V$2,"Y",0)', f'=if(G{r}=$W$2,"Y",0)', f'=if(H{r}>=$X$2,"Y",0)',
        f'=if(I{r}>=$Y$2,"Y",0)', f'=if(J{r}>=$Z$2,"Y",0)', f'=IF(AND(K{r}<=$AA$2,K{r}>1),"Y",0)',
        "", "", "", "", "", "", "", "",
        *m["c"], *m["p"],
    ]


def pool_rows(m: dict, data: dict, top_n: int = 5, exclude_ids: set | None = None) -> list[list]:
    """풀링 영상 만들기 탭 A~D. 쇼츠 제외, 조회수 순."""
    y, mo, d = m["searchDate"].split("-")
    label = f"{y}.{int(mo)}.{int(d)}. \n\n{m['keyword']}"
    vids = [v for v in data.get("videos", []) if not v.get("shorts")
            and v.get("id") and v["id"] not in (exclude_ids or set())]
    vids.sort(key=lambda v: float(v.get("viewCount") or 0), reverse=True)
    return [[label, f"https://www.youtube.com/watch?v={v['id']}",
             f'=IMAGE("https://img.youtube.com/vi/{v["id"]}/hqdefault.jpg")', v.get("title", "")]
            for v in vids[:top_n]]


EDU_RE = re.compile(
    r"아이|자녀|초등|부모|엄마|아빠|학부모|육아|교육|교사|선생님|학생|학교|공부|학습|유아|어린이|아동|훈육|양육|금쪽|오은영|EBS|"
    r"학년|교실|유치원|발달|독서|한글|영어|수학|문해력|학원|입학|성장|심리|상담|자존감|칭찬|습관|아기|딸|아들|형제|가정|암기|단어|시험|성적|뇌|집중",
    re.I)
# 키즈 예능·동요·장난감 리뷰·예능·뉴스·음악 등 "교육·육아 채널"이 아닌 것 (2026-09-18 수작업 선별 결과를 규칙화)
EDU_EXCLUDE_RE = re.compile(
    r"동요|키즈|kids|toy|장난감티비|튜브|보람|핑크퐐|뽀로로|타요|베베핀|라바|꼬모|로보카|주니토니|애니|만화|동화|vlog|브이로그|먹방|챌린지|"
    r"숯박스|웃음|예능|드라마|노래|음악|플리|playlist|asmr|게임|minecraft|마인크래프트|로블록스|주파수|세타파|hz|라이브|콘서트|cover|"
    r"인형|슬라임|색깔놀이|모래놀이|자동차 장난감|블라드|니키타|토이|유라야놀자|까투리|헤이지니|캐리와|다람냥|사랑아놀자|체조|극한직업|"
    r"뉴스|news|대통령|무한도전|유퀴즈|트루먼쇼|시어머니|부부|배우자|중년|어른|직장|회사|연애|신랑수업|토익|텝스|편입|당구|리뷰|갤럭시|아이폰|폴드|키즈폰|마른|나의 두 번째 교과서",
    re.I)


def _edu_label(m: dict) -> str:
    y, mo, d = m["searchDate"].split("-")
    return f"{y}.{int(mo)}.{int(d)}. \n\n{m['keyword']} (교육·육아 채널)"


def _to_pool_row(label: str, v: dict) -> list:
    return [label, f"https://www.youtube.com/watch?v={v['id']}",
            f'=IMAGE("https://img.youtube.com/vi/{v["id"]}/hqdefault.jpg")', v.get("title", "")]


def edu_pool_rows(m: dict, data: dict, top_n: int = 5, exclude_ids: set | None = None) -> list[list]:
    """교육·육아 채널 영상만 골라 풀링 행을 만든다 (일반 명사 키워드 보완용, 라벨에 '(교육·육아 채널)').

    1차: LLM(orchestrator.llm.call_json)에 후보 40개(조회수 순, 쇼츠 제외)를 주고 고르게 한다.
    2차(LLM 실패): 정규식 휴리스틱 (정밀도 낮음).
    """
    label = _edu_label(m)
    vids = [v for v in sorted(data.get("videos", []), key=lambda v: float(v.get("viewCount") or 0), reverse=True)
            if not v.get("shorts") and v.get("id") and v["id"] not in (exclude_ids or set())]
    cands = vids[:40]
    try:
        from orchestrator import llm
        listing = "\n".join(f"{i}. [{v.get('channelTitle', '')}] {v.get('title', '')} ({float(v.get('viewCount') or 0) / 10000:.0f}만회)"
                            for i, v in enumerate(cands))
        prompt = (
            f"유튜브 검색어 '{m['keyword']}'의 결과 영상 목록이다. 초등 학부모 대상 교육 채널이 "
            "벤치마크로 쓸 '교육·육아 채널의 영상'만 고른다. 기준: 부모·교사·전문가가 아이 교육/육아/학습법을 "
            "설명하는 정보성 영상(예: 오은영, EBS 다큐, 교육대기자TV, 초등교사 채널, 공부법 강의). 제외: 아동용 "
            "동요·장난감·키즈 예능 채널, 예능·드라마·미디어 클립, 뉴스 단신, 음악, 모바일/가전 리뷰, 성인 대상 자기계발, "
            f"주제와 무관한 영상. 최대 {top_n}개를 조회수가 높은 순으로 고르고, 적합한 것이 없으면 빈 배열을 낸다.\n"
            '설명 없이 JSON만: {"picks": [번호, ...]}\n\n' + listing)
        obj = llm.call_json(prompt, max_tokens=300)
        picks = [int(i) for i in obj.get("picks", []) if str(i).isdigit() and int(i) < len(cands)]
        return [_to_pool_row(label, cands[i]) for i in picks[:top_n]]
    except Exception as e:
        log(f"교육·육아 선별 LLM 실패({m['keyword']}): {e} → 정규식 휴리스틱 사용")
    out = []
    for v in vids:
        text = f"{v.get('title', '')} {v.get('channelTitle', '')}"
        if EDU_RE.search(text) and not EDU_EXCLUDE_RE.search(text):
            out.append(_to_pool_row(label, v))
        if len(out) >= top_n:
            break
    return out


# ---------------------------------------------------------------- 시트 I/O
class Sheet:
    def __init__(self):
        self.sheet_id = os.getenv("DG_VT_SHEET_ID", "").strip() or gsheet.SHEET_ID_DEFAULT
        os.environ["DG_THUMB_SHEET_ID"] = self.sheet_id  # gsheet 모듈이 이 값을 읽는다
        self.kw_gid = int(os.getenv("DG_VT_KEYWORD_GID", "") or KEYWORD_GID_DEFAULT)
        self.pool_gid = int(os.getenv("DG_VT_POOL_GID", "") or POOL_GID_DEFAULT)
        self.kw_title = gsheet.resolve_title(self.kw_gid)
        self.pool_title = gsheet.resolve_title(self.pool_gid)

    @staticmethod
    def _last_nonempty(col_values: list[list[str]]) -> int:
        last = 0
        for i, row in enumerate(col_values):
            if row and str(row[0]).strip():
                last = i + 1
        return last

    def existing_keywords(self) -> set[str]:
        return {norm(r[0]) for r in gsheet.read("C3:C2000", self.kw_title) if r and r[0].strip()}

    def next_keyword_row(self) -> int:
        return self._last_nonempty(gsheet.read("C1:C2000", self.kw_title)) + 1

    def next_pool_row(self) -> int:
        return self._last_nonempty(gsheet.read("A1:A5000", self.pool_title)) + 1

    def pooled_video_ids(self) -> set[str]:
        ids = set()
        for r in gsheet.read("B2:B5000", self.pool_title):
            if r and "v=" in r[0]:
                ids.add(r[0].split("v=")[1].split("&")[0])
        return ids

    def write_keyword_rows(self, start: int, rows: list[list]) -> None:
        end = start + len(rows) - 1
        gsheet.update(f"A{start}:AK{end}", rows, self.kw_title)
        gsheet.batch_update([{
            "repeatCell": {
                "range": {"sheetId": self.kw_gid, "startRowIndex": start - 1, "endRowIndex": end,
                          "startColumnIndex": 7, "endColumnIndex": 9},  # H:I
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}},
                "fields": "userEnteredFormat.numberFormat",
            }}])

    def write_pool_rows(self, start: int, rows: list[list]) -> None:
        end = start + len(rows) - 1
        gsheet.update(f"A{start}:D{end}", rows, self.pool_title)
        gsheet.batch_update([{
            "updateDimensionProperties": {
                "range": {"sheetId": self.pool_gid, "dimension": "ROWS",
                          "startIndex": start - 1, "endIndex": end},
                "properties": {"pixelSize": 150},
                "fields": "pixelSize",
            }}])


# ---------------------------------------------------------------- 큐
def queue_path() -> Path:
    return Path(os.getenv("DG_VT_QUEUE", "") or REPO_ROOT / "viewtrap_keyword_queue.json")


def load_queue() -> dict:
    return json.loads(queue_path().read_text(encoding="utf-8"))


def save_queue(q: dict) -> None:
    queue_path().write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")


def notify(text: str) -> None:
    if not (os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and os.getenv("TELEGRAM_CHAT_ID", "").strip()):
        log("텔레그램 미설정(TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID) — 알림 생략")
        return
    try:
        from vault_pipeline.telegram_notify import send
        ok = send(text)
        log("텔레그램 발송 성공" if ok else "텔레그램 발송 실패 (Bot API 오류)")
    except Exception as e:  # 알림은 부가 기능
        log(f"텔레그램 실패: {e}")


# ---------------------------------------------------------------- 메인
def run(limit: int, dry_run: bool, max_age_days: int, min_credits: int, pause: tuple[float, float],
        edu_extra: bool = True) -> int:
    q = load_queue()
    pending = [k for k in q["keywords"] if k.get("status") == "pending"]
    if not pending:
        log("큐가 비었음")
        notify("뷰트랩 키워드 조사: 큐가 비었습니다. viewtrap_keyword_queue.json에 키워드를 추가하세요.")
        return 0

    vt = Viewtrap(os.getenv("VIEWTRAP_COOKIE", ""))
    remaining = vt.remaining()
    log(f"잔여 검색 횟수 {remaining}")
    expiry = cookie_expiry(os.getenv("VIEWTRAP_COOKIE", ""))
    expiry_note = ""
    if expiry:
        left = expiry - datetime.now(KST)
        expiry_note = f"쿠키 만료 {expiry.strftime('%m/%d %H:%M')} (남은 {left.days}일 {left.seconds // 3600}시간)"
        log(expiry_note)
        if left < timedelta(days=2):
            notify(f"⚠️ 뷰트랩 쿠키가 {expiry.strftime('%m/%d %H:%M')}에 만료됩니다. 만료 전에 app.viewtrap.com에 다시 로그인해 "
                   f"DevTools → Network → api.viewtrap.com 요청의 cookie 헤더를 GitHub Secret VIEWTRAP_COOKIE에 다시 넣어주세요.")
    sheet = Sheet()
    existing = sheet.existing_keywords()
    hist = {}
    for h in vt.histories():  # 최신 round가 먼저 오므로 처음 본 것을 유지
        hist.setdefault(norm(h.get("keyword", "")), str(h["round_no"]))

    today = kst_date()
    done, errors, results = [], [], []
    for item in pending:
        if len(results) >= limit:
            break
        kw = item["keyword"]
        if norm(kw) in existing:
            item["status"] = "skipped_in_sheet"
            log(f"{kw}: 이미 시트에 있음 → 건너뜀")
            continue
        try:
            round_no, data, reused = None, None, False
            if norm(kw) in hist:
                cand = vt.videos(hist[norm(kw)])
                m0 = compute_metrics(kw, cand)
                age = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(m0["searchDate"], "%Y-%m-%d")).days
                if age <= max_age_days and m0["n"] > 0:
                    round_no, data, reused = hist[norm(kw)], cand, True
            if data is None:
                if remaining < min_credits:
                    log(f"잔여 검색 횟수 {remaining} < {min_credits} → 새 검색 중단")
                    break
                if dry_run:
                    log(f"[dry-run] 새 검색 예정: {kw}")
                    continue
                round_no, data = vt.search(kw)
                remaining -= 1
                time.sleep(random.uniform(*pause))
            m = compute_metrics(kw, data)
            results.append((item, m, data, reused))
            log(f"{kw}: round {round_no} n={m['n']} score={m['score']} F={m['F']} G={m['G']} "
                f"J={m['medViews']} K={m['medSubs']}{' (재사용)' if reused else ''}")
            item.update({"status": "done", "date": today, "round_no": round_no,
                         "score": m["score"], "reused": reused})
            done.append(kw)
        except AuthError:
            raise
        except Exception as e:
            errors.append(f"{kw}: {e}")
            item.update({"status": "error", "error": str(e)[:200], "date": today})
            log(f"{kw}: 오류 {e}")

    if dry_run:
        log("[dry-run] 시트/큐 기록 생략")
        return 0

    # 1) 키워드 탭
    if results:
        start = sheet.next_keyword_row()
        rows = []
        for i, (item, m, _, _) in enumerate(results):
            rows.append(keyword_row(start + i, m, yt_suggest(m["keyword"])))
            item["sheetRow"] = start + i
        sheet.write_keyword_rows(start, rows)
        log(f"키워드 탭 {start}~{start + len(rows) - 1}행 기록")

    # 2) 풀링 탭 (5점 이상)
    good = [(item, m, data) for item, m, data, _ in results if m["score"] >= 5]
    pooled_range = None
    if good:
        exclude = sheet.pooled_video_ids()
        prow = []
        for item, m, data in good:
            rows = pool_rows(m, data, 5, exclude)
            exclude.update(r[1].split("v=")[1] for r in rows)
            if edu_extra:
                extra = edu_pool_rows(m, data, 5, exclude)
                exclude.update(r[1].split("v=")[1] for r in extra)
                rows += extra
            prow.extend(rows)
            item["pooled"] = bool(rows)
        if prow:
            pstart = sheet.next_pool_row()
            sheet.write_pool_rows(pstart, prow)
            pooled_range = (pstart, pstart + len(prow) - 1)
            log(f"풀링 탭 {pooled_range[0]}~{pooled_range[1]}행 기록")

    q["lastRun"] = {"date": today, "searched": len(results), "remainingSearchCredits": remaining,
                    "errors": errors}
    save_queue(q)

    lines = [f"뷰트랩 키워드 조사 {today}: {len(results)}개 처리, 잔여 검색 {remaining}회" + (f", {expiry_note}" if expiry_note else "")]
    lines += [f"- {m['keyword']}: {m['score']}점 (F {m['F']}만, G {m['G']}, J {m['medViews']}, K {m['medSubs']})"
              for _, m, _, _ in sorted(results, key=lambda x: -x[1]["score"])]
    if good:
        lines.append("5점 이상: " + ", ".join(m["keyword"] for _, m, _ in good)
                     + (f" → 풀링 {pooled_range[0]}~{pooled_range[1]}행" if pooled_range else "")
                     + (" (교육·육아 채널 추가 선별은 정규식 휴리스틱 — 수작업 확인 권장)" if edu_extra else ""))
    if errors:
        lines.append("오류: " + "; ".join(errors))
    lines.append("주의: 일반 명사 키워드는 주제 무관 대형 채널 영상 때문에 점수가 높을 수 있음")
    notify("\n".join(lines))
    print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=int(os.getenv("DG_VT_DAILY_LIMIT", "30")))
    ap.add_argument("--dry-run", action="store_true", help="검색·기록 없이 계획만 출력")
    ap.add_argument("--max-age-days", type=int, default=365, help="검색 내역 재사용 허용 일수")
    ap.add_argument("--min-credits", type=int, default=40, help="잔여 검색 횟수가 이보다 적으면 새 검색 중단")
    ap.add_argument("--pause", default="8,15", help="검색 사이 대기 초 (min,max)")
    ap.add_argument("--no-edu-extra", action="store_true",
                    help="5점 키워드의 교육·육아 채널 추가 선별 행을 넣지 않음")
    args = ap.parse_args(argv)
    lo, hi = (float(x) for x in args.pause.split(","))
    try:
        return run(args.limit, args.dry_run, args.max_age_days, args.min_credits, (lo, hi),
                   edu_extra=not args.no_edu_extra)
    except AuthError as e:
        log(str(e))
        notify(f"뷰트랩 키워드 조사 중단: {e}\nDevTools → Network → api.viewtrap.com 요청 → cookie 헤더를 "
               f"GitHub Secret VIEWTRAP_COOKIE에 다시 넣어주세요.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
