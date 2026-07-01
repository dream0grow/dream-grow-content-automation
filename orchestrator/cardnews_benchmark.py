"""카드뉴스 벤치마킹 리서치 - 최근 뜬 카드뉴스에서 통하는 요소를 뽑아 저장한다.

느린 리서치(Manus)는 주간 잡으로 분리해 data/cardnews_benchmark.md 를 갱신하고,
빠른 카드 생성(cardnews.make_slides)은 load()로 그 파일만 읽어 프롬프트에 주입한다.

Manus가 있으면 웹 리서치로 task 생성 후 폴링, 없으면 Claude 지식 기반 폴백.

실행:
  python3 -m orchestrator.cardnews_benchmark            # 리서치 → 벤치마크 파일 갱신
"""
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from orchestrator import llm, manus_research, prompts
from orchestrator.config import MANUS_API_BASE

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MD_PATH = DATA_DIR / "cardnews_benchmark.md"
JSON_PATH = DATA_DIR / "cardnews_benchmark.json"
KST = timezone(timedelta(hours=9))

BENCHMARK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["trends", "hook_patterns", "structure_patterns", "visual_patterns",
                 "caption_cta_patterns", "avoid", "examples", "confidence"],
    "properties": {
        "trends": {"type": "array", "items": {"type": "string"}},
        "hook_patterns": {"type": "array", "items": {"type": "string"}},
        "structure_patterns": {"type": "array", "items": {"type": "string"}},
        "visual_patterns": {"type": "array", "items": {"type": "string"}},
        "caption_cta_patterns": {"type": "array", "items": {"type": "string"}},
        "avoid": {"type": "array", "items": {"type": "string"}},
        "examples": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["summary", "why_viral"],
            "properties": {"summary": {"type": "string"}, "why_viral": {"type": "string"}}}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
}

# Manus 리서치 완료 대기 한도 (분). 초과 시 Claude 폴백.
STALL_MINUTES = 20


def log(msg: str):
    print(f"[cardnews-benchmark] {msg}", flush=True)


def _manus_research() -> dict | None:
    """Manus로 카드뉴스 벤치마킹 task를 만들고 폴링한다. 실패/미완료면 None."""
    if not manus_research.available():
        return None
    try:
        body = {
            "title": "DG CardNews Benchmark",
            "locale": "ko", "ask_followup": False, "is_hidden": True,
            "share_visibility": "private",
            "message": {"content": prompts.CARDNEWS_BENCHMARK},
            "structured_output_schema": BENCHMARK_SCHEMA,
        }
        resp = manus_research._request_with_retry(
            "POST", f"{MANUS_API_BASE}/v2/task.create",
            headers=manus_research._headers(), json=body, timeout=60)
        resp.raise_for_status()
        task_id = resp.json()["task_id"]
        log(f"Manus task 생성: {task_id[:8]} — 결과 폴링(최대 {STALL_MINUTES}분)")
    except Exception as e:
        log(f"Manus task 생성 실패({type(e).__name__}: {e}) → Claude 폴백")
        return None

    deadline = time.time() + STALL_MINUTES * 60
    while time.time() < deadline:
        time.sleep(30)
        try:
            done, results, dbg = manus_research.poll_results([task_id])
        except Exception as e:
            log(f"폴링 예외: {e}")
            continue
        if done and results:
            log("Manus 벤치마킹 완료")
            return results[0]
    log("Manus 시간 초과 → Claude 폴백")
    return None


def _claude_research() -> dict:
    return llm.call_json(prompts.CARDNEWS_BENCHMARK, system=prompts.get_system())


def _fmt_md(data: dict) -> str:
    def sec(title, items):
        body = "\n".join(f"- {x}" for x in (items or []) if str(x).strip())
        return f"## {title}\n{body}\n"
    ex = "\n".join(f"- **{e.get('summary','')}** — {e.get('why_viral','')}"
                   for e in data.get("examples", []))
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    return (f"# 카드뉴스 벤치마킹 (갱신: {ts}, 신뢰도: {data.get('confidence','?')})\n\n"
            + sec("지금 뜨는 흐름", data.get("trends"))
            + sec("후킹(표지) 패턴", data.get("hook_patterns"))
            + sec("전개 구조 패턴", data.get("structure_patterns"))
            + sec("시각 요소 패턴", data.get("visual_patterns"))
            + sec("캡션·CTA 패턴", data.get("caption_cta_patterns"))
            + sec("피할 요소", data.get("avoid"))
            + f"## 터진 사례\n{ex}\n")


def research() -> dict:
    data = _manus_research() or _claude_research()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(_fmt_md(data), encoding="utf-8")
    log(f"저장 완료 → {MD_PATH}")
    return data


def load(max_age_days: int = 45) -> str:
    """벤치마크 마크다운을 읽어 반환. 없거나 너무 오래됐으면 ''(주입 생략)."""
    if not MD_PATH.exists():
        return ""
    age_days = (time.time() - MD_PATH.stat().st_mtime) / 86400
    if age_days > max_age_days:
        return ""
    return MD_PATH.read_text(encoding="utf-8")


if __name__ == "__main__":
    research()
