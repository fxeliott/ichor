"""End-to-end orchestrator test with a scripted in-memory runner."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_brain.orchestrator import Orchestrator
from ichor_brain.runner_client import InMemoryRunnerClient

from .fixtures import (
    ASSET_OK_JSON,
    INVALIDATION_OK_JSON,
    REGIME_OK_JSON,
    STRESS_OK_JSON,
    assert_call_contracts,
    four_pass_responses,
    stub_critic_fn,
)

_DATA_POOL = (
    "DXY 105.30 (+1.2%); US10Y 4.18 (-12bps); VIX 18.2 (+4.1); "
    "DFII10 1.85; BAMLH0A0HYM2 3.10; ECB Lagarde dovish on May 2."
)
_ASSET_DATA = (
    "DGS10=4.18 IRLTLT01DEM156N=2.45 EUR_USD COT MM_short=80th_pct "
    "URL https://www.ecb.europa.eu/press/key/date/2026/html/ecb.sp260502.en.html"
)


@pytest.mark.asyncio
async def test_orchestrator_happy_path_produces_session_card() -> None:
    runner = InMemoryRunnerClient(four_pass_responses(duration_ms=8_000))
    orch = Orchestrator(runner=runner, critic_fn=stub_critic_fn())
    now = datetime(2026, 5, 4, 5, 0, tzinfo=UTC)

    result = await orch.run(
        session_type="pre_londres",
        asset="EUR_USD",
        data_pool=_DATA_POOL,
        asset_data=_ASSET_DATA,
        now=now,
    )

    card = result.card
    assert card.session_type == "pre_londres"
    assert card.asset == "EUR_USD"
    assert card.regime.quadrant == REGIME_OK_JSON["quadrant"]
    assert card.specialization.bias_direction == ASSET_OK_JSON["bias_direction"]
    assert card.stress.revised_conviction_pct == STRESS_OK_JSON["revised_conviction_pct"]
    assert len(card.invalidation.conditions) == len(INVALIDATION_OK_JSON["conditions"])
    assert card.generated_at == now
    assert card.claude_duration_ms == 8_000 * 4
    assert card.source_pool_hash  # non-empty


@pytest.mark.asyncio
async def test_orchestrator_calls_runner_4_times_in_order() -> None:
    runner = InMemoryRunnerClient(four_pass_responses())
    orch = Orchestrator(runner=runner, critic_fn=stub_critic_fn())

    result = await orch.run(
        session_type="pre_ny",
        asset="EUR_USD",
        data_pool=_DATA_POOL,
        asset_data=_ASSET_DATA,
    )

    calls = result.runner_calls
    assert_call_contracts(calls)
    # Same order = pass1 → pass2 → pass3 → pass4
    assert "pass1_regime" in calls[0].cache_key
    assert "pass2_asset" in calls[1].cache_key
    assert "pass3_stress" in calls[2].cache_key
    assert "pass4_invalidation" in calls[3].cache_key
    # Asset is interpolated into the asset cache key for fan-out cache reuse
    assert "EUR_USD" in calls[1].cache_key


@pytest.mark.asyncio
async def test_orchestrator_runs_critic_and_records_verdict() -> None:
    runner = InMemoryRunnerClient(four_pass_responses())
    orch = Orchestrator(runner=runner, critic_fn=stub_critic_fn())

    result = await orch.run(
        session_type="pre_londres",
        asset="EUR_USD",
        data_pool=_DATA_POOL,
        asset_data=_ASSET_DATA,
    )

    critic = result.card.critic
    assert critic.verdict in {"approved", "amendments", "blocked"}
    assert 0.0 <= critic.confidence <= 1.0


@pytest.mark.asyncio
async def test_orchestrator_records_blocked_verdict_when_critic_blocks() -> None:
    runner = InMemoryRunnerClient(four_pass_responses())
    orch = Orchestrator(
        runner=runner,
        critic_fn=stub_critic_fn(verdict="blocked", confidence=0.42),
    )

    result = await orch.run(
        session_type="pre_londres",
        asset="EUR_USD",
        data_pool=_DATA_POOL,
        asset_data=_ASSET_DATA,
    )

    assert result.card.critic.verdict == "blocked"
    assert result.card.critic.confidence == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_orchestrator_propagates_pass_validation_error() -> None:
    """A malformed Pass 1 response should bubble up — no silent fallback."""
    bad_responses = four_pass_responses(
        regime={"quadrant": "made_up", "rationale": "x" * 30, "confidence_pct": 50},
    )
    runner = InMemoryRunnerClient(bad_responses)
    orch = Orchestrator(runner=runner, critic_fn=stub_critic_fn())

    with pytest.raises(Exception) as excinfo:
        await orch.run(
            session_type="pre_londres",
            asset="EUR_USD",
            data_pool=_DATA_POOL,
            asset_data=_ASSET_DATA,
        )
    assert "regime pass" in str(excinfo.value).lower()
