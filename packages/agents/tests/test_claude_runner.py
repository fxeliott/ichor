"""Tests for the Claude path of FallbackChain (ADR-021).

Covers:
  - ClaudeRunnerConfig.from_env: returns None when env incomplete,
    returns config when all 3 vars set
  - _strip_json_fence: handles plain JSON, ```json``` fence, and ``` fence
  - call_agent_task: parses success body, validates Pydantic, raises
    on HTTP error / status!=success / invalid JSON
  - FallbackChain integration: tries Claude first, falls back on
    ClaudeRunnerError

No network calls — httpx is mocked via httpx.MockTransport.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import httpx
import pytest
from ichor_agents.claude_runner import (
    _AGENT_MODE_OVERRIDE_PREFIX,
    ClaudeRunnerConfig,
    ClaudeRunnerError,
    ClaudeRunnerOutputError,
    _extract_first_balanced_json,
    _schema_hint,
    _strip_json_fence,
    _wrap_system_prompt_with_agent_override,
    call_agent_task,
)
from ichor_agents.fallback import AllProvidersFailed, FallbackChain
from pydantic import BaseModel, Field


class _Out(BaseModel):
    answer: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)


# ── ClaudeRunnerConfig.from_env ────────────────────────────────────


def test_from_env_returns_none_when_url_missing() -> None:
    with patch.dict(
        os.environ,
        {
            "ICHOR_API_CLAUDE_RUNNER_URL": "",
            "ICHOR_API_CF_ACCESS_CLIENT_ID": "id",
            "ICHOR_API_CF_ACCESS_CLIENT_SECRET": "secret",
        },
        clear=True,
    ):
        assert ClaudeRunnerConfig.from_env() is None


def test_from_env_returns_config_without_cf_creds_when_url_set() -> None:
    """Runner can be deployed in dev mode (no CF Access). When the URL
    is set, we route through Claude even without service-token creds —
    the runner itself decides whether to enforce auth."""
    with patch.dict(
        os.environ,
        {
            "ICHOR_API_CLAUDE_RUNNER_URL": "https://runner.example.com",
            "ICHOR_API_CF_ACCESS_CLIENT_ID": "",
            "ICHOR_API_CF_ACCESS_CLIENT_SECRET": "",
        },
        clear=True,
    ):
        cfg = ClaudeRunnerConfig.from_env()
    assert cfg is not None
    assert cfg.runner_url == "https://runner.example.com"
    assert cfg.cf_access_client_id is None
    assert cfg.cf_access_client_secret is None


def test_from_env_returns_config_when_all_set() -> None:
    with patch.dict(
        os.environ,
        {
            "ICHOR_API_CLAUDE_RUNNER_URL": "https://runner.example.com/",
            "ICHOR_API_CF_ACCESS_CLIENT_ID": "id123",
            "ICHOR_API_CF_ACCESS_CLIENT_SECRET": "secret456",
        },
        clear=True,
    ):
        cfg = ClaudeRunnerConfig.from_env(model="haiku", effort="low")
    assert cfg is not None
    assert cfg.runner_url == "https://runner.example.com"  # trailing slash stripped
    assert cfg.cf_access_client_id == "id123"
    assert cfg.cf_access_client_secret == "secret456"
    assert cfg.model == "haiku"
    assert cfg.effort == "low"


# ── _strip_json_fence ────────────────────────────────────────────────


def test_strip_fence_plain_json() -> None:
    assert _strip_json_fence('{"a": 1}') == '{"a": 1}'


def test_strip_fence_with_json_label() -> None:
    text = '```json\n{"a": 1}\n```'
    assert _strip_json_fence(text) == '{"a": 1}'


def test_strip_fence_without_label() -> None:
    text = '```\n{"a": 1}\n```'
    assert _strip_json_fence(text) == '{"a": 1}'


def test_strip_fence_handles_leading_trailing_whitespace() -> None:
    text = '  \n```json\n{"x": "y"}\n```  \n'
    assert _strip_json_fence(text) == '{"x": "y"}'


# ── trailing tool-envelope leak (macro Couche-2, witnessed 2026-06-03) ──
# Opus 4.8 intermittently appends tool-call XML scaffolding (</invoke>,
# </parameter>) AFTER an otherwise-valid JSON object. Pre-fix, when the
# text STARTED with `{`, _strip_json_fence skipped balanced extraction and
# returned `{...}</invoke>` verbatim → model_validate_json failed with
# "Invalid JSON: trailing characters". macro failed every cron fire.


def test_strip_fence_strips_trailing_invoke_token_when_starts_with_brace() -> None:
    text = '{"drivers": [{"theme": "monetary_policy"}], "summary": "ok"}</invoke>'
    assert _strip_json_fence(text) == '{"drivers": [{"theme": "monetary_policy"}], "summary": "ok"}'


def test_strip_fence_strips_trailing_parameter_token() -> None:
    text = '{"a": 1, "b": "x"}\n</parameter>\n</invoke>'
    assert _strip_json_fence(text) == '{"a": 1, "b": "x"}'


def test_strip_fence_strips_leading_prose_and_trailing_tool_token() -> None:
    text = 'Here is the result:\n{"a": 1}\n</invoke>'
    assert _strip_json_fence(text) == '{"a": 1}'


def test_strip_fence_plain_object_with_no_trailing_is_unchanged() -> None:
    # Regression guard : the common happy path must be byte-identical.
    text = '{"k": [1, 2, 3], "nested": {"x": "}"}}'
    assert _strip_json_fence(text) == text


# ── call_agent_task ─────────────────────────────────────────────────


async def _no_op() -> None:
    """Awaitable no-op for monkey-patching asyncio.sleep in retry tests."""
    return None


def _cfg() -> ClaudeRunnerConfig:
    return ClaudeRunnerConfig(
        runner_url="https://runner.example.com",
        cf_access_client_id="id",
        cf_access_client_secret="secret",
        model="sonnet",
        effort="medium",
        timeout_sec=5.0,
    )


@pytest.mark.asyncio
async def test_call_agent_task_returns_validated_pydantic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        # r169 G-fix-Couche2 : system is now wrapped with the
        # [AGENT-MODE-OVERRIDE] prefix to prevent user-scope CLAUDE.md
        # leakage. The original "sys" persona MUST still appear verbatim
        # at the tail of the wrapped block, AND the override preamble
        # MUST be present at the top.
        assert b"[AGENT-MODE-OVERRIDE" in body
        assert b"[ORIGINAL AGENT SYSTEM PROMPT BELOW]" in body
        # The agent persona "sys" lives verbatim AFTER the override block
        # (json-encoded forms ; escaping preserves the trailing literal).
        assert b"sys" in body
        # Prompt is enriched with the JSON schema when output_type is set ;
        # check the original user text appears at the start and the
        # strengthened "OUTPUT CONTRACT" instruction is present.
        assert b'"prompt":"user-prompt' in body
        assert b"OUTPUT CONTRACT" in body  # r169 strengthened schema hint
        assert b"Now output the single JSON object" in body  # r169 JSON priming suffix
        assert request.headers["CF-Access-Client-Id"] == "id"
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": '{"answer": "ok", "score": 0.42}',
                "duration_ms": 1234,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        out = await call_agent_task(_cfg(), system="sys", prompt="user-prompt", output_type=_Out)

    assert isinstance(out, _Out)
    assert out.answer == "ok"
    assert out.score == 0.42


@pytest.mark.asyncio
async def test_call_agent_task_returns_text_when_no_output_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": "free-form markdown",
                "duration_ms": 50,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        out = await call_agent_task(_cfg(), system="sys", prompt="p", output_type=None)
    assert out == "free-form markdown"


@pytest.mark.asyncio
async def test_call_agent_task_raises_on_http_error() -> None:
    """Non-retryable HTTP errors (anything ≥ 400 except 429/503) fail fast."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        with pytest.raises(ClaudeRunnerError, match="HTTP 500"):
            await call_agent_task(_cfg(), system="s", prompt="p", output_type=_Out)


@pytest.mark.asyncio
async def test_call_agent_task_retries_on_503_then_succeeds(monkeypatch) -> None:
    """503 = runner busy; we should retry transparently."""
    monkeypatch.setattr("ichor_agents.claude_runner.asyncio.sleep", lambda *a, **kw: _no_op())

    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(503, text='{"detail":"Another task in flight"}')
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": '{"answer": "ok-after-retry", "score": 0.5}',
                "duration_ms": 50,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        out = await call_agent_task(_cfg(), system="s", prompt="p", output_type=_Out)
    assert out.answer == "ok-after-retry"
    assert state["calls"] == 2  # one 503 + one success


@pytest.mark.asyncio
async def test_call_agent_task_raises_when_status_not_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "subprocess_error",
                "error_message": "claude CLI exited 2",
                "duration_ms": 12,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        with pytest.raises(ClaudeRunnerError, match="subprocess_error"):
            await call_agent_task(_cfg(), system="s", prompt="p", output_type=_Out)


@pytest.mark.asyncio
async def test_call_agent_task_raises_when_output_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": "this is not json at all",
                "duration_ms": 10,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        with pytest.raises(ClaudeRunnerOutputError):
            await call_agent_task(_cfg(), system="s", prompt="p", output_type=_Out)


# ── FallbackChain integration ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fallback_tries_claude_first_when_configured() -> None:
    """Given Claude succeeds, the chain returns the Claude output and
    never invokes any fallback provider."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": '{"answer": "via-claude", "score": 0.9}',
                "duration_ms": 100,
            },
        )

    transport = httpx.MockTransport(handler)
    chain = FallbackChain(
        providers=(),  # no fallback providers — proves Claude is used
        system_prompt="test system prompt over 100 chars " * 5,
        output_type=_Out,
        claude=_cfg(),
        # W67 default is async polling ; the mock above returns the
        # sync-shaped immediate-success body. Force sync path so the
        # mock and the code under test agree on the wire format.
        use_async_endpoint=False,
    )

    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        out = await chain.run("user prompt")

    assert isinstance(out, _Out)
    assert out.answer == "via-claude"


@pytest.mark.asyncio
async def test_fallback_raises_when_claude_fails_and_no_providers() -> None:
    """When Claude fails and there's nothing to fall back on, the chain
    raises AllProvidersFailed and includes 'claude' in the attempts."""

    # 500 = non-retryable; fails fast so the test doesn't burn the
    # 65 s retry budget set up for transient 503/429.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="runner down")

    transport = httpx.MockTransport(handler)
    chain = FallbackChain(
        providers=(),
        system_prompt="test system prompt over 100 chars " * 5,
        output_type=_Out,
        claude=_cfg(),
    )

    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        with pytest.raises(AllProvidersFailed) as exc:
            await chain.run("user prompt")

    names = [name for name, _err in exc.value.attempts]
    assert "claude" in names


# ── r169 G-fix-Couche2 — AGENT_MODE_OVERRIDE + balanced JSON extraction ───


class TestR169AgentModeOverridePrefix:
    """The [AGENT-MODE-OVERRIDE] prefix is the canonical fix for the
    r168 production failure where claude CLI inherited user-scope
    CLAUDE.md rules (self-checklist / tracker / Ready-for-Stop) and
    returned pure prose instead of JSON. Tests pin :
      - the prefix CONTAINS the explicit forbidden patterns
      - the wrapper PREPENDS it to the agent persona (not appends)
      - the prefix is the FIRST text claude sees in the system block
    """

    def test_prefix_contains_explicit_forbidden_patterns(self) -> None:
        """Empirically observed prose patterns from Hetzner journalctl
        MUST be in the forbidden list of the override prefix so claude
        cannot leak them."""
        forbidden = [
            "Self-checklist",
            "Ready for Stop",
            "tracker",
            "Perfect.",
            "Markdown",
        ]
        for marker in forbidden:
            assert marker in _AGENT_MODE_OVERRIDE_PREFIX, (
                f"forbidden marker {marker!r} missing from "
                "_AGENT_MODE_OVERRIDE_PREFIX (regression vs r168 root cause)"
            )

    def test_prefix_declares_highest_priority(self) -> None:
        """The prefix must explicitly assert priority over OTHER rules
        so claude resolves the conflict in favor of the agent contract."""
        assert "HIGHEST PRIORITY" in _AGENT_MODE_OVERRIDE_PREFIX
        assert "OVERRIDES ALL OTHER RULES" in _AGENT_MODE_OVERRIDE_PREFIX

    def test_wrapper_prepends_not_appends(self) -> None:
        """The override MUST be the FIRST text claude sees. If it were
        appended, the user-scope CLAUDE.md rules loaded BEFORE the
        agent persona would already have shaped claude's response mode."""
        original = "You are the Test Agent. Do thing X."
        wrapped = _wrap_system_prompt_with_agent_override(original)
        assert wrapped.startswith("[AGENT-MODE-OVERRIDE")
        assert wrapped.endswith(original)
        assert "[ORIGINAL AGENT SYSTEM PROMPT BELOW]" in wrapped

    def test_wrapper_preserves_original_system_intact(self) -> None:
        """The agent's persona must reach claude verbatim — no
        truncation, no normalization, no escape."""
        original = (
            "Multi-line\n"
            "agent persona with 'quotes' and \"double-quotes\"\n"
            "and unicode é à ü ñ chars.\n"
        )
        wrapped = _wrap_system_prompt_with_agent_override(original)
        assert original in wrapped


class TestR169SchemaHintStrengthened:
    """The schema_hint instruction now enumerates the empirically
    observed forbidden patterns so claude cannot rationalise away the
    no-prose constraint."""

    def test_schema_hint_lists_forbidden_patterns(self) -> None:
        """Mirror of the override prefix : schema hint repeats the
        forbidden patterns at the prompt-tail level for defense in depth."""

        class _Schema(BaseModel):
            x: int

        hint = _schema_hint(_Schema)
        for marker in ["Self-checklist", "Ready for Stop", "Perfect."]:
            assert marker in hint, (
                f"forbidden marker {marker!r} missing from _schema_hint "
                "tail block (defense-in-depth regression)"
            )

    def test_schema_hint_appends_priming_suffix(self) -> None:
        """The 'Now output the single JSON object' primer gives claude
        a clean handoff from prompt-tail to output start."""

        class _Schema(BaseModel):
            x: int

        hint = _schema_hint(_Schema)
        assert "Now output the single JSON object" in hint

    def test_schema_hint_returns_priming_only_for_non_pydantic(self) -> None:
        """When output_type isn't a Pydantic BaseModel, the helper
        still returns the priming suffix so claude doesn't slip into
        prose mode — degrades gracefully without the schema."""
        hint = _schema_hint(int)  # raw int has no model_json_schema
        assert "Now output" in hint


class TestR169BalancedJsonExtractor:
    """Stack-based bracket matcher used as the last-resort fallback
    inside ``_strip_json_fence``. Robust against prose containing stray
    braces (markdown lists, code snippets in explanations)."""

    def test_extracts_first_balanced_object_when_embedded_in_prose(self) -> None:
        text = 'Here is the answer: {"a": 1, "b": 2} and that is all.'
        assert _extract_first_balanced_json(text) == '{"a": 1, "b": 2}'

    def test_returns_none_when_no_brace_anywhere(self) -> None:
        """Production root cause : pure prose with ZERO braces."""
        assert _extract_first_balanced_json("Perfect. Ready for Stop.") is None

    def test_handles_nested_objects_correctly(self) -> None:
        text = 'prefix {"outer": {"inner": 1}, "x": 2} suffix'
        # Outer balanced span = `{"outer": {"inner": 1}, "x": 2}`
        assert _extract_first_balanced_json(text) == '{"outer": {"inner": 1}, "x": 2}'

    def test_ignores_braces_inside_string_literals(self) -> None:
        """Brace inside a JSON string MUST NOT confuse the bracket count."""
        text = '{"name": "has } inside string", "value": 1}'
        assert _extract_first_balanced_json(text) == text

    def test_escaped_quote_does_not_break_string_tracking(self) -> None:
        """Escaped quote (\\\") inside a string must not terminate the
        string scan prematurely."""
        text = '{"q": "she said \\"hi\\""}'
        result = _extract_first_balanced_json(text)
        assert result == text

    def test_strip_json_fence_uses_balanced_extractor_on_prose_with_braces(self) -> None:
        """End-to-end : prose surrounding the JSON object with additional
        braces in trailing markdown — balanced extractor wins over greedy."""
        text = 'prefix {"clean": "json"} suffix {bogus}'
        # Greedy regex `\{.*\}` would capture from first `{` to LAST `}`,
        # returning `{"clean": "json"} suffix {bogus}` which Pydantic
        # would fail. Balanced extractor returns the clean first object.
        stripped = _strip_json_fence(text)
        assert stripped == '{"clean": "json"}'
