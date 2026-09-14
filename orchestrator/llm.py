"""LLM 호출 wrapper - 클라우드(API 키)와 로컬(Claude Max CLI) 양쪽 지원

GitHub Actions에서는 ANTHROPIC_API_KEY로 API를 직접 호출하고,
로컬 Mac에서는 키가 없으면 기존 claude_client(Claude Max 구독 CLI)로 폴백한다.
"""
import json
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.config import MODEL_UTILITY, MODEL_WRITING, WEB_SEARCH_MAX_USES

API_URL = "https://api.anthropic.com/v1/messages"

# 서버 도구 웹 검색(Messages API). 결과 블록(web_search_tool_result)은 text 블록만 모으면
# 자연히 걸러진다. 서버 도구가 턴을 잠시 멈추면(pause_turn) 같은 대화를 이어 보낸다.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
CLI_WEB_TOOLS = ["WebSearch", "WebFetch"]
_PAUSE_TURN_MAX = 4


def _api_headers(api_key: str) -> dict:
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def _api_call(body: dict) -> dict:
    resp = requests.post(API_URL, headers=_api_headers(os.environ["ANTHROPIC_API_KEY"]),
                         json=body, timeout=600)
    resp.raise_for_status()
    return resp.json()


def call(prompt: str, system: str = "", model: str = "", max_tokens: int = 4096,
         web_search: bool = False) -> str:
    """프롬프트를 실행하고 텍스트를 반환한다.

    web_search=True면 Claude가 실제 웹을 검색해 답한다 — API 키 경로는 서버 도구
    web_search, CLI(Claude Max) 경로는 WebSearch/WebFetch 허용. DG_WEB_SEARCH_MAX_USES=0이면
    검색 없이 지식 기반으로만 답한다.
    """
    model = model or MODEL_UTILITY
    use_search = web_search and WEB_SEARCH_MAX_USES > 0
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        if use_search:
            body["tools"] = [dict(WEB_SEARCH_TOOL, max_uses=WEB_SEARCH_MAX_USES)]
        data = _api_call(body)
        # 서버 도구는 긴 검색 중 pause_turn으로 턴을 끊을 수 있다 → 그대로 이어 보낸다.
        for _ in range(_PAUSE_TURN_MAX):
            if data.get("stop_reason") != "pause_turn":
                break
            body["messages"] = body["messages"] + [
                {"role": "assistant", "content": data["content"]}]
            data = _api_call(body)
        return "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")

    # 로컬/Actions(Claude Max 구독) 폴백: Claude Code CLI
    from claude_client import claude_call
    return claude_call(prompt, model=model, system=system or None,
                       tools=CLI_WEB_TOOLS if use_search else None)


def call_vision(prompt: str, image_bytes: bytes, media_type: str = "image/jpeg",
                model: str = "", max_tokens: int = 2048) -> str:
    """이미지 + 프롬프트 호출 (썸네일 OCR·그림 분석). API 키 없으면 빈 문자열.

    로컬 Claude Max CLI 폴백은 이미지 입력을 못 받으므로, 호출부는 빈 반환을
    "비전 불가"로 보고 텍스트 정보만으로 진행해야 한다.
    """
    import base64
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return ""
    body = {
        "model": model or MODEL_UTILITY,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {
                "type": "base64", "media_type": media_type,
                "data": base64.b64encode(image_bytes).decode()}},
            {"type": "text", "text": prompt},
        ]}],
    }
    resp = requests.post(
        API_URL,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json=body, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    return "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")


def call_writing(prompt: str, system: str = "", max_tokens: int = 8000) -> str:
    """글쓰기 품질이 중요한 호출 (작가/브리프)."""
    return call(prompt, system=system, model=MODEL_WRITING, max_tokens=max_tokens)


def _extract_balanced_json(text: str) -> str | None:
    """첫 '{'부터 중괄호 짝이 맞는 지점까지 잘라낸다 (JSON 뒤에 붙은 설명문 무시)."""
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _try_parse(raw: str) -> dict | None:
    """그대로 파싱 → 안 되면 가벼운 복구(후행 쉼표·스마트따옴표) 후 재시도."""
    for candidate in (
        raw,
        re.sub(r",\s*([}\]])", r"\1", raw),                       # 후행 쉼표 제거
        re.sub(r",\s*([}\]])", r"\1", raw)
          .replace("“", '\\"').replace("”", '\\"'),      # 스마트 따옴표
    ):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def call_json(prompt: str, system: str = "", model: str = "",
              max_tokens: int = 4096, retries: int = 2, web_search: bool = False) -> dict:
    """JSON 응답을 요구하는 호출. 파싱 실패 시 복구·재요청으로 총 retries+1회 시도한다.

    LLM은 가끔 문자열 안 따옴표 미이스케이프 등 깨진 JSON을 내므로,
    한 번의 실패로 파이프라인 전체가 죽지 않게 한다.
    """
    last_err: Exception | None = None
    ask = prompt
    for attempt in range(retries + 1):
        text = call(ask, system=system, model=model, max_tokens=max_tokens,
                    web_search=web_search)
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        raw = _extract_balanced_json(cleaned) or ""
        if raw:
            obj = _try_parse(raw)
            if obj is not None:
                return obj
            last_err = ValueError(f"파싱 불가 JSON: {raw[:200]}")
        else:
            last_err = ValueError(f"JSON 없음: {text[:200]}")
        ask = (
            prompt
            + "\n\n[재요청] 직전 응답이 유효한 JSON이 아니었습니다. 설명 없이 유효한 JSON "
            '객체만 출력하세요. 문자열 안의 큰따옴표는 반드시 \\" 로 이스케이프하고, '
            "후행 쉼표를 넣지 마세요."
        )
    raise ValueError(f"JSON 파싱 실패({retries + 1}회 시도): {last_err}")
