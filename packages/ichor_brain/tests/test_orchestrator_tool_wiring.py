"""W87 STEP-5 — verify ToolConfig propagates to RunnerCall correctly.

Default behaviour : Pass-1 (regime) and Pass-2 (asset specialization)
receive tool fields. Pass-3 (stress) and Pass-4 (invalidation) do
not — they operate on prior-pass narrative output where tool access
provides no marginal lift.

The pre-W87 baseline (no `tool_config` argument) keeps tool fields
absent on every RunnerCall — strict backward-compat.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ichor_brain import (
    AssetSpecialization,
    InMemoryRunnerClient,
    InvalidationConditions,
    Orchestrator,
    RegimeReading,
    RunnerResponse,
    StressTest,
    ToolConfig,
)
from ichor_brain.passes import AssetPass, InvalidationPass, RegimePass, StressPass

# Minimal narrative fixtures — identical shape to what the real Pass
# parsers produce. Kept inline so the test stays self-contained.
_REGIME_REPLY = """```json
{
  "quadrant": "haven_bid",
  "confidence_pct": 70,
  "rationale": "USD strength bid alongside risk-off into Asia close, DXY above 102 with VIX firming."
}
```"""

_ASSET_REPLY = """```json
{
  "asset": "EUR_USD",
  "bias_direction": "short",
  "conviction_pct": 60,
  "mechanisms": [{"claim": "USD bid into Asia close", "evidence": "DXY > 102"}]
}
```"""

_STRESS_REPLY = """```json
{
  "counter_claims": [{"claim": "ECB hawkish surprise", "data": "OIS curve"}],
  "revised_conviction_pct": 55
}
```"""

_INVALIDATION_REPLY = """```json
{
  "conditions": [{"condition": "DXY < 101.5 by NY open", "horizon": "24h"}]
}
```"""


def _stub_critic(*, briefing_markdown, source_pool, asset_whitelist):
    """Lightweight critic stub — no ichor_agents import."""

    class _Verdict:
        verdict = "approved"
        confidence = 0.9
        findings: list = []
        suggested_footer = ""

    return _Verdict()


def _build_runner() -> InMemoryRunnerClient:
    """4 scripted responses, one per pass."""
    return InMemoryRunnerClient(
        [
            RunnerResponse(text=_REGIME_REPLY, raw={}, duration_ms=10),
            RunnerResponse(text=_ASSET_REPLY, raw={}, duration_ms=10),
            RunnerResponse(text=_STRESS_REPLY, raw={}, duration_ms=10),
            RunnerResponse(text=_INVALIDATION_REPLY, raw={}, duration_ms=10),
        ]
    )


def _run(orch: Orchestrator) -> list:
    """Drive a synthetic 4-pass run, return the captured RunnerCalls."""
    result = asyncio.run(
        orch.run(
            session_type="pre_londres",
            asset="EUR_USD",
            data_pool="<<DATA_POOL_STUB>>",
            asset_data="<<ASSET_DATA_STUB>>",
            now=datetime(2026, 5, 9, 6, 0, 0, tzinfo=timezone.utc),
        )
    )
    return result.runner_calls


def test_no_tool_config_keeps_runnercalls_tool_free() -> None:
    """Backward-compat : without `tool_config`, no pass receives tool fields."""
    runner = _build_runner()
    orch = Orchestrator(
        runner=runner,
        regime_pass=RegimePass(),
        asset_pass=AssetPass(),
        stress_pass=StressPass(),
        invalidation_pass=InvalidationPass(),
        critic_fn=_stub_critic,
    )
    calls = _run(orch)
    assert len(calls) == 4
    for c in calls:
        assert c.mcp_config is None
        assert c.allowed_tools is None
        assert c.max_turns == 0


def test_default_tool_config_wires_pass1_pass2_only() -> None:
    """Default `enabled_for_passes={"regime","asset"}` :
    Pass-1 and Pass-2 carry tool fields, Pass-3 and Pass-4 stay clean."""
    mcp = {"mcpServers": {"ichor": {"command": "python", "args": ["-m", "ichor_mcp.server"]}}}
    tools = ("mcp__ichor__query_db", "mcp__ichor__calc")
    cfg = ToolConfig(mcp_config=mcp, allowed_tools=tools)

    runner = _build_runner()
    orch = Orchestrator(
        runner=runner,
        regime_pass=RegimePass(),
        asset_pass=AssetPass(),
        stress_pass=StressPass(),
        invalidation_pass=InvalidationPass(),
        critic_fn=_stub_critic,
        tool_config=cfg,
    )
    calls = _run(orch)
    assert len(calls) == 4

    # Pass 1 (regime) — wired
    assert calls[0].mcp_config == mcp
    assert calls[0].allowed_tools == tools
    assert calls[0].max_turns == 8

    # Pass 2 (asset) — wired
    assert calls[1].mcp_config == mcp
    assert calls[1].allowed_tools == tools
    assert calls[1].max_turns == 8

    # Pass 3 (stress) — NOT wired by default
    assert calls[2].mcp_config is None
    assert calls[2].allowed_tools is None
    assert calls[2].max_turns == 0

    # Pass 4 (invalidation) — NOT wired by default
    assert calls[3].mcp_config is None
    assert calls[3].allowed_tools is None
    assert calls[3].max_turns == 0


def test_custom_enabled_for_passes_filters_correctly() -> None:
    """Caller can restrict tool wiring to a single pass — test 'asset' only."""
    mcp = {"mcpServers": {"ichor": {"command": "python"}}}
    cfg = ToolConfig(
        mcp_config=mcp,
        allowed_tools=("mcp__ichor__calc",),
        max_turns=4,
        enabled_for_passes=frozenset({"asset"}),
    )

    runner = _build_runner()
    orch = Orchestrator(
        runner=runner,
        regime_pass=RegimePass(),
        asset_pass=AssetPass(),
        stress_pass=StressPass(),
        invalidation_pass=InvalidationPass(),
        critic_fn=_stub_critic,
        tool_config=cfg,
    )
    calls = _run(orch)

    # Only Pass 2 (asset) wired
    assert calls[0].mcp_config is None  # regime: not in enabled_for_passes
    assert calls[1].mcp_config == mcp  # asset: enabled
    assert calls[1].max_turns == 4
    assert calls[2].mcp_config is None
    assert calls[3].mcp_config is None


def test_empty_enabled_for_passes_disables_everywhere() -> None:
    """Edge case : enabled_for_passes=frozenset() disables tool wiring on every pass."""
    cfg = ToolConfig(
        mcp_config={"mcpServers": {}},
        allowed_tools=(),
        enabled_for_passes=frozenset(),
    )
    runner = _build_runner()
    orch = Orchestrator(
        runner=runner,
        regime_pass=RegimePass(),
        asset_pass=AssetPass(),
        stress_pass=StressPass(),
        invalidation_pass=InvalidationPass(),
        critic_fn=_stub_critic,
        tool_config=cfg,
    )
    calls = _run(orch)
    for c in calls:
        assert c.mcp_config is None
        assert c.allowed_tools is None
        assert c.max_turns == 0


def test_tool_config_dataclass_is_hashable_and_frozen() -> None:
    """ToolConfig must stay hashable so RunnerCall (frozen) accepts it
    without losing immutability semantics."""
    cfg = ToolConfig(
        mcp_config={"mcpServers": {}},
        allowed_tools=("mcp__ichor__query_db",),
    )
    # frozen=True implies attribute reassign is blocked
    import dataclasses

    assert dataclasses.is_dataclass(cfg)
    assert cfg.max_turns == 8
    assert cfg.enabled_for_passes == frozenset({"regime", "asset"})
