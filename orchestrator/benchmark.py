"""벤치마크 후보 판정 — "내가 색칠한 영상과 비슷한 것"을 규칙 + LLM으로 고른다.

사용자 기준(2026-09-19, data/benchmark_rules.json "criteria"):
  1) 유명인이 나오는 영상 제외 (사람 때문에 보는 조회수)
  2) 구독자 많은 채널·방송·뉴스·키즈 제외 — 구독자 대비 조회수가 높은 소규모 채널 우선
  3) 썸네일·제목만으로 조회수를 얻은 것 같은 영상

두 단계:
  rule_score(video)  : 규칙 점수(가중치는 rules.json weights)와 차단 사유. 빠르고 공짜. 정밀도 ~50%.
  judge(videos)      : LLM(orchestrator.llm.call_json)에 기준 + 사용자가 확정한 예시(시트의 노란 행)와
                       확정하지 않은 예시를 주고 0~10점과 한 줄 사유를 받는다. 규칙에서 차단된 것은 보내지 않는다.
score_videos()가 둘을 합쳐 [{score, why, blocked, rule_score, ...}]를 돌려준다.

영상 dict 형식(뷰트랩·유튜브 API·시트 어디서 오든 이 키로 맞춘다):
  {id, title, channelTitle, viewCount, subscriberCount, publishedAt, durationSec, shorts}
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_FILE = REPO_ROOT / "data" / "benchmark_rules.json"
EXAMPLES_FILE = REPO_ROOT / "data" / "benchmark_examples.json"


def log(msg: str) -> None:
    print(f"[benchmark] {msg}", flush=True)


def load_rules() -> dict:
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def load_examples() -> dict:
    if EXAMPLES_FILE.exists():
        return json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    return {"picks": [], "rejects": []}


def _pattern(words: list[str]) -> re.Pattern:
    return re.compile("|".join(re.escape(w) for w in words if w), re.I) if words else re.compile(r"(?!x)x")


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def rule_score(v: dict, rules: dict | None = None) -> dict:
    """규칙 점수. 반환: {rule_score, blocked(bool), reasons[list], ratio}"""
    rules = rules or load_rules()
    w, th = rules["weights"], rules["thresholds"]
    text = f"{v.get('title', '')} {v.get('channelTitle', '')}"
    subs, views = _num(v.get("subscriberCount")), _num(v.get("viewCount"))
    ratio = (views / subs) if (subs and views and subs > 0) else None
    s, why, blocked = 0, [], []
    if subs is not None:
        if subs <= th["max_subscribers"]:
            s += w["subs_under_max"]; why.append(f"구독 {subs / 1e4:.0f}만≤{th['max_subscribers'] / 1e4:.0f}만")
        if subs <= th["prefer_subscribers_under"]:
            s += w["subs_under_prefer"]
        if subs > 3_000_000:
            s += w["subs_over_3m"]; why.append("구독>300만")
    if views is not None:
        if views >= th["min_views"]:
            s += w["views_over_min"]
        else:
            s += w["views_under_min"]; why.append(f"조회 {views / 1e4:.1f}만<{th['min_views'] / 1e4:.0f}만")
    if ratio is not None:
        if ratio >= th["good_ratio"]:
            s += w["ratio_good"]
        if ratio >= th["great_ratio"]:
            s += w["ratio_great"]; why.append(f"조회/구독 {ratio:.1f}배")
    if _pattern(rules["celebrities"]).search(text):
        s += w["celebrity"]; blocked.append("유명인")
    if _pattern(rules["media_channels"]).search(text):
        s += w["media"]; blocked.append("방송/미디어/기업")
    if _pattern(rules["kids_music_patterns"]).search(text):
        s += w["kids_music"]; blocked.append("키즈/음악/예능")
    if _pattern(rules["parent_topic_patterns"]).search(v.get("title", "")):
        s += w["parent_topic"]; why.append("학부모 주제")
    if v.get("shorts") or v.get("isShort"):
        s += w["shorts"]
        if th.get("exclude_shorts"):
            blocked.append("쇼츠")
    dur = _num(v.get("durationSec"))
    if dur and th.get("max_duration_sec") and dur > th["max_duration_sec"]:
        blocked.append("60분 초과")
    hard_block = bool({"키즈/음악/예능", "쇼츠", "60분 초과"} & set(blocked))
    return {"rule_score": s, "blocked": hard_block, "flags": blocked, "reasons": why, "ratio": ratio}


def _ex_line(e: dict) -> str:
    subs = e.get("subs"); views = e.get("views")
    return (f"[{e.get('channel', '')}] 구독 {(_num(subs) or 0) / 1e4:.0f}만 · 조회 {(_num(views) or 0) / 1e4:.0f}만"
            f" · {e.get('ratio') or 0:.1f}배 — {e.get('title', '')}")


def judge(videos: list[dict], rules: dict | None = None, examples: dict | None = None,
          max_examples: int = 14, keyword: str = "") -> list[dict]:
    """LLM 판정. videos 순서대로 [{score(0~10), why}] (실패 시 빈 리스트)."""
    if not videos:
        return []
    rules = rules or load_rules()
    examples = examples or load_examples()
    picks = examples.get("picks", [])[-max_examples:]
    rejects = [r for r in examples.get("rejects", []) if "(교육·육아" in str(r.get("keyword", ""))][-max_examples:] \
        or examples.get("rejects", [])[-max_examples:]
    listing = "\n".join(
        f"{i}. [{v.get('channelTitle', '')}] 구독 {(_num(v.get('subscriberCount')) or 0) / 1e4:.0f}만 · "
        f"조회 {(_num(v.get('viewCount')) or 0) / 1e4:.0f}만 · {(v.get('_ratio') or 0):.1f}배 · "
        f"{int((_num(v.get('durationSec')) or 0) // 60)}분 — {v.get('title', '')}"
        for i, v in enumerate(videos))
    prompt = (
        "나는 초등 학부모 대상 교육 유튜브 채널(구독자 수천 명)을 운영한다. 벤치마크로 쓸 영상을 고르는 내 기준:\n"
        + "\n".join(f"- {c}" for c in rules["criteria"]) + "\n\n"
        "내가 실제로 '벤치마크 확정'한 영상 예시(노란색):\n" + "\n".join("  ✔ " + _ex_line(e) for e in picks) + "\n\n"
        "같은 검색 결과에 있었지만 확정하지 않은 영상 예시:\n" + "\n".join("  ✘ " + _ex_line(e) for e in rejects) + "\n\n"
        + (f"검색어: {keyword}\n" if keyword else "")
        + "아래 후보 각각에 대해 '내가 노란색으로 칠할 확률'을 0~10점으로 매기고 한 줄 사유를 써라. "
        "기준 1·2에 걸리면 3점 이하. 정보성(교육·육아·학습법)이 아니어도 제목 구조가 베낄 만하면 6점 이상 가능. "
        "구독자 대비 조회수가 높을수록, 채널이 작을수록 가점.\n"
        '설명 없이 JSON만: {"scores": [{"i": 0, "score": 8, "why": "..."}, ...]}\n\n' + listing)
    try:
        from orchestrator import llm
        obj = llm.call_json(prompt, max_tokens=1500)
    except Exception as e:  # LLM 없음/실패 → 규칙 점수만 쓴다
        log(f"LLM 판정 실패: {e}")
        return []
    out = [{"score": None, "why": ""} for _ in videos]
    for s in obj.get("scores", []):
        try:
            i = int(s.get("i"))
            if 0 <= i < len(videos):
                out[i] = {"score": max(0, min(10, int(s.get("score", 0)))), "why": str(s.get("why", ""))[:200]}
        except (TypeError, ValueError):
            continue
    return out


def score_videos(videos: list[dict], keyword: str = "", use_llm: bool = True,
                 rules: dict | None = None, examples: dict | None = None) -> list[dict]:
    """규칙 + LLM 합산. 각 원소: {score(0~10), why, blocked, flags, rule_score, ratio, llm_score}.

    score = LLM 점수(있으면), 없으면 규칙 점수를 0~10으로 눌러 담는다(rule_score+2, 0~10 절단).
    차단(키즈/쇼츠/60분 초과)은 0점. 유명인·방송은 LLM이 최종 판단(예: EBSi 강의는 통과)하되 규칙만일 땐 감점 그대로.
    """
    rules = rules or load_rules()
    res = []
    for v in videos:
        r = rule_score(v, rules)
        v["_ratio"] = r["ratio"]
        res.append({**r, "llm_score": None, "score": None, "why": ""})
    if use_llm:
        idx = [i for i, r in enumerate(res) if not r["blocked"]]
        js = judge([videos[i] for i in idx], rules, examples, keyword=keyword) if idx else []
        for k, i in enumerate(idx):
            if k < len(js) and js[k]["score"] is not None:
                res[i]["llm_score"] = js[k]["score"]
                res[i]["why"] = js[k]["why"]
    for r in res:
        if r["blocked"]:
            r["score"] = 0
            r["why"] = r["why"] or ("제외: " + ", ".join(r["flags"]))
        elif r["llm_score"] is not None:
            r["score"] = r["llm_score"]
        else:
            r["score"] = max(0, min(10, r["rule_score"] + 2))
            r["why"] = r["why"] or ", ".join(r["flags"] + r["reasons"])
    return res


def is_candidate(scored: dict, rules: dict | None = None) -> bool:
    rules = rules or load_rules()
    return (scored.get("score") or 0) >= rules["thresholds"]["candidate_score"]


def pick_benchmarks(videos: list[dict], top_n: int = 5, keyword: str = "",
                    exclude_ids: set | None = None, use_llm: bool = True) -> list[tuple[dict, dict]]:
    """검색 결과 전체에서 벤치마크 후보 top_n. (영상, 판정) 쌍을 점수·조회/구독 배율 순으로."""
    rules = load_rules()
    th = rules["thresholds"]
    pool = [v for v in videos if v.get("id") and v["id"] not in (exclude_ids or set())
            and (_num(v.get("viewCount")) or 0) >= th["min_views"]
            and (_num(v.get("subscriberCount")) is None or _num(v.get("subscriberCount")) <= th["max_subscribers"])]
    # 규칙 1차: 차단 제거 후 규칙 점수 상위 40개만 LLM에 보낸다 (비용 제한)
    pre = [(v, rule_score(v, rules)) for v in pool]
    pre = [(v, r) for v, r in pre if not r["blocked"]]
    pre.sort(key=lambda x: (x[1]["rule_score"], x[1]["ratio"] or 0), reverse=True)
    cands = [v for v, _ in pre[:40]]
    scored = score_videos(cands, keyword=keyword, use_llm=use_llm, rules=rules)
    pairs = [(v, s) for v, s in zip(cands, scored) if is_candidate(s, rules)]
    pairs.sort(key=lambda x: (x[1]["score"], x[1]["ratio"] or 0), reverse=True)
    return pairs[:top_n]


def use_llm_default() -> bool:
    return not os.getenv("DG_BENCH_NO_LLM")
