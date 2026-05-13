"""Phase D W117a — DSPy ClaudeRunnerLM wrapper unit tests.

Two slices :

1. ALWAYS-RUN tests (no DSPy required) — module is importable, stub
   raises clear error, allowed model tags are pinned, ADR-009 contract
   documented in module docstring.
2. WITH-DSPY tests (skipif marker) — class inherits dspy.BaseLM,
   capability properties match the researcher SOTA brief, forward()
   correctly threads to call_agent_task_async with proper inputs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from ichor_api.services.dspy_claude_runner_lm import (
    _ALLOWED_MODEL_TAGS,
    _DSPY_AVAILABLE,
    _MISSING_DSPY_MSG,
    ClaudeRunnerLM,
)

# ──────────────────────────── always-run (Voie D contract) ──────────


def test_module_importable_without_dspy() -> None:
    """The module MUST be importable even when DSPy isn't installed.
    This is the W90 ADR-009 contract : production code never breaks
    on missing optional deps, gracefully degrades."""
    # If the module imported at the top of this test file, this passes.
    assert _ALLOWED_MODEL_TAGS is not None


def test_allowed_model_tags_are_ichor_sentinels() -> None:
    """ADR-009 critical invariant : the wrapper accepts ONLY sentinel
    model tags `ichor-claude-runner-*`. The actual model selection
    happens via `runner_cfg.model` (ADR-023 Haiku low). Using the raw
    Anthropic model names (`claude-3-haiku-...`) would let DSPy's
    litellm-aware adapters route to paid API.

    This frozenset is the canary : if a future refactor adds
    `claude-haiku-3.5` or similar Anthropic-canonical names, the
    Voie D invariant test catches the regression."""
    assert _ALLOWED_MODEL_TAGS == frozenset(
        {
            "ichor-claude-runner-haiku",
            "ichor-claude-runner-sonnet",
            "ichor-claude-runner-opus",
        }
    )


def test_stub_raises_clear_message_when_dspy_missing() -> None:
    """When DSPy is absent the class is a stub ; instantiation raises
    with an actionable install hint."""
    if _DSPY_AVAILABLE:
        pytest.skip(
            "DSPy is installed in this venv — stub path not exercised "
            "(see test_class_instantiates_with_dspy below)."
        )
    with pytest.raises(RuntimeError, match=r"DSPy 3\.2 not installed"):
        ClaudeRunnerLM(runner_cfg=None)  # type: ignore[call-arg]


def test_missing_dspy_msg_includes_install_command() -> None:
    """The error message MUST point at the right pyproject extras —
    catches a refactor that renames `[phase-d-w117]` without updating
    the hint."""
    assert "phase-d-w117" in _MISSING_DSPY_MSG
    assert "pip install" in _MISSING_DSPY_MSG.lower()


# ──────────────────────────── DSPy-dependent tests ─────────────────────


_requires_dspy = pytest.mark.skipif(
    not _DSPY_AVAILABLE,
    reason="DSPy not installed — run with `pip install -e 'apps/api[phase-d-w117]'`",
)


@_requires_dspy
def test_class_instantiates_with_dspy() -> None:
    """Happy-path : DSPy installed, ClaudeRunnerLM constructs cleanly."""
    from ichor_agents.claude_runner import ClaudeRunnerConfig

    cfg = ClaudeRunnerConfig(
        runner_url="http://localhost:8766",
        model="haiku",
        effort="low",
    )
    lm = ClaudeRunnerLM(runner_cfg=cfg)
    assert lm is not None


@_requires_dspy
def test_class_rejects_unknown_model_tag() -> None:
    """Defensive : if someone tries to use a raw Anthropic model name,
    we 400 at construction. This catches the most likely Voie D
    regression."""
    from ichor_agents.claude_runner import ClaudeRunnerConfig

    cfg = ClaudeRunnerConfig(runner_url="http://localhost:8766")
    for bad in (
        "claude-3-haiku-20240307",
        "claude-3-5-haiku-latest",
        "claude-haiku",
        "haiku",
    ):
        with pytest.raises(ValueError, match=r"not in .*ichor-claude-runner"):
            ClaudeRunnerLM(runner_cfg=cfg, model_tag=bad)


@_requires_dspy
def test_capability_properties_match_sota_brief() -> None:
    """Researcher SOTA brief round-15 specified capability flags so
    DSPy adapters know what NOT to expect from the subprocess path."""
    from ichor_agents.claude_runner import ClaudeRunnerConfig

    lm = ClaudeRunnerLM(runner_cfg=ClaudeRunnerConfig(runner_url="x"))
    assert lm.supports_function_calling is False
    assert lm.supports_reasoning is False
    assert lm.supports_response_schema is False
    assert lm.supported_params == {"temperature", "max_tokens", "stop"}


@_requires_dspy
@pytest.mark.asyncio
async def test_async_forward_calls_call_agent_task_async() -> None:
    """The forward path MUST go through `call_agent_task_async` — the
    canonical W116c Voie D entry point. We patch the function and
    verify it's called with the prompt."""
    from ichor_agents.claude_runner import ClaudeRunnerConfig

    cfg = ClaudeRunnerConfig(runner_url="http://localhost:8766")
    lm = ClaudeRunnerLM(runner_cfg=cfg)

    fake_call = AsyncMock(return_value="hello from claude-runner")

    with patch("ichor_agents.claude_runner.call_agent_task_async", fake_call):
        result = await lm._async_forward(
            prompt="What is 2+2?",
            messages=None,
        )

    fake_call.assert_awaited_once()
    call_kwargs = fake_call.await_args.kwargs
    assert call_kwargs["cfg"] is cfg
    assert call_kwargs["user_prompt"] == "What is 2+2?"
    assert call_kwargs["output_type"] is None
    # Response in litellm shape
    assert result["choices"][0]["message"]["content"] == "hello from claude-runner"


@_requires_dspy
@pytest.mark.asyncio
async def test_async_forward_collapses_messages_to_prompt() -> None:
    """If `messages` is given instead of `prompt`, the wrapper flattens
    them. The claude-runner agent-task endpoint takes (system, user)
    only — multi-turn must collapse."""
    from ichor_agents.claude_runner import ClaudeRunnerConfig

    cfg = ClaudeRunnerConfig(runner_url="http://localhost:8766")
    lm = ClaudeRunnerLM(runner_cfg=cfg)
    fake_call = AsyncMock(return_value="ok")

    with patch("ichor_agents.claude_runner.call_agent_task_async", fake_call):
        await lm._async_forward(
            prompt=None,
            messages=[
                {"role": "user", "content": "first turn"},
                {"role": "assistant", "content": "first reply"},
                {"role": "user", "content": "second turn"},
            ],
        )

    user_prompt = fake_call.await_args.kwargs["user_prompt"]
    assert "first turn" in user_prompt
    assert "first reply" in user_prompt
    assert "second turn" in user_prompt


@_requires_dspy
@pytest.mark.asyncio
async def test_async_forward_maps_context_window_to_dspy_exception() -> None:
    """413 / context-too-large from claude-runner MUST surface as
    `dspy.ContextWindowExceededError` so DSPy's retry/truncation logic
    engages instead of bubbling a raw RuntimeError."""
    import dspy
    from ichor_agents.claude_runner import ClaudeRunnerConfig

    cfg = ClaudeRunnerConfig(runner_url="http://localhost:8766")
    lm = ClaudeRunnerLM(runner_cfg=cfg)
    fake_call = AsyncMock(side_effect=RuntimeError("HTTP 413 context window exceeded"))

    with patch("ichor_agents.claude_runner.call_agent_task_async", fake_call):
        with pytest.raises(dspy.ContextWindowExceededError):
            await lm._async_forward(prompt="x", messages=None)


@_requires_dspy
@pytest.mark.asyncio
async def test_async_forward_propagates_other_runner_errors() -> None:
    """Non-context-window failures bubble up unchanged (DSPy retry
    catches them at a higher level)."""
    from ichor_agents.claude_runner import ClaudeRunnerConfig

    cfg = ClaudeRunnerConfig(runner_url="http://localhost:8766")
    lm = ClaudeRunnerLM(runner_cfg=cfg)
    fake_call = AsyncMock(side_effect=RuntimeError("CF tunnel 530 transient"))

    with patch("ichor_agents.claude_runner.call_agent_task_async", fake_call):
        with pytest.raises(RuntimeError, match=r"CF tunnel 530"):
            await lm._async_forward(prompt="x", messages=None)
