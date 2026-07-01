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

from orchestrator.config import MODEL_UTILITY, MODEL_WRITING

API_URL = "https://api.anthropic.com/v1/messages"


def call(prompt: str, system: str = "", model: str = "", max_tokens: int = 4096) -> str:
    """프롬프트를 실행하고 텍스트를 반환한다."""
    model = model or MODEL_UTILITY
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        resp = requests.post(
            API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")

    # 로컬 폴백: Claude Max 구독 CLI
    from claude_client import claude_call
    return claude_call(prompt, model=model, system=system or None)


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
              max_tokens: int = 4096, retries: int = 2) -> dict:
    """JSON 응답을 요구하는 호출. 파싱 실패 시 복구·재요청으로 총 retries+1회 시도한다.

    LLM은 가끔 문자열 안 따옴표 미이스케이프 등 깨진 JSON을 내므로,
    한 번의 실패로 파이프라인 전체가 죽지 않게 한다.
    """
    last_err: Exception | None = None
    ask = prompt
    for attempt in range(retries + 1):
        text = call(ask, system=system, model=model, max_tokens=max_tokens)
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
