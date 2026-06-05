"""Claude Max 구독 기반 LLM 호출 wrapper

API 크레딧 대신 Claude Code CLI를 사용합니다.
Claude Max 200 구독 인증 세션을 재사용하므로 크레딧 소비 없음.

적용 방법 (기존 코드 1줄 추가):
  import claude_client; claude_client.patch_anthropic()
  import anthropic  # 이제 Claude Max 사용

직접 호출:
  from claude_client import claude_call
  text = claude_call("프롬프트", model="sonnet")
"""
import os
import subprocess
from dataclasses import dataclass, field

CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")

MODEL_MAP = {
    "claude-opus-4-6": "opus",
    "claude-sonnet-4-20250514": "sonnet",
    "claude-sonnet-4-6": "sonnet",
    "claude-haiku-4-5-20251001": "haiku",
    "claude-3-5-sonnet-20241022": "sonnet",
    "claude-3-5-haiku-20241022": "haiku",
    "opus": "opus",
    "sonnet": "sonnet",
    "haiku": "haiku",
}


def claude_call(
    prompt: str,
    model: str = "sonnet",
    system: str | None = None,
    timeout: int = 600,
) -> str:
    cli_model = MODEL_MAP.get(model, "sonnet")
    cmd = [CLAUDE_BIN, "-p", "--model", cli_model]
    if system:
        cmd.extend(["--append-system-prompt", system])
    env = {k: v for k, v in __import__("os").environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=timeout, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error ({result.returncode}): {result.stderr}")
    return result.stdout.strip()


@dataclass
class _ContentBlock:
    text: str
    type: str = "text"

@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0

@dataclass
class _Message:
    content: list
    model: str = "sonnet"
    role: str = "assistant"
    stop_reason: str = "end_turn"
    usage: _Usage = field(default_factory=_Usage)


class _Messages:
    def create(self, model="sonnet", max_tokens=4096, messages=None, system=None, **kw):
        if not messages:
            raise ValueError("messages required")
        parts = []
        for msg in messages:
            c = msg.get("content", "")
            if isinstance(c, list):
                c = "\n".join(b.get("text", "") for b in c if b.get("type") == "text")
            if msg.get("role") == "user":
                parts.append(c)
            elif msg.get("role") == "assistant":
                parts.append(f"[이전 답변]\n{c}")
        text = claude_call("\n\n".join(parts), model=model, system=system)
        return _Message(content=[_ContentBlock(text=text)], model=model)


class Anthropic:
    """anthropic.Anthropic 호환. API 키 대신 Claude Max 구독 사용."""
    def __init__(self, api_key=None, **kw):
        self.messages = _Messages()

class BadRequestError(Exception):
    pass

class APIError(Exception):
    pass


def patch_anthropic():
    """import anthropic이 Claude Max CLI를 쓰도록 패치."""
    import sys, types
    mod = types.ModuleType("anthropic")
    mod.Anthropic = Anthropic
    mod.BadRequestError = BadRequestError
    mod.APIError = APIError
    sys.modules["anthropic"] = mod


if __name__ == "__main__":
    print("=== 테스트 ===")
    r = claude_call("'테스트 성공'이라고만 답해.", model="haiku")
    print(f"claude_call: {r}")
    client = Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=50,
        messages=[{"role": "user", "content": "2+2=?"}],
    )
    print(f"Anthropic 호환: {msg.content[0].text}")
