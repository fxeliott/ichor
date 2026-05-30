"""r164 tests for ``services/scenario_invalidation_monitor.py`` (Strand D).

Covers atom-level :
- Source-type classifier dispatcher (6 source types : FRED / Polygon /
  CBOE_SKEW / CBOE_VVIX / Polymarket / honest_gap)
- Per-source evaluators (FRED / Polygon / CBOE_SKEW / CBOE_VVIX /
  Polymarket) with AsyncMock — no real DB
- Direction operators : above / below / crosses_above / crosses_below
  (the 2-tick memory path for ``crosses_*``)
- Severity tier resolution : hard / soft / note → fired_* status
- Doctrine #11 calibrated honesty :
    - no data → ``not_evaluable`` (NOT ``not_fired`` — distinct semantic)
    - ``crosses_*`` without sufficient history → ``not_evaluable``
    - honest_gap metrics (MOVE, EVENT_*) → ``not_evaluable``
- Aggregator ``evaluate_scenario_invalidations`` :
    - returns None on missing card
    - returns None on empty scenarios
    - returns None when all buckets have empty invalidations[]
    - strict severity hierarchy hard > soft > note (one bucket → one list)
- ``_polymarket_slug_from_metric`` derivation rule
- ``_fred_series_id_for`` VIX special-case + FRED_-prefix stripping
- ``all_whitelist_metrics_have_router_branch`` invariant helper

Mirrors the r152 ``test_event_anticipation.py`` AsyncMock pattern + r162
``test_coach_macro_context_router.py`` TestClient pattern.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from ichor_api.services.scenario_invalidation_monitor import (
    _classify_metric_source,
    _evaluate_direction,
    _fred_series_id_for,
    _needs_two_tick_memory,
    _polymarket_slug_from_metric,
    _resolve_status,
    all_whitelist_metrics_have_router_branch,
    evaluate_invalidation,
    evaluate_scenario_invalidations,
)
from ichor_brain.scenarios import (
    INVALIDATION_METRIC_NAMES,
    InvalidationCondition,
)

# ── helpers ─────────────────────────────────────────────────────────────


def _make_condition(
    *,
    metric_name: str = "VIX",
    threshold: float = 25.0,
    direction: str = "above",
    severity: str = "hard",
    description: str = "Test condition contradicting the bucket mechanism for unit-test purposes.",
) -> InvalidationCondition:
    """Build an InvalidationCondition fixture exercising every field."""
    return InvalidationCondition(
        metric_name=metric_name,
        threshold=threshold,
        direction=direction,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        description=description,
    )


def _scalars_returning(values: list[object]) -> MagicMock:
    """Build a `session.execute()` mock chain that returns the given
    scalar values for `.scalars().all()`. Polymarket / FRED / Polygon /
    CBOE evaluators all use this pattern."""
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=values)
    result_mock.scalars = MagicMock(return_value=scalars_mock)
    return result_mock


def _scalar_one_or_none_returning(value: object | None) -> MagicMock:
    """Build a `session.execute()` mock chain that returns the given
    value for `.scalar_one_or_none()`."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=value)
    return result_mock


# ── source-type classifier ──────────────────────────────────────────────


class TestClassifyMetricSource:
    """The dispatcher MUST route every whitelist metric to a known source."""

    def test_fred_prefixed_metrics_route_to_fred(self) -> None:
        for m in ("FRED_DGS10", "FRED_BAMLH0A0HYM2", "FRED_PAYEMS"):
            assert _classify_metric_source(m) == "fred", m

    def test_vix_special_case_routes_to_fred(self) -> None:
        """VIX is in whitelist without FRED_ prefix but stored under
        `fred_observations.series_id="VIXCLS"`."""
        assert _classify_metric_source("VIX") == "fred"

    def test_polygon_assets_route_to_polygon(self) -> None:
        for m in ("DXY", "EURUSD", "GBPUSD", "SPX500", "NAS100", "XAUUSD", "BRENT", "WTI"):
            assert _classify_metric_source(m) == "polygon", m

    def test_cboe_skew_routes_to_cboe_skew(self) -> None:
        assert _classify_metric_source("SKEW") == "cboe_skew"

    def test_cboe_vvix_routes_to_cboe_vvix(self) -> None:
        assert _classify_metric_source("VVIX") == "cboe_vvix"

    def test_polymarket_prefixed_routes_to_polymarket(self) -> None:
        for m in ("POLY_FED_CUTS_2026", "POLY_FED_HIKE_2026", "POLY_RECESSION_2026"):
            assert _classify_metric_source(m) == "polymarket", m

    def test_honest_gap_metrics_route_to_honest_gap(self) -> None:
        """MOVE + 3 EVENT_* metrics are honest gaps r164 — no clean source."""
        for m in (
            "MOVE",
            "EVENT_HORMUZ_VOLUME_PCT",
            "EVENT_IRAN_CEASEFIRE_STATUS",
            "EVENT_TRUMP_TARIFF_STATUS",
        ):
            assert _classify_metric_source(m) == "honest_gap", m

    def test_unknown_metric_falls_back_to_honest_gap(self) -> None:
        """Defensive : a metric NOT in any class (would be a whitelist drift
        caught by the CI invariant) still returns honest_gap at runtime."""
        assert _classify_metric_source("UNKNOWN_FOOBAR") == "honest_gap"


# ── helper derivations ──────────────────────────────────────────────────


class TestFredSeriesIdMapping:
    def test_strip_fred_prefix(self) -> None:
        assert _fred_series_id_for("FRED_DGS10") == "DGS10"
        assert _fred_series_id_for("FRED_BAMLH0A0HYM2") == "BAMLH0A0HYM2"
        assert _fred_series_id_for("FRED_PAYEMS") == "PAYEMS"

    def test_vix_special_case_to_vixcls(self) -> None:
        assert _fred_series_id_for("VIX") == "VIXCLS"


class TestPolymarketSlugDerivation:
    def test_canonical_3_polymarket_metrics(self) -> None:
        assert _polymarket_slug_from_metric("POLY_FED_CUTS_2026") == "fed-cuts-2026"
        assert _polymarket_slug_from_metric("POLY_FED_HIKE_2026") == "fed-hike-2026"
        assert _polymarket_slug_from_metric("POLY_RECESSION_2026") == "recession-2026"


# ── direction operator primitives ───────────────────────────────────────


class TestEvaluateDirection:
    """Pure-fn direction operator evaluator."""

    def test_above_fired_when_current_exceeds(self) -> None:
        assert _evaluate_direction(
            current_value=30.0, previous_value=None, threshold=25.0, direction="above"
        )

    def test_above_not_fired_when_current_below(self) -> None:
        assert not _evaluate_direction(
            current_value=20.0, previous_value=None, threshold=25.0, direction="above"
        )

    def test_below_fired_when_current_under(self) -> None:
        assert _evaluate_direction(
            current_value=15.0, previous_value=None, threshold=25.0, direction="below"
        )

    def test_below_not_fired_when_current_above(self) -> None:
        assert not _evaluate_direction(
            current_value=30.0, previous_value=None, threshold=25.0, direction="below"
        )

    def test_crosses_above_requires_prev_below_and_current_above(self) -> None:
        # Transition prev<thr → current>thr fires
        assert _evaluate_direction(
            current_value=30.0,
            previous_value=20.0,
            threshold=25.0,
            direction="crosses_above",
        )
        # Both above : no transition
        assert not _evaluate_direction(
            current_value=30.0,
            previous_value=27.0,
            threshold=25.0,
            direction="crosses_above",
        )
        # Both below : no transition
        assert not _evaluate_direction(
            current_value=20.0,
            previous_value=15.0,
            threshold=25.0,
            direction="crosses_above",
        )
        # Going other direction : no fire on crosses_above
        assert not _evaluate_direction(
            current_value=20.0,
            previous_value=30.0,
            threshold=25.0,
            direction="crosses_above",
        )

    def test_crosses_below_requires_prev_above_and_current_below(self) -> None:
        assert _evaluate_direction(
            current_value=20.0,
            previous_value=30.0,
            threshold=25.0,
            direction="crosses_below",
        )
        assert not _evaluate_direction(
            current_value=30.0,
            previous_value=20.0,
            threshold=25.0,
            direction="crosses_below",
        )

    def test_crosses_with_no_prev_returns_false_caller_treats_as_not_evaluable(
        self,
    ) -> None:
        """Per docstring : the primitive returns False ; the caller MUST
        convert that to ``"not_evaluable"`` (not ``"not_fired"``) when
        prev is None — preserving doctrine #11 honesty."""
        assert not _evaluate_direction(
            current_value=30.0,
            previous_value=None,
            threshold=25.0,
            direction="crosses_above",
        )

    def test_unknown_direction_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown direction operator"):
            _evaluate_direction(
                current_value=30.0,
                previous_value=None,
                threshold=25.0,
                direction="sideways",  # type: ignore[arg-type]
            )


class TestNeedsTwoTickMemory:
    def test_above_below_stateless(self) -> None:
        assert not _needs_two_tick_memory("above")
        assert not _needs_two_tick_memory("below")

    def test_crosses_need_memory(self) -> None:
        assert _needs_two_tick_memory("crosses_above")
        assert _needs_two_tick_memory("crosses_below")


class TestResolveStatus:
    def test_not_fired_maps_to_not_fired(self) -> None:
        assert _resolve_status(fired=False, severity="hard") == "not_fired"
        assert _resolve_status(fired=False, severity="soft") == "not_fired"
        assert _resolve_status(fired=False, severity="note") == "not_fired"

    def test_fired_hard(self) -> None:
        assert _resolve_status(fired=True, severity="hard") == "fired_hard"

    def test_fired_soft(self) -> None:
        assert _resolve_status(fired=True, severity="soft") == "fired_soft"

    def test_fired_note(self) -> None:
        assert _resolve_status(fired=True, severity="note") == "fired_note"


# ── dispatcher : evaluate_invalidation ──────────────────────────────────


class TestEvaluateInvalidationDispatcher:
    """One-condition dispatcher routes to the right source-type evaluator."""

    @pytest.mark.asyncio
    async def test_fred_route_fires_on_above_threshold(self) -> None:
        """FRED VIXCLS at 30.0 vs threshold 25.0 above → fired_hard."""
        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalars_returning([30.0]))
        condition = _make_condition(
            metric_name="VIX",
            threshold=25.0,
            direction="above",
            severity="hard",
        )
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "fired_hard"

    @pytest.mark.asyncio
    async def test_fred_route_returns_not_evaluable_when_no_data(self) -> None:
        """FRED with empty rows → not_evaluable (doctrine #11)."""
        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalars_returning([]))
        condition = _make_condition(metric_name="FRED_DGS10", threshold=4.5)
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "not_evaluable"

    @pytest.mark.asyncio
    async def test_polygon_route_below_threshold(self) -> None:
        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalars_returning([95.0]))
        condition = _make_condition(
            metric_name="DXY",
            threshold=100.0,
            direction="below",
            severity="soft",
        )
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "fired_soft"

    @pytest.mark.asyncio
    async def test_polygon_route_crosses_above_requires_two_rows(self) -> None:
        """crosses_above with only 1 row → not_evaluable (need prev)."""
        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalars_returning([110.0]))
        condition = _make_condition(
            metric_name="DXY",
            threshold=105.0,
            direction="crosses_above",
            severity="hard",
        )
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "not_evaluable"

    @pytest.mark.asyncio
    async def test_polygon_route_crosses_above_two_rows_fires(self) -> None:
        """current=110, prev=100, threshold=105 → crosses_above fired."""
        session = MagicMock()
        # rows[0] = most recent = current ; rows[1] = previous
        session.execute = AsyncMock(return_value=_scalars_returning([110.0, 100.0]))
        condition = _make_condition(
            metric_name="DXY",
            threshold=105.0,
            direction="crosses_above",
            severity="hard",
        )
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "fired_hard"

    @pytest.mark.asyncio
    async def test_cboe_skew_route(self) -> None:
        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalars_returning([145.0]))
        condition = _make_condition(
            metric_name="SKEW",
            threshold=140.0,
            direction="above",
            severity="note",
        )
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "fired_note"

    @pytest.mark.asyncio
    async def test_cboe_vvix_route(self) -> None:
        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalars_returning([105.0]))
        condition = _make_condition(
            metric_name="VVIX",
            threshold=100.0,
            direction="above",
            severity="soft",
        )
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "fired_soft"

    @pytest.mark.asyncio
    async def test_polymarket_route_above(self) -> None:
        """Polymarket binary market list shape ``[yes_prob, no_prob]``."""
        session = MagicMock()
        # Single row : last_prices = [0.55, 0.45]
        session.execute = AsyncMock(return_value=_scalars_returning([[0.55, 0.45]]))
        condition = _make_condition(
            metric_name="POLY_FED_CUTS_2026",
            threshold=0.50,
            direction="above",
            severity="hard",
        )
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "fired_hard"

    @pytest.mark.asyncio
    async def test_polymarket_route_handles_empty_prices_gracefully(self) -> None:
        """Defensive : JSONB returns ``[]`` (no prices yet) → not_evaluable."""
        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalars_returning([[]]))
        condition = _make_condition(
            metric_name="POLY_FED_CUTS_2026",
            threshold=0.50,
        )
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "not_evaluable"

    @pytest.mark.asyncio
    async def test_polymarket_route_handles_malformed_prices(self) -> None:
        """Defensive : non-list JSONB → not_evaluable (no fabrication)."""
        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalars_returning(["not-a-list"]))
        condition = _make_condition(metric_name="POLY_RECESSION_2026", threshold=0.30)
        status = await evaluate_invalidation(session, condition=condition)
        assert status == "not_evaluable"

    @pytest.mark.asyncio
    async def test_honest_gap_metrics_return_not_evaluable(self) -> None:
        """MOVE + 3 EVENT_* honest gaps r164 — doctrine #11."""
        session = MagicMock()
        # Note : honest_gap path should never even call session.execute,
        # so the AsyncMock doesn't need to be set. Defensive : if it IS
        # called, the test would still pass since the dispatcher returns
        # the literal before any DB query.
        for metric in (
            "MOVE",
            "EVENT_HORMUZ_VOLUME_PCT",
            "EVENT_IRAN_CEASEFIRE_STATUS",
            "EVENT_TRUMP_TARIFF_STATUS",
        ):
            condition = _make_condition(metric_name=metric, threshold=0.0)
            status = await evaluate_invalidation(session, condition=condition)
            assert status == "not_evaluable", metric


# ── aggregator : evaluate_scenario_invalidations ────────────────────────


def _make_session_with_scenarios_result(
    scenarios_jsonb: object,
) -> MagicMock:
    """Build a session mock where session.execute() returns a result whose
    .scalar_one_or_none() yields the given scenarios JSONB."""
    session = MagicMock()
    session.execute = AsyncMock(return_value=_scalar_one_or_none_returning(scenarios_jsonb))
    return session


class TestEvaluateScenarioInvalidationsAggregator:
    """End-to-end aggregator tests reading session_card_audit.scenarios JSONB."""

    @pytest.mark.asyncio
    async def test_missing_card_returns_none(self) -> None:
        session = _make_session_with_scenarios_result(None)
        result = await evaluate_scenario_invalidations(session, session_card_id=str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_scenarios_list_returns_none(self) -> None:
        session = _make_session_with_scenarios_result([])
        result = await evaluate_scenario_invalidations(session, session_card_id=str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_scenarios_with_no_invalidations_returns_none(self) -> None:
        """Pre-r163 emissions OR LLM that ignored Strand C → all
        invalidations[] empty → aggregator returns None (no monitor data)."""
        scenarios = [
            {
                "label": "base",
                "p": 0.5,
                "magnitude_pips": [-10, 10],
                "mechanism": "Side mechanism narrative.",
                "invalidations": [],
            },
        ]
        session = _make_session_with_scenarios_result(scenarios)
        result = await evaluate_scenario_invalidations(session, session_card_id=str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_strict_severity_hierarchy_hard_wins(self, monkeypatch) -> None:
        """If a bucket has BOTH a fired_hard AND a fired_soft invalidation,
        the bucket appears ONLY in scenarios_invalidated_hard (strict
        hierarchy)."""

        async def fake_evaluate(_session, *, condition: InvalidationCondition):
            # Map metric_name to a deterministic test status.
            if condition.metric_name == "VIX":
                return "fired_hard"
            if condition.metric_name == "FRED_DGS10":
                return "fired_soft"
            return "not_fired"

        monkeypatch.setattr(
            "ichor_api.services.scenario_invalidation_monitor.evaluate_invalidation",
            fake_evaluate,
        )

        scenarios = [
            {
                "label": "crash_flush",
                "p": 0.03,
                "magnitude_pips": [-300, -120],
                "mechanism": "Crash flush risk mechanism narrative.",
                "invalidations": [
                    {
                        "metric_name": "VIX",
                        "threshold": 18.0,
                        "direction": "below",
                        "severity": "hard",
                        "description": "Cooling vol contradicts crash flush.",
                    },
                    {
                        "metric_name": "FRED_DGS10",
                        "threshold": 4.50,
                        "direction": "below",
                        "severity": "soft",
                        "description": "Yields softening contradicts the panic narrative.",
                    },
                ],
            },
        ]
        session = _make_session_with_scenarios_result(scenarios)
        result = await evaluate_scenario_invalidations(session, session_card_id=str(uuid4()))
        assert result is not None
        assert "crash_flush" in result.scenarios_invalidated_hard
        assert "crash_flush" not in result.scenarios_invalidated_soft
        assert "crash_flush" not in result.scenarios_with_notes

    @pytest.mark.asyncio
    async def test_soft_wins_over_note(self, monkeypatch) -> None:
        async def fake_evaluate(_session, *, condition: InvalidationCondition):
            if condition.metric_name == "FRED_NFCI":
                return "fired_soft"
            if condition.metric_name == "SKEW":
                return "fired_note"
            return "not_fired"

        monkeypatch.setattr(
            "ichor_api.services.scenario_invalidation_monitor.evaluate_invalidation",
            fake_evaluate,
        )

        scenarios = [
            {
                "label": "mild_bear",
                "p": 0.18,
                "magnitude_pips": [-40, -10],
                "mechanism": "Mild downside continuation mechanism narrative.",
                "invalidations": [
                    {
                        "metric_name": "FRED_NFCI",
                        "threshold": -0.20,
                        "direction": "below",
                        "severity": "soft",
                        "description": "Financial conditions easing partially contradicts.",
                    },
                    {
                        "metric_name": "SKEW",
                        "threshold": 130.0,
                        "direction": "above",
                        "severity": "note",
                        "description": "Skew elevated provides risk context shift.",
                    },
                ],
            },
        ]
        session = _make_session_with_scenarios_result(scenarios)
        result = await evaluate_scenario_invalidations(session, session_card_id=str(uuid4()))
        assert result is not None
        assert "mild_bear" in result.scenarios_invalidated_soft
        assert "mild_bear" not in result.scenarios_with_notes
        assert "mild_bear" not in result.scenarios_invalidated_hard

    @pytest.mark.asyncio
    async def test_not_fired_invalidations_dont_count(self, monkeypatch) -> None:
        """A bucket with only not_fired or not_evaluable statuses appears
        in NONE of the 3 lists — verdict consumer interprets absence as
        "mechanism remains plausible"."""

        async def fake_evaluate(_session, *, condition: InvalidationCondition):
            return "not_fired"

        monkeypatch.setattr(
            "ichor_api.services.scenario_invalidation_monitor.evaluate_invalidation",
            fake_evaluate,
        )

        scenarios = [
            {
                "label": "strong_bull",
                "p": 0.11,
                "magnitude_pips": [40, 120],
                "mechanism": "Strong upside continuation mechanism narrative.",
                "invalidations": [
                    {
                        "metric_name": "POLY_FED_CUTS_2026",
                        "threshold": 0.40,
                        "direction": "below",
                        "severity": "hard",
                        "description": "Cut probability dropping contradicts the rally thesis.",
                    },
                ],
            },
        ]
        session = _make_session_with_scenarios_result(scenarios)
        result = await evaluate_scenario_invalidations(session, session_card_id=str(uuid4()))
        # any_invalidation_seen=True (condition was evaluated) so result is not None
        # but the bucket is in NO list (status was not_fired).
        assert result is not None
        assert "strong_bull" not in result.scenarios_invalidated_hard
        assert "strong_bull" not in result.scenarios_invalidated_soft
        assert "strong_bull" not in result.scenarios_with_notes

    @pytest.mark.asyncio
    async def test_last_check_utc_set_to_now(self, monkeypatch) -> None:
        async def fake_evaluate(_session, *, condition: InvalidationCondition):
            return "fired_hard"

        monkeypatch.setattr(
            "ichor_api.services.scenario_invalidation_monitor.evaluate_invalidation",
            fake_evaluate,
        )

        scenarios = [
            {
                "label": "base",
                "p": 0.34,
                "magnitude_pips": [-10, 10],
                "mechanism": "Base case mechanism narrative for invalidation test.",
                "invalidations": [
                    {
                        "metric_name": "DXY",
                        "threshold": 108.0,
                        "direction": "crosses_above",
                        "severity": "hard",
                        "description": "DXY breakout above the rangebound regime.",
                    },
                ],
            },
        ]
        session = _make_session_with_scenarios_result(scenarios)
        now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
        result = await evaluate_scenario_invalidations(
            session, session_card_id=str(uuid4()), now_utc=now
        )
        assert result is not None
        assert result.last_check_utc == now


# ── CI invariant : whitelist ⇄ dispatcher lockstep ──────────────────────


class TestR164InvalidationMetricLockstepCoverage:
    """r164 W90 invariant : every metric in INVALIDATION_METRIC_NAMES MUST
    be classified by ``_classify_metric_source`` to one of the 6 known
    source types (5 evaluable + 1 honest_gap). If a future commit adds a
    metric to the whitelist without adding a routing branch, this test
    fails the build BEFORE the LLM emits an invalidation the runtime
    cannot route.

    Symmetric pin to r163 ``test_pass6_system_prompt_lists_metric_name_
    whitelist`` which ensures the LLM prompt enumerates the whitelist
    verbatim. Together they close the loop : prompt → emission → schema →
    monitor → status.
    """

    def test_all_33_whitelist_metrics_have_router_branch(self) -> None:
        ok, missing = all_whitelist_metrics_have_router_branch()
        assert ok, (
            "r164 Strand D invariant violated : the following metrics in "
            f"INVALIDATION_METRIC_NAMES have NO routing branch in "
            f"scenario_invalidation_monitor._classify_metric_source : "
            f"{missing}. If a metric was added to the whitelist, also add "
            "it to _FRED_PREFIXED / _POLYGON_DIRECT / _CBOE_SKEW / _CBOE_VVIX "
            "/ _POLYMARKET_PREFIXED / _HONEST_GAPS_R164 (whichever applies)."
        )

    def test_whitelist_size_pinned_at_33(self) -> None:
        """If the whitelist grows or shrinks intentionally, also update :
        (a) this size pin, (b) the r163 prompt invariant size pin in
        test_invariants_ichor.py, (c) the routing coverage above."""
        assert len(INVALIDATION_METRIC_NAMES) == 33, (
            f"INVALIDATION_METRIC_NAMES has {len(INVALIDATION_METRIC_NAMES)} "
            "entries, r164 expected 33. Update this test + the r163 prompt "
            "invariant pin (test_invariants_ichor.py) when the whitelist "
            "evolves."
        )
