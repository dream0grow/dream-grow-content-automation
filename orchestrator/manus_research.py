"""Manus API 연동 - 외부 리서치 전담 (설계 결정 #3)

Manus는 리서치 stage에서만 호출한다. 키워드/브리프/초안/검수는 모두 Claude.
MANUS_API_KEY가 없으면 Claude 리서치로 자동 폴백하므로 시스템은 항상 동작한다.
"""
import json
import os
import time

import requests

from orchestrator import llm, prompts
from orchestrator.config import MANUS_API_BASE, MANUS_API_KEY

RESEARCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "research_focus", "key_findings", "source_links", "parent_language",
        "content_opportunities", "risk_notes", "confidence",
    ],
    "properties": {
        "research_focus": {"type": "string"},
        "key_findings": {"type": "array", "items": {"type": "string"}},
        "source_links": {"type": "array", "items": {"type": "string"}},
        "parent_language": {"type": "array", "items": {"type": "string"}},
        "content_opportunities": {"type": "array", "items": {"type": "string"}},
        "risk_notes": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
}


def available() -> bool:
    return bool(MANUS_API_KEY)


def _headers() -> dict:
    return {"x-manus-api-key": MANUS_API_KEY, "Content-Type": "application/json"}


# Manus API가 429(레이트리밋)/5xx를 줄 때 지수 백오프로 재시도한다.
# 카드를 한꺼번에 처리하면 task.create 버스트가 레이트리밋에 걸리므로 필수.
MANUS_MAX_RETRIES = int(os.getenv("DG_MANUS_MAX_RETRIES", "4"))
MANUS_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """429/5xx 응답에 지수 백오프(2,4,8,16초) 재시도. Retry-After 헤더를 우선 존중한다."""
    delay = 2.0
    resp = None
    for attempt in range(MANUS_MAX_RETRIES):
        resp = requests.request(method, url, **kwargs)
        if resp.status_code not in MANUS_RETRY_STATUSES:
            return resp
        if attempt == MANUS_MAX_RETRIES - 1:
            break
        retry_after = resp.headers.get("Retry-After", "")
        wait = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else delay
        time.sleep(wait)
        delay *= 2
    return resp


def create_research_tasks(content_id: str, topic: str, audience: str) -> list[str]:
    """관점이 다른 리서치 task 3개를 병렬 생성하고 task_id 목록을 반환한다."""
    task_ids = []
    for focus in prompts.RESEARCH_FOCUSES:
        body = {
            "title": f"DG Research - {content_id} - {focus[:20]}",
            "locale": "ko",
            "ask_followup": False,
            "is_hidden": True,
            "share_visibility": "private",
            "message": {
                "content": prompts.RESEARCH.format(
                    topic=topic, audience=audience or "초등 학부모", focus=focus,
                )
            },
            "structured_output_schema": RESEARCH_SCHEMA,
        }
        resp = _request_with_retry(
            "POST", f"{MANUS_API_BASE}/v2/task.create",
            headers=_headers(), json=body, timeout=60,
        )
        resp.raise_for_status()
        task_ids.append(resp.json()["task_id"])
        time.sleep(1)  # task.create 버스트 완화 (레이트리밋 회피)
    return task_ids


def poll_results(task_ids: list[str]) -> tuple[bool, list[dict], str]:
    """task들의 완료 여부와 structured output을 확인한다.

    Returns: (모두 완료 여부, 완료된 결과 목록, 디버그 문자열)
    디버그에는 응답 status와 top-level 키를 남겨 응답형식 불일치를 추적한다.
    """
    results = []
    all_done = True
    debug_parts = []
    for task_id in task_ids:
        resp = _request_with_retry(
            "GET", f"{MANUS_API_BASE}/v2/task.listMessages",
            headers=_headers(), params={"task_id": task_id}, timeout=60,
        )
        if resp.status_code >= 400:
            all_done = False
            debug_parts.append(f"{task_id[:8]}=HTTP {resp.status_code}:{resp.text[:120]}")
            continue
        try:
            data = resp.json()
        except ValueError:
            all_done = False
            debug_parts.append(f"{task_id[:8]}=비JSON응답")
            continue
        output = _extract_structured_output(data)
        if output:
            results.append(output)
        else:
            all_done = False
            keys = ",".join(list(data.keys())[:6]) if isinstance(data, dict) else type(data).__name__
            debug_parts.append(f"{task_id[:8]}=출력없음(keys:{keys})")
    return all_done, results, " | ".join(debug_parts)


def _extract_structured_output(data: dict) -> dict | None:
    """listMessages 응답에서 structured output을 찾는다."""
    detail = data.get("task_detail") or {}
    so = detail.get("structured_output") or data.get("structured_output") or {}
    if so.get("success") and so.get("value"):
        return so["value"]
    # 메시지 목록 기반 응답 형식 폴백
    for msg in reversed(data.get("messages", [])):
        msg_so = (msg.get("structured_output") or {})
        if msg_so.get("success") and msg_so.get("value"):
            return msg_so["value"]
    # listMessages가 구조화 출력을 직접 안 주는 경우: 마지막 메시지 텍스트에서 JSON 파싱
    import json as _json
    import re as _re
    for msg in reversed(data.get("messages", [])):
        content = msg.get("content")
        text = content if isinstance(content, str) else ""
        if isinstance(content, list):
            text = " ".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in content
            )
        if not text:
            continue
        match = _re.search(r"\{.*\}", text, _re.DOTALL)
        if match:
            try:
                obj = _json.loads(match.group(0))
                if isinstance(obj, dict) and obj.get("key_findings"):
                    return obj
            except ValueError:
                continue
    return None


def claude_research_fallback(topic: str, audience: str) -> list[dict]:
    """Manus 키가 없을 때 Claude가 관점 3개 리서치를 수행한다 (웹 접근 없이 지식 기반)."""
    results = []
    for focus in prompts.RESEARCH_FOCUSES:
        prompt = prompts.RESEARCH.format(
            topic=topic, audience=audience or "초등 학부모", focus=focus,
        ) + "\n\n주의: 웹 검색 없이 작성하므로 확신할 수 없는 출처는 적지 말고, confidence를 보수적으로 매기세요."
        try:
            results.append(llm.call_json(prompt, system=prompts.get_system()))
        except (ValueError, json.JSONDecodeError):
            continue
    return results
