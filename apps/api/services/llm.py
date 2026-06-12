"""LLM service — wraps Anthropic SDK (HTTP API) with optional Claude CLI fallback.

Drops the legacy hardcoded /Users/lhg/... CLAUDE_BIN path. If ANTHROPIC_API_KEY
is set, uses the SDK directly. Otherwise tries the `claude` CLI from PATH or
the explicit CLAUDE_BIN env var.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from packages.generators.base import GeneratedContent

DEFAULT_MODEL_MAP = {
    "opus": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}


def _resolve_model(model: str) -> str:
    return DEFAULT_MODEL_MAP.get(model, DEFAULT_MODEL_MAP["sonnet"])


def _api_call(prompt: str, system: str | None, model: str, max_tokens: int) -> GeneratedContent:
    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=_resolve_model(model),
        max_tokens=max_tokens,
        system=system or anthropic.NOT_GIVEN,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "text") == "text")
    return GeneratedContent(
        body_md=text.strip(),
        model=msg.model,
        tokens_in=msg.usage.input_tokens,
        tokens_out=msg.usage.output_tokens,
    )


def _cli_call(prompt: str, system: str | None, model: str, timeout: int = 600) -> GeneratedContent:
    binary = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not binary:
        raise RuntimeError("No ANTHROPIC_API_KEY and no claude CLI available")
    cmd = [binary, "-p", "--model", model]
    if system:
        cmd.extend(["--append-system-prompt", system])
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(cmd, input=prompt, capture_output=True,
                            text=True, timeout=timeout, env=env, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error ({result.returncode}): {result.stderr}")
    return GeneratedContent(body_md=result.stdout.strip(), model=f"cli:{model}")


def llm_call(
    prompt: str,
    *,
    system: str | None = None,
    model: str = "sonnet",
    max_tokens: int = 4096,
) -> GeneratedContent:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _api_call(prompt, system, model, max_tokens)
    return _cli_call(prompt, system, model)
