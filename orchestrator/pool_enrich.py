"""풀링 영상 만들기 탭 보강 — 빈 조회수(게시일)·구독자 셀 채우기 + 벤치마크 후보 표시.

실행: python3 -m orchestrator.pool_enrich [--dry-run] [--no-llm] [--limit N] [--rescore] [--refresh-examples]
크론: .github/workflows/pool-enrich.yml (6시간마다 + 수동). 뷰트랩 파이프라인이 새 행을 넣은 뒤에도 호출된다.

흐름
  1. 헤더로 열 위치를 잡고(orchestrator.pool_cells) URL 있는 행을 모은다.
  2. B(조회수) 또는 C(구독자)가 빈 행의 영상 통계를 받는다. 출처는 둘 중 하나:
       YOUTUBE_API_KEY            → YouTube Data API v3 (videos.list + channels.list, 50개당 쿼터 1+1)
       YT_RESEARCH_URL(+PASSWORD) → yt_research 사이트 POST /api/videos-refresh (사이트에 있는 키를 씀)
     A열 검색일 기준 경과일·일평균을 계산해 pool_cells.views_cell / subs_cell 형식으로 쓴다.
  3. 벤치마크 후보: 통계가 있는 행 중 아직 판정 안 한 행(C셀 메모 없음)을 orchestrator.benchmark로
     채점한다. 후보(점수≥7)는 C셀 배경을 연두로 칠하고 메모에 "벤치 후보 8/10 — 사유"를 남긴다.
     사용자가 D(URL) 셀을 노란색으로 칠한 행은 '확정'이라 판정하지 않는다(예시로만 쓴다).
     --rescore 면 메모가 있어도 다시 채점한다.
  4. --refresh-examples: 시트의 노란 행/그 외 행을 data/benchmark_examples.json 으로 내보낸다(LLM few-shot).

환경변수: GSHEET_SA_JSON(필수), YOUTUBE_API_KEY 또는 YT_RESEARCH_URL(+YT_RESEARCH_PASSWORD),
          ANTHROPIC_API_KEY/CLAUDE_CODE_OAUTH_TOKEN(LLM 판정, 없으면 규칙 점수만), TELEGRAM_*(선택)
          DG_THUMB_SHEET_ID / DG_VT_POOL_GID (기본: 벤치마킹 시트 787785781)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import benchmark, gsheet  # noqa: E402
from orchestrator.pool_cells import (col_letter, resolve_pool_columns, search_date_from_label,  # noqa: E402
                                     subs_cell, video_id, views_cell)

POOL_GID_DEFAULT = 787785781
YT_API = "https://www.googleapis.com/youtube/v3"


def log(msg: str) -> None:
    print(f"[pool_enrich] {msg}", flush=True)


# ---------------------------------------------------------------- 영상 통계
def _parse_duration(iso: str) -> int:
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def stats_youtube_api(ids: list[str], key: str) -> dict[str, dict]:
    """YouTube Data API v3. 반환 {id: {viewCount, subscriberCount, publishedAt, channelTitle, durationSec, shorts}}"""
    out: dict[str, dict] = {}
    chan_ids: set[str] = set()
    for i in range(0, len(ids), 50):
        r = requests.get(f"{YT_API}/videos", params={
            "part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50]), "key": key}, timeout=60)
        r.raise_for_status()
        for it in r.json().get("items", []):
            dur = _parse_duration(it.get("contentDetails", {}).get("duration", ""))
            out[it["id"]] = {
                "id": it["id"], "title": it["snippet"].get("title", ""),
                "channelId": it["snippet"].get("channelId", ""), "channelTitle": it["snippet"].get("channelTitle", ""),
                "publishedAt": it["snippet"].get("publishedAt", ""),
                "viewCount": int(it.get("statistics", {}).get("viewCount", 0) or 0),
                "durationSec": dur, "shorts": 0 < dur <= 60,
            }
            chan_ids.add(out[it["id"]]["channelId"])
    subs: dict[str, int] = {}
    cl = sorted(c for c in chan_ids if c)
    for i in range(0, len(cl), 50):
        r = requests.get(f"{YT_API}/channels", params={"part": "statistics", "id": ",".join(cl[i:i + 50]), "key": key},
                         timeout=60)
        r.raise_for_status()
        for it in r.json().get("items", []):
            subs[it["id"]] = int(it.get("statistics", {}).get("subscriberCount", 0) or 0)
    for v in out.values():
        v["subscriberCount"] = subs.get(v["channelId"])
    return out


def stats_yt_research(ids: list[str], base: str, password: str = "") -> dict[str, dict]:
    """yt_research 사이트의 /api/videos-refresh (서버 키 사용). APP_PASSWORD 가 걸려 있으면 로그인 쿠키를 받는다."""
    s = requests.Session()
    base = base.rstrip("/")
    if password:
        r = s.post(f"{base}/api/login", json={"password": password}, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"yt_research 로그인 실패 {r.status_code}: {r.text[:120]}")
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 400):
        r = s.post(f"{base}/api/videos-refresh", json={"videoIds": ids[i:i + 400]}, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"videos-refresh {r.status_code}: {r.text[:160]}")
        for it in r.json().get("items", []):
            out[it["videoId"]] = {
                "id": it["videoId"], "title": it.get("title", ""), "channelId": it.get("channelId", ""),
                "channelTitle": it.get("channelTitle", ""), "publishedAt": it.get("publishedAt", ""),
                "viewCount": it.get("viewCount"), "subscriberCount": it.get("subscriberCount"),
                "durationSec": it.get("durationSec"), "shorts": bool(it.get("isShort")),
            }
    return out


def fetch_stats(ids: list[str]) -> dict[str, dict]:
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    base = os.getenv("YT_RESEARCH_URL", "").strip()
    if key:
        return stats_youtube_api(ids, key)
    if base:
        return stats_yt_research(ids, base, os.getenv("YT_RESEARCH_PASSWORD", "").strip())
    raise RuntimeError("YOUTUBE_API_KEY 또는 YT_RESEARCH_URL 이 필요합니다")


# ---------------------------------------------------------------- 시트
class Pool:
    def __init__(self):
        self.gid = int(os.getenv("DG_VT_POOL_GID", "") or POOL_GID_DEFAULT)
        self.title = gsheet.resolve_title(self.gid)
        rows = gsheet.read("A1:AZ2000", self.title)
        self.header = rows[0] if rows else []
        self.cols = resolve_pool_columns(self.header)
        self.rows = rows[1:]  # 0-base i → 시트 행 i+2
        self.last_row = len(rows)

    def cell(self, i: int, key: str) -> str:
        c = self.cols[key]
        r = self.rows[i]
        return str(r[c]).strip() if c < len(r) else ""

    def url_backgrounds(self) -> list:
        """D(URL) 열 배경색 — 노란색 = 사용자 확정."""
        u = col_letter(self.cols["url"])
        try:
            bgs = gsheet.read_backgrounds(f"{u}2:{u}{self.last_row}", self.title)
        except Exception as e:
            log(f"배경색 읽기 실패: {e}")
            return []
        return [(r[0] if r else None) for r in bgs]

    def subs_notes(self) -> list[str]:
        """C(구독자) 열 메모 — 이미 판정한 행 표시."""
        c = col_letter(self.cols["subs"])
        try:
            r = requests.get(f"{gsheet.API}/{gsheet.sheet_id()}", headers=gsheet._headers(), params={
                "ranges": f"'{self.title}'!{c}2:{c}{self.last_row}", "includeGridData": "true",
                "fields": "sheets.data.rowData.values.note"}, timeout=60)
            r.raise_for_status()
            data = (r.json().get("sheets") or [{}])[0].get("data", [{}])[0]
            out = []
            for row in data.get("rowData", []):
                vals = row.get("values") or [{}]
                out.append(str(vals[0].get("note", "")))
            return out
        except Exception as e:
            log(f"메모 읽기 실패: {e}")
            return []


def is_user_pick(bg, rules: dict) -> bool:
    """노란 계열(사용자 확정). 파이프라인이 칠하는 연두/파랑은 제외."""
    if not gsheet.is_colored(bg):
        return False
    r, g, b = bg
    cand = rules["candidate_color"]
    if abs(r - cand["red"]) < 0.03 and abs(g - cand["green"]) < 0.03 and abs(b - cand["blue"]) < 0.03:
        return False
    if abs(r - 0.788) < 0.03 and abs(g - 0.854) < 0.03 and abs(b - 0.973) < 0.03:  # DONE_BLUE
        return False
    return True


def export_examples(pool: Pool, stats_by_row: dict[int, dict], rules: dict) -> dict:
    """시트 → data/benchmark_examples.json (노란 행 = picks, 통계 있는 나머지 = rejects)."""
    bgs = pool.url_backgrounds()
    picks, rejects = [], []
    for i in range(len(pool.rows)):
        st = stats_by_row.get(i)
        if not st:
            continue
        ex = {"row": i + 2, "keyword": pool.cell(i, "date_kw").split("\n")[-1].strip(), "channel": st.get("channelTitle", ""),
              "subs": st.get("subscriberCount"), "views": st.get("viewCount"), "ratio": st.get("_ratio"),
              "duration_sec": st.get("durationSec"), "title": st.get("title") or pool.cell(i, "title")}
        (picks if (i < len(bgs) and is_user_pick(bgs[i], rules)) else rejects).append(ex)
    return {"_doc": "pool_enrich --refresh-examples 로 시트에서 내보낸 예시(노란 행 = picks)", "picks": picks, "rejects": rejects}


# ---------------------------------------------------------------- 실행
def run(dry_run: bool, use_llm: bool, limit: int, rescore: bool, refresh_examples: bool) -> int:
    if not gsheet.available():
        log("GSHEET_SA_JSON 미설정 — 종료")
        return 1
    rules = benchmark.load_rules()
    pool = Pool()
    log(f"탭 '{pool.title}' 열={pool.cols} 행={len(pool.rows)}")

    # 1) 통계가 필요한 행
    need: list[tuple[int, str]] = []  # (i, video_id)
    all_ids: dict[int, str] = {}
    for i in range(len(pool.rows)):
        vid = video_id(pool.cell(i, "url"))
        if not vid:
            continue
        all_ids[i] = vid
        if not pool.cell(i, "views") or not pool.cell(i, "subs"):
            need.append((i, vid))
    need = need[:limit]
    log(f"통계 채울 행 {len(need)}개 (URL 있는 행 {len(all_ids)}개)")

    filled = 0
    stats: dict[str, dict] = {}
    if need:
        try:
            stats = fetch_stats(sorted({v for _, v in need}))
        except Exception as e:
            log(f"통계 조회 실패: {e}")
            stats = {}
        updates = []
        for i, vid in need:
            st = stats.get(vid)
            if not st:
                continue
            sd = search_date_from_label(pool.cell(i, "date_kw"))
            b = views_cell(st.get("viewCount"), st.get("publishedAt"), sd)
            c = subs_cell(st.get("subscriberCount"), st.get("viewCount"))
            row = pool.rows[i]
            while len(row) <= max(pool.cols["views"], pool.cols["subs"]):
                row.append("")
            row[pool.cols["views"]], row[pool.cols["subs"]] = b, c
            updates.append((i + 2, b, c))
        if updates and not dry_run:
            lo, hi = pool.cols["views"], pool.cols["subs"]
            for rownum, b, c in updates:
                if hi == lo + 1:
                    gsheet.update(f"{col_letter(lo)}{rownum}:{col_letter(hi)}{rownum}", [[b, c]], pool.title)
                else:
                    gsheet.update(f"{col_letter(lo)}{rownum}", [[b]], pool.title)
                    gsheet.update(f"{col_letter(hi)}{rownum}", [[c]], pool.title)
                time.sleep(0.2)
        filled = len(updates)
        log(f"조회수·구독자 {filled}행 {'(dry-run) ' if dry_run else ''}기록")

    # 2) 벤치마크 후보 판정 — 통계가 있고(방금 받았거나 셀에 있음), 사용자 확정(노랑)이 아니고, 메모 없는 행
    bgs = pool.url_backgrounds()
    notes = pool.subs_notes()
    targets: list[int] = []
    for i, vid in all_ids.items():
        if i < len(bgs) and is_user_pick(bgs[i], rules):
            continue
        if not rescore and i < len(notes) and notes[i].startswith("벤치"):
            continue
        if vid in stats or (pool.cell(i, "views") and pool.cell(i, "subs")):
            targets.append(i)
    # 셀에만 통계가 있는 행은 다시 받아야 채점 가능 (제목·채널명·게시일 필요) — 한 번에 400개까지
    missing = [all_ids[i] for i in targets if all_ids[i] not in stats]
    if missing and (targets):
        try:
            stats.update(fetch_stats(sorted(set(missing))[:400]))
        except Exception as e:
            log(f"채점용 통계 조회 실패: {e}")
    videos, idx = [], []
    for i in targets:
        st = stats.get(all_ids[i])
        if st:
            videos.append(dict(st)); idx.append(i)
    log(f"벤치마크 채점 대상 {len(videos)}행 (LLM {'사용' if use_llm else '미사용'})")
    scored = benchmark.score_videos(videos, use_llm=use_llm, rules=rules) if videos else []
    n_cand = 0
    for i, v, s in zip(idx, videos, scored):
        rownum = i + 2
        cand = benchmark.is_candidate(s, rules)
        note = (f"벤치 {'후보' if cand else '보류'} {s['score']}/10 — {s['why']}"
                f"\n규칙 {s['rule_score']}점 {', '.join(s['flags'] + s['reasons'])}".strip())
        if dry_run:
            log(f"  행{rownum} {'★' if cand else ' '} {s['score']} [{v.get('channelTitle', '')[:12]}] {v.get('title', '')[:32]} — {s['why'][:60]}")
            continue
        reqs = [{"updateCells": {
            "range": {"sheetId": pool.gid, "startRowIndex": rownum - 1, "endRowIndex": rownum,
                      "startColumnIndex": pool.cols["subs"], "endColumnIndex": pool.cols["subs"] + 1},
            "rows": [{"values": [{"note": note}]}], "fields": "note"}}]
        if cand:
            n_cand += 1
            c = rules["candidate_color"]
            reqs.append({"repeatCell": {
                "range": {"sheetId": pool.gid, "startRowIndex": rownum - 1, "endRowIndex": rownum,
                          "startColumnIndex": pool.cols["subs"], "endColumnIndex": pool.cols["subs"] + 1},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": c["red"], "green": c["green"], "blue": c["blue"]}}},
                "fields": "userEnteredFormat.backgroundColor"}})
        gsheet.batch_update(reqs)
        time.sleep(0.2)
    if not dry_run:
        log(f"후보 {n_cand}행 연두색 표시, 메모 {len(scored)}행")

    # 3) 예시 갱신
    if refresh_examples:
        by_row = {i: stats[all_ids[i]] for i in all_ids if all_ids[i] in stats}
        for st in by_row.values():
            benchmark.rule_score(st, rules)  # _ratio 채움
            st["_ratio"] = benchmark.rule_score(st, rules)["ratio"]
        ex = export_examples(pool, by_row, rules)
        if dry_run:
            log(f"[dry-run] 예시 picks {len(ex['picks'])} / rejects {len(ex['rejects'])}")
        else:
            benchmark.EXAMPLES_FILE.write_text(json.dumps(ex, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"예시 파일 갱신: picks {len(ex['picks'])} / rejects {len(ex['rejects'])}")

    # 4) 텔레그램
    if not dry_run and (filled or n_cand):
        try:
            from vault_pipeline.telegram_notify import send
            send(f"풀링 시트 보강: 조회수·구독자 {filled}행 채움, 벤치마크 후보 {n_cand}행 연두색 표시"
                 f"(C열 메모에 사유). 확정하려면 D열(URL)을 노란색으로.")
        except Exception as e:
            log(f"텔레그램 생략: {e}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="시트에 쓰지 않고 로그만")
    ap.add_argument("--no-llm", action="store_true", help="LLM 판정 없이 규칙 점수만")
    ap.add_argument("--limit", type=int, default=300, help="한 번에 통계 채울 최대 행 수")
    ap.add_argument("--rescore", action="store_true", help="이미 메모가 있는 행도 다시 채점")
    ap.add_argument("--refresh-examples", action="store_true", help="시트의 노란 행을 data/benchmark_examples.json 으로 내보내기")
    a = ap.parse_args(argv)
    return run(a.dry_run, use_llm=not a.no_llm and benchmark.use_llm_default(), limit=a.limit,
               rescore=a.rescore, refresh_examples=a.refresh_examples)


if __name__ == "__main__":
    sys.exit(main())
