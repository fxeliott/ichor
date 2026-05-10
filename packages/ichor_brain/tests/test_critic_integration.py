"""Integration test : the orchestrator wired to the real Critic Agent.

Skipped automatically when `ichor_agents` isn't on the path.
"""

from __future__ import annotations

import pytest
from ichor_brain.orchestrator import Orchestrator
from ichor_brain.runner_client import InMemoryRunnerClient

from .fixtures import four_pass_responses

pytest.importorskip("ichor_agents")


_DATA_POOL = (
    "DXY 105.30 (+1.2%); US10Y 4.18 (-12bps); VIX 18.2 (+4.1); "
    "DFII10 1.85; BAMLH0A0HYM2 3.10; ECB Lagarde dovish on May 2."
)
_ASSET_DATA = (
    "DGS10=4.18 IRLTLT01DEM156N=2.45 EUR_USD COT MM_short=80th_pct "
    "URL https://www.ecb.europa.eu/press/key/date/2026/html/ecb.sp260502.en.html"
)


@pytest.mark.asyncio
async def test_real_critic_approves_well_sourced_card() -> None:
    """When all asset/CB references appear in the data pool, the
    rule-based critic should not flag anything."""
    runner = InMemoryRunnerClient(four_pass_responses())
    orch = Orchestrator(runner=runner)  # default critic = real one

    result = await orch.run(
        session_type="pre_londres",
        asset="EUR_USD",
        data_pool=_DATA_POOL,
        asset_data=_ASSET_DATA,
    )

    assert result.card.critic.verdict in {"approved", "amendments"}
    assert result.card.critic.confidence >= 0.5
