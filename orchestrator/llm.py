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


def call_json(prompt: str, system: str = "", model: str = "", max_tokens: int = 4096) -> dict:
    """JSON 응답을 요구하는 호출. 코드펜스를 벗겨내고 파싱한다."""
    text = call(prompt, system=system, model=model, max_tokens=max_tokens)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"JSON 파싱 실패: {text[:200]}")
    return json.loads(match.group(0))
