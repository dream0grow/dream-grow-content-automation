"""Claude 와이드 리서치(claude_research.py)와 llm 웹 검색 배선 테스트.

실행: python3 -m pytest orchestrator/test_claude_research.py -q
"""
import types

from orchestrator import claude_research, llm


def test_build_prompt_mentions_search_when_enabled(monkeypatch):
    monkeypatch.setattr(claude_research, "WEB_SEARCH_MAX_USES", 6)
    p = claude_research.build_prompt("받아쓰기", "초등 학부모", "학술 근거")
    assert "웹 검색을 실제로 수행" in p and "최대 6회" in p and "받아쓰기" in p
    monkeypatch.setattr(claude_research, "WEB_SEARCH_MAX_USES", 0)
    p0 = claude_research.build_prompt("받아쓰기", "초등 학부모", "학술 근거")
    assert "웹 검색 없이" in p0


def test_run_parallel_keeps_successes_and_skips_failures(monkeypatch):
    calls = []

    def fake_call_json(prompt, system="", max_tokens=0, web_search=False, **k):
        calls.append(web_search)
        if "부모 커뮤니티" in prompt:
            raise ValueError("깨진 JSON")
        if "트렌드" in prompt:
            return {"key_findings": []}  # 비어 있음 → 제외
        return {"key_findings": ["근거1"], "source_links": ["https://x"]}

    monkeypatch.setattr(claude_research.llm, "call_json", fake_call_json)
    monkeypatch.setattr(claude_research.prompts, "get_system", lambda: "sys")
    out = claude_research.run("주제", "학부모")
    assert len(out) == 1 and out[0]["key_findings"] == ["근거1"]
    assert out[0]["research_focus"].startswith("학술")   # 누락 시 관점명 보충
    assert calls and all(calls)                            # 전부 웹 검색 켜고 호출


def test_llm_api_path_adds_web_search_tool_and_resumes_pause_turn(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(llm, "WEB_SEARCH_MAX_USES", 4)
    bodies = []
    responses = [
        {"stop_reason": "pause_turn",
         "content": [{"type": "server_tool_use", "id": "s1"},
                     {"type": "web_search_tool_result", "content": []}]},
        {"stop_reason": "end_turn",
         "content": [{"type": "web_search_tool_result", "content": []},
                     {"type": "text", "text": "최종 "}, {"type": "text", "text": "답"}]},
    ]

    def fake_post(url, headers=None, json=None, timeout=0):
        bodies.append(json)
        data = responses[len(bodies) - 1]
        return types.SimpleNamespace(raise_for_status=lambda: None, json=lambda: data)

    monkeypatch.setattr(llm.requests, "post", fake_post)
    out = llm.call("질문", system="s", web_search=True)
    assert out == "최종 답"
    assert bodies[0]["tools"] == [{"type": "web_search_20260209", "name": "web_search",
                                   "max_uses": 4}]
    assert len(bodies) == 2 and bodies[1]["messages"][1]["role"] == "assistant"


def test_llm_api_path_without_search_has_no_tools(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=0):
        seen.update(json)
        return types.SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]})

    monkeypatch.setattr(llm.requests, "post", fake_post)
    assert llm.call("q") == "ok"
    assert "tools" not in seen


def test_llm_cli_path_allows_web_tools(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "WEB_SEARCH_MAX_USES", 3)
    import claude_client
    cmds = []

    def fake_run(cmd, input=None, capture_output=True, text=True, timeout=0, env=None):
        cmds.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="cli ok", stderr="")

    monkeypatch.setattr(claude_client.subprocess, "run", fake_run)
    assert llm.call("q", model="claude-sonnet-5", web_search=True) == "cli ok"
    cmd = cmds[0]
    assert cmd[:4] == ["claude", "-p", "--model", "sonnet"]
    i = cmd.index("--allowedTools")
    assert cmd[i + 1:i + 3] == ["WebSearch", "WebFetch"]
    llm.call("q", web_search=False)
    assert "--allowedTools" not in cmds[1]


def test_manus_available_requires_explicit_provider(monkeypatch):
    from orchestrator import manus_research
    monkeypatch.setattr(manus_research, "MANUS_API_KEY", "key")
    monkeypatch.setattr(manus_research, "RESEARCH_PROVIDER", "claude")
    assert manus_research.available() is False
    monkeypatch.setattr(manus_research, "RESEARCH_PROVIDER", "manus")
    assert manus_research.available() is True
