"""End-to-end orchestrator test with a scripted in-memory runner."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_brain.orchestrator import Orchestrator
from ichor_brain.runner_client import InMemoryRunnerClient, RunnerCall, RunnerResponse

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


class TestEffortDoctrine:
    """ADR-110 lockstep — every Couche-1 generation call runs Opus 4.8 at
    effort `xhigh` (owner decision 2026-06-11; Fable-5 migration cancelled
    — Fable 5 leaves the Max plan June 22, a Fable engine would breach the
    ZERO-spend invariant). A silent regression to `high`/`medium` here
    would halve the engine quality with zero test failing — lock it."""

    @pytest.mark.asyncio
    async def test_four_passes_emit_opus_xhigh(self) -> None:
        runner = InMemoryRunnerClient(four_pass_responses())
        orch = Orchestrator(runner=runner, critic_fn=stub_critic_fn())

        result = await orch.run(
            session_type="pre_londres",
            asset="EUR_USD",
            data_pool=_DATA_POOL,
            asset_data=_ASSET_DATA,
        )

        assert len(result.runner_calls) == 4
        for i, call in enumerate(result.runner_calls, start=1):
            assert call.model == "opus", f"pass {i}: model {call.model!r} != opus (ADR-108)"
            assert call.effort == "xhigh", f"pass {i}: effort {call.effort!r} != xhigh (ADR-110)"

    def test_pass6_default_effort_is_xhigh(self) -> None:
        orch = Orchestrator(
            runner=InMemoryRunnerClient([]),
            critic_fn=stub_critic_fn(),
        )
        assert orch._scenarios_effort == "xhigh"  # noqa: SLF001 — doctrine lockstep
        assert orch._scenarios_model == "opus"  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_pass6_emitted_runner_call_is_opus_xhigh(self) -> None:
        """Exercise the ACTUAL Pass-6 RunnerCall (enable_scenarios=True) —
        asserting only the constructor default would let a hardcoded
        effort at the call site slip through (verifier finding F6)."""

        class _StubScenariosPass:
            name = "pass6_scenarios"
            system_prompt = "stub system"

            def build_prompt(self, **kwargs: object) -> str:
                return "stub scenarios prompt"

            def parse(self, text: str) -> object:
                class _Decomp:
                    scenarios: list = []

                return _Decomp()

        responses = four_pass_responses()
        responses.append(RunnerResponse(text="{}", raw={"stub": True}, duration_ms=1_000))
        runner = InMemoryRunnerClient(responses)
        orch = Orchestrator(
            runner=runner,
            critic_fn=stub_critic_fn(),
            scenarios_pass=_StubScenariosPass(),
            enable_scenarios=True,
        )

        result = await orch.run(
            session_type="pre_londres",
            asset="EUR_USD",
            data_pool=_DATA_POOL,
            asset_data=_ASSET_DATA,
        )

        assert len(result.runner_calls) == 5
        call6 = result.runner_calls[4]
        assert call6.model == "opus", f"Pass-6 model {call6.model!r} != opus (ADR-110)"
        assert call6.effort == "xhigh", f"Pass-6 effort {call6.effort!r} != xhigh (ADR-110)"

    def test_runner_call_default_effort_is_xhigh(self) -> None:
        assert RunnerCall(prompt="p", system="s").effort == "xhigh"


@pytest.mark.asyncio
async def test_orchestrator_propagates_pass_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed Pass 1 response should bubble up — no silent fallback."""
    # The single retry on the parse error would otherwise sleep the real
    # jittered ~30 s backoff — patch the seam so the test stays fast.
    import ichor_brain.orchestrator as orch_mod

    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(orch_mod.asyncio, "sleep", _no_sleep)

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


class TestRetryBackoffJitter:
    """S02 socle-reliability (2026-06-18) — the pass-retry backoff is base
    30 s ± 25 % jitter, not a fixed 30 s, so that when a fleet-wide cause
    (runner restart, CF-tunnel blip, Claude auth expiry) fails every
    per-asset orchestrator in lock-step they do NOT re-hit the runner at the
    same instant (thundering herd)."""

    @staticmethod
    def _one_retry_then_ok_runner() -> InMemoryRunnerClient:
        # A malformed regime ({} → missing required fields → PassError) on the
        # first attempt, then a valid 4-pass script → exactly one retry.
        first_bad = RunnerResponse(text="{}", raw={}, duration_ms=0)
        return InMemoryRunnerClient([first_bad, *four_pass_responses()])

    @pytest.mark.asyncio
    async def test_retry_sleep_is_jittered_within_band(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ichor_brain.orchestrator as orch_mod

        slept: list[float] = []

        async def _capture(delay: float) -> None:
            slept.append(delay)

        monkeypatch.setattr(orch_mod.asyncio, "sleep", _capture)

        orch = Orchestrator(runner=self._one_retry_then_ok_runner(), critic_fn=stub_critic_fn())
        result = await orch.run(
            session_type="pre_londres",
            asset="EUR_USD",
            data_pool=_DATA_POOL,
            asset_data=_ASSET_DATA,
        )

        # Recovered after exactly one retry, and that retry slept a jittered
        # value inside 30 s ± 25 % (22.5–37.5 s) — never the bare 30.0.
        assert result.card.asset == "EUR_USD"
        assert len(slept) == 1
        assert 22.5 <= slept[0] <= 37.5

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("uniform_ret", "expected_delay"),
        # delay == 30 * (1 + uniform_ret) : +0.2→36.0, -0.2→24.0, 0.0→30.0.
        [(0.2, 36.0), (-0.2, 24.0), (0.0, 30.0)],
    )
    async def test_retry_sleep_delay_tracks_jitter_seam(
        self,
        monkeypatch: pytest.MonkeyPatch,
        uniform_ret: float,
        expected_delay: float,
    ) -> None:
        """The slept delay MUST be base * (1 + random.uniform(-frac, +frac)).

        Mutation guard : a fixed ``asyncio.sleep(30.0)`` (jitter removed) must
        NOT survive — for uniform=+0.2 the delay must be 36.0 (not 30.0), and
        for -0.2 it must be 28.8. A band-only assertion (22.5–37.5) would let
        the fixed-30 regression through, so we pin the exact multiplicative
        relationship and assert the jitter band passed to uniform is (-0.25,
        0.25)."""
        import ichor_brain.orchestrator as orch_mod

        slept: list[float] = []
        seen_args: list[tuple[float, float]] = []

        async def _capture(delay: float) -> None:
            slept.append(delay)

        def _uniform(low: float, high: float) -> float:
            seen_args.append((low, high))
            return uniform_ret

        monkeypatch.setattr(orch_mod.asyncio, "sleep", _capture)
        monkeypatch.setattr(orch_mod.random, "uniform", _uniform)

        orch = Orchestrator(runner=self._one_retry_then_ok_runner(), critic_fn=stub_critic_fn())
        await orch.run(
            session_type="pre_londres",
            asset="EUR_USD",
            data_pool=_DATA_POOL,
            asset_data=_ASSET_DATA,
        )
        # delay == base 30 * (1 + uniform_ret) — fixed-30 mutant dies here.
        assert slept == [pytest.approx(expected_delay)]
        # jitter fraction band is exactly ±_RETRY_JITTER_FRAC (0.25).
        assert seen_args == [(-0.25, 0.25)]
