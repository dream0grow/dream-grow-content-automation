from packages.generators import REGISTRY
from packages.generators.base import GeneratedContent, GeneratorContext


def fake_llm(prompt, *, system=None, model="sonnet", max_tokens=4096):
    return GeneratedContent(
        body_md=f"[{model}] {prompt[:30]}",
        model=f"claude-fake-{model}",
        tokens_in=10, tokens_out=20,
    )


def test_thread_generator_returns_content():
    ctx = GeneratorContext(topic="초등 수학", channel="thread", category="수학")
    result = REGISTRY["thread"](ctx, fake_llm)
    assert isinstance(result, GeneratedContent)
    assert result.body_md
    assert "opus" in result.model


def test_all_channels_callable():
    for channel, fn in REGISTRY.items():
        ctx = GeneratorContext(topic="테스트", channel=channel,
                               magnet_type="checklist")
        result = fn(ctx, fake_llm)
        assert isinstance(result, GeneratedContent)
        assert result.body_md
