"""Claude 와이드 리서치 — 리서치 stage의 기본 제공자 (Manus 대체, 2026-09-14)

주제 하나를 관점 3개(학술 근거 / 부모 커뮤니티 언어 / 콘텐츠 트렌드, prompts.RESEARCH_FOCUSES)로
나눠 Claude에게 **병렬**로 묻는다. 각 호출은 웹 검색을 켠 채(llm.call_json(web_search=True))
실제 출처를 찾아 JSON(prompts.RESEARCH 형식)으로 답한다. 검색이 꺼져 있으면
(DG_WEB_SEARCH_MAX_USES=0) 지식 기반으로 답하되 출처를 보수적으로 적도록 지시한다.

Manus와 달리 외부 task 폴링이 없어 intake 한 번에 리서치가 끝나고 바로 keyword 단계로 간다.
관점 하나가 실패해도 나머지로 진행한다(전부 실패면 빈 목록 → 호출부가 판단).
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

from orchestrator import llm, prompts
from orchestrator.config import WEB_SEARCH_MAX_USES

# 관점 3개를 동시에 돌린다. 레이트리밋이 걱정되면 DG_RESEARCH_PARALLEL=1.
PARALLEL = int(os.getenv("DG_RESEARCH_PARALLEL") or "3")

_SEARCH_NOTE = (
    "\n\n조사 방법: 웹 검색을 실제로 수행해 근거를 찾으세요. 검색 횟수는 최대 {n}회이니 "
    "'{topic} 초등' 같은 한국어 질의와 영어 학술 질의를 섞어 쓰세요. source_links에는 검색으로 "
    "확인한 실제 URL만 적고, 확인하지 못한 출처는 적지 마세요. 최종 답변은 설명 없이 JSON만 출력하세요."
)
_NO_SEARCH_NOTE = (
    "\n\n주의: 웹 검색 없이 작성하므로 확신할 수 없는 출처는 적지 말고, "
    "confidence를 보수적으로 매기세요. 설명 없이 JSON만 출력하세요."
)


def log(msg: str):
    print(f"[claude-research] {msg}", flush=True)


def build_prompt(topic: str, audience: str, focus: str) -> str:
    base = prompts.RESEARCH.format(
        topic=topic, audience=audience or "초등 학부모", focus=focus,
    )
    if WEB_SEARCH_MAX_USES > 0:
        return base + _SEARCH_NOTE.format(n=WEB_SEARCH_MAX_USES, topic=topic)
    return base + _NO_SEARCH_NOTE


def research_focus(topic: str, audience: str, focus: str) -> dict | None:
    """관점 하나를 조사한다. JSON 파싱까지 실패하면 None."""
    try:
        result = llm.call_json(
            build_prompt(topic, audience, focus), system=prompts.get_system(),
            max_tokens=6000, web_search=True,
        )
    except (ValueError, json.JSONDecodeError, RuntimeError) as e:
        log(f"관점 실패({focus[:20]}): {type(e).__name__}: {str(e)[:120]}")
        return None
    if not isinstance(result, dict) or not result.get("key_findings"):
        log(f"관점 결과 비어 있음({focus[:20]})")
        return None
    result.setdefault("research_focus", focus)
    return result


def run(topic: str, audience: str, focuses: list[str] | None = None) -> list[dict]:
    """관점별 리서치를 병렬로 수행해 결과 목록(성공분만)을 반환한다."""
    focuses = list(focuses or prompts.RESEARCH_FOCUSES)
    workers = max(1, min(PARALLEL, len(focuses)))
    mode = f"웹검색 최대 {WEB_SEARCH_MAX_USES}회" if WEB_SEARCH_MAX_USES > 0 else "지식 기반"
    log(f"'{topic[:30]}' 관점 {len(focuses)}개 병렬 {workers} ({mode})")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outs = list(pool.map(lambda f: research_focus(topic, audience, f), focuses))
    results = [r for r in outs if r]
    log(f"완료 {len(results)}/{len(focuses)}")
    return results
