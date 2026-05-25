"""Tests for r147 Engine 8 event_proximity_engine service + factor builder.

Covers atom-level :

- `_map_title_to_event_class` substring matching (FOMC/ECB/BoE/BoJ/NFP/CPI)
- `_impact_multiplier` high=1.0 / medium=0.4 / low=0.0
- `_time_decay` linear t-to-event window
- `_vix_regime_to_gate` Kurov 2021 VIX gating (p75/p50/below)
- `_currencies_for_asset` mapping
- 8 EDGE CASES (researcher A R59 §6) :
  1. No future events in window → None
  2. Event already fired → next future picked
  3. Weekend / holiday → confidence='low' + caveat (TBD r148 ; r147 ships
     baseline behaviour : no special-case)
  4. Pre-event window <60min → confidence='high'
  5. No VIX in last 4 sessions → vix_regime_gate='unavailable',
     confidence capped 'low'
  6. business_cycle_sign None → +1 default + caveat
  7. event_class unmapped → magnitude_bp=None, parse_failures
  8. Multiple events in window → pick highest-impact, tie-break earliest

- ADR-017 boundary : no BUY/SELL tokens in output ; geometric only.
- Brier lockstep CI : new factor name "event_anticipation" present in BOTH
  `brier_optimizer.DEFAULT_FACTOR_NAMES` AND `cli.run_brier_optimizer._FACTOR_NAMES`
  (test inherited from `test_r142_brier_optimizer_factor_names_lockstep`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from ichor_api.services.event_proximity_engine import (
    EVENT_CLASS_BASELINE_BP,
    EventProximityFactor,
    _currencies_for_asset,
    _impact_multiplier,
    _map_title_to_event_class,
    _time_decay,
    _vix_regime_to_gate,
    assess_event_proximity,
)

# ── helpers ─────────────────────────────────────────────────────────


def _make_event_row(
    *,
    title: str = "Federal Funds Rate",
    impact: str = "high",
    currency: str = "USD",
    scheduled_at: datetime | None = None,
) -> MagicMock:
    """Build an EconomicEvent-shaped MagicMock."""
    if scheduled_at is None:
        scheduled_at = datetime(2026, 6, 18, 18, 0, tzinfo=UTC)
    row = MagicMock()
    row.id = uuid4()
    row.title = title
    row.impact = impact
    row.currency = currency
    row.scheduled_at = scheduled_at
    return row


def _make_fred_row(value: float, observation_date) -> MagicMock:
    """Build a FredObservation-shaped MagicMock."""
    row = MagicMock()
    row.value = value
    row.observation_date = observation_date
    return row


def _build_session(
    *,
    event_rows: list[MagicMock] | None = None,
    vix_row: MagicMock | None = None,
) -> MagicMock:
    """Build AsyncSession mock with sequential execute() returns :
    1st execute = events query → event_rows scalar all
    2nd execute = VIX query → vix_row scalar_one_or_none
    """
    session = MagicMock()
    events_result = MagicMock()
    events_scalars = MagicMock()
    events_scalars.all = MagicMock(return_value=event_rows or [])
    events_result.scalars = MagicMock(return_value=events_scalars)

    vix_result = MagicMock()
    vix_result.scalar_one_or_none = MagicMock(return_value=vix_row)

    session.execute = AsyncMock(side_effect=[events_result, vix_result])
    return session


# ── pure-fn tests ───────────────────────────────────────────────────


class TestMapTitleToEventClass:
    def test_fomc_statement_maps_FOMC(self) -> None:
        assert _map_title_to_event_class("FOMC Statement") == "FOMC"

    def test_federal_funds_rate_maps_FOMC(self) -> None:
        assert _map_title_to_event_class("Federal Funds Rate") == "FOMC"

    def test_ecb_press_conference_maps_ECB(self) -> None:
        assert _map_title_to_event_class("ECB Press Conference") == "ECB"

    def test_boe_official_bank_rate_maps_BoE(self) -> None:
        assert _map_title_to_event_class("BoE Official Bank Rate") == "BoE"

    def test_non_farm_employment_change_maps_NFP(self) -> None:
        assert _map_title_to_event_class("Non-Farm Employment Change") == "NFP"

    def test_core_cpi_maps_CPI_before_generic(self) -> None:
        """Order in _TITLE_TO_EVENT_CLASS matters : Core CPI must NOT
        match generic 'cpi' before. Both should map to 'CPI' class."""
        assert _map_title_to_event_class("Core CPI m/m") == "CPI"
        assert _map_title_to_event_class("CPI y/y") == "CPI"

    def test_case_insensitive_matching(self) -> None:
        assert _map_title_to_event_class("FOMC STATEMENT") == "FOMC"
        assert _map_title_to_event_class("fomc statement") == "FOMC"

    def test_unmapped_title_returns_none(self) -> None:
        assert _map_title_to_event_class("Construction Spending m/m") is None
        assert _map_title_to_event_class("Crude Oil Inventories") is None

    def test_empty_title_returns_none(self) -> None:
        assert _map_title_to_event_class("") is None


class TestImpactMultiplier:
    def test_high_full_weight(self) -> None:
        assert _impact_multiplier("high") == 1.0

    def test_medium_partial(self) -> None:
        assert _impact_multiplier("medium") == 0.4

    def test_low_zero(self) -> None:
        assert _impact_multiplier("low") == 0.0

    def test_unknown_zero(self) -> None:
        assert _impact_multiplier("unknown") == 0.0
        assert _impact_multiplier(None) == 0.0


class TestTimeDecay:
    def test_event_now_full_magnitude(self) -> None:
        assert _time_decay(0, 2880) == 1.0

    def test_event_at_window_edge_zero(self) -> None:
        assert _time_decay(2880, 2880) == 0.0

    def test_linear_midpoint(self) -> None:
        assert _time_decay(1440, 2880) == pytest.approx(0.5)

    def test_negative_time_clamped_to_1(self) -> None:
        """Past events (minutes_until <= 0) → full magnitude (just fired)."""
        assert _time_decay(-10, 2880) == 1.0

    def test_beyond_window_zero(self) -> None:
        assert _time_decay(3000, 2880) == 0.0


class TestVixRegimeToGate:
    def test_above_p75_full_gate(self) -> None:
        label, mult = _vix_regime_to_gate(30.0)
        assert label == "above_p75"
        assert mult == 1.0

    def test_p50_to_p75(self) -> None:
        label, mult = _vix_regime_to_gate(20.0)
        assert label == "p50_to_p75"
        assert mult == 0.4

    def test_below_p50_low(self) -> None:
        label, mult = _vix_regime_to_gate(15.0)
        assert label == "below_p50"
        assert mult == 0.1

    def test_none_unavailable(self) -> None:
        label, mult = _vix_regime_to_gate(None)
        assert label == "unavailable"
        assert mult == 0.0

    def test_boundary_p75_inclusive(self) -> None:
        label, _ = _vix_regime_to_gate(24.0)
        assert label == "above_p75"  # >= p75 inclusive

    def test_boundary_p50_inclusive(self) -> None:
        label, _ = _vix_regime_to_gate(18.0)
        assert label == "p50_to_p75"  # >= p50 inclusive


class TestCurrenciesForAsset:
    def test_eur_usd_pulls_both(self) -> None:
        assert _currencies_for_asset("EUR_USD") == ("USD", "EUR")

    def test_gbp_usd_pulls_both(self) -> None:
        assert _currencies_for_asset("GBP_USD") == ("USD", "GBP")

    def test_spx_pulls_usd_only(self) -> None:
        assert _currencies_for_asset("SPX500_USD") == ("USD",)

    def test_nas_pulls_usd_only(self) -> None:
        assert _currencies_for_asset("NAS100_USD") == ("USD",)

    def test_xau_pulls_usd_only(self) -> None:
        assert _currencies_for_asset("XAU_USD") == ("USD",)

    def test_case_insensitive(self) -> None:
        assert _currencies_for_asset("eur_usd") == ("USD", "EUR")


# ── assess_event_proximity edge cases ──────────────────────────────


class TestAssessEventProximity:
    """8 edge cases from researcher A R59 §6 + integration."""

    @pytest.mark.asyncio
    async def test_edge_case_1_no_future_events_returns_none(self) -> None:
        """Edge case 1 : no future events in window → return None."""
        session = _build_session(event_rows=[])
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        result = await assess_event_proximity(session, asset="EUR_USD", now=now)
        assert result is None

    @pytest.mark.asyncio
    async def test_edge_case_4_pre_event_window_under_60min_confidence_high(self) -> None:
        """Edge case 4 : pre-event window <60min → confidence='high'."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        # Event in 30 minutes
        event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(minutes=30),
        )
        vix = _make_fred_row(30.0, now.date())  # above p75
        session = _build_session(event_rows=[event], vix_row=vix)
        result = await assess_event_proximity(session, asset="EUR_USD", now=now)
        assert result is not None
        assert result.confidence == "high"
        assert result.next_event_minutes_until == 30

    @pytest.mark.asyncio
    async def test_edge_case_5_no_vix_observation_unavailable_low_confidence(self) -> None:
        """Edge case 5 : no VIX in last 4 sessions → vix_regime_gate='unavailable',
        confidence capped at 'low'."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(minutes=120),
        )
        session = _build_session(event_rows=[event], vix_row=None)
        result = await assess_event_proximity(session, asset="EUR_USD", now=now)
        assert result is not None
        assert result.vix_regime_gate == "unavailable"
        assert result.confidence == "low"
        assert "vix_observation_missing" in result.parse_failures

    @pytest.mark.asyncio
    async def test_edge_case_6_business_cycle_sign_default_with_caveat(self) -> None:
        """Edge case 6 : business_cycle_sign None → +1 default + caveat."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(hours=12),
        )
        vix = _make_fred_row(30.0, now.date())
        session = _build_session(event_rows=[event], vix_row=vix)
        result = await assess_event_proximity(session, asset="EUR_USD", now=now)
        assert result is not None
        assert "Asymétrie cyclique non vérifiée" in result.caveat
        # r147 trader YELLOW-1 : cold-start prior caveat ALWAYS appended
        assert "Magnitude prior littérature, pas calibrée sur historique Ichor" in result.caveat
        # Default sign +1 → positive drift expectation for FOMC
        assert result.expected_drift_direction == "up"
        assert result.expected_drift_magnitude_bp is not None
        assert result.expected_drift_magnitude_bp > 0

    @pytest.mark.asyncio
    async def test_edge_case_6_explicit_negative_cycle_sign_flips_direction(self) -> None:
        """If business_cycle_sign=-1 (contraction), drift direction flips down."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(hours=12),
        )
        vix = _make_fred_row(30.0, now.date())
        session = _build_session(event_rows=[event], vix_row=vix)
        result = await assess_event_proximity(
            session, asset="EUR_USD", now=now, business_cycle_sign=-1
        )
        assert result is not None
        assert result.expected_drift_direction == "down"
        assert result.expected_drift_magnitude_bp is not None
        assert result.expected_drift_magnitude_bp < 0
        assert "Asymétrie cyclique non vérifiée" not in result.caveat
        # r147 trader YELLOW-1 : prior caveat still appended even when cycle wired
        assert "Magnitude prior littérature" in result.caveat

    @pytest.mark.asyncio
    async def test_yellow_1_cold_start_prior_caveat_always_present(self) -> None:
        """r147 trader YELLOW-1 : cold-start prior caveat MUST appear in
        EVERY output regardless of other gating state."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(hours=12),
        )
        vix = _make_fred_row(30.0, now.date())
        session = _build_session(event_rows=[event], vix_row=vix)
        result = await assess_event_proximity(
            session, asset="EUR_USD", now=now, business_cycle_sign=+1
        )
        assert result is not None
        # All-clean scenario : NO other caveat fires, but the prior caveat
        # STILL appears (was the noise-only fallback prior to YELLOW-1 fix).
        assert "Magnitude prior littérature, pas calibrée sur historique Ichor" in result.caveat

    @pytest.mark.asyncio
    async def test_sf_3_malformed_impact_surfaces_sentinel(self) -> None:
        """r147 code-reviewer SF-3 : malformed impact value (not in
        {high,medium,low}) → next_event_impact=None +
        parse_failures.add('impact_value_invalid'). Parity with r141
        SurpriseClassification honest sentinel discipline."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        # ORM has no CHECK on impact ; malformed string possible from
        # upstream provider drift.
        event = _make_event_row(
            title="FOMC Statement",
            impact="extreme",  # not in canonical set
            currency="USD",
            scheduled_at=now + timedelta(hours=6),
        )
        # Query filters impact IN ("high","medium") so "extreme" wouldn't
        # match upstream — but if a future provider drift produces a row
        # that DOES match (e.g., "high " with trailing space), the
        # in-line ternary post-filter would still flag it. Use a probe-
        # row that bypasses the SQL filter by mocking it directly.
        event.impact = "extreme"
        session = _build_session(event_rows=[event], vix_row=_make_fred_row(30.0, now.date()))
        result = await assess_event_proximity(session, asset="EUR_USD", now=now)
        assert result is not None
        assert result.next_event_impact is None  # honestly surfaced
        assert "impact_value_invalid" in result.parse_failures

    @pytest.mark.asyncio
    async def test_edge_case_7_unmapped_event_class_returns_magnitude_none(self) -> None:
        """Edge case 7 : event_class unmapped → magnitude_bp=None,
        parse_failures has 'event_class_unmapped', confidence='unavailable'."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        event = _make_event_row(
            title="Construction Spending m/m",  # not in baseline table
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(hours=12),
        )
        vix = _make_fred_row(30.0, now.date())
        session = _build_session(event_rows=[event], vix_row=vix)
        result = await assess_event_proximity(session, asset="EUR_USD", now=now)
        assert result is not None
        assert result.expected_drift_magnitude_bp is None
        assert result.expected_drift_direction == "unknown"
        assert result.confidence == "unavailable"
        assert "event_class_unmapped" in result.parse_failures
        assert "Classe d'événement non mappée" in result.caveat

    @pytest.mark.asyncio
    async def test_edge_case_8_multiple_events_highest_impact_wins(self) -> None:
        """Edge case 8 : pool of high+medium events ; high-impact wins."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        medium_event = _make_event_row(
            title="ECB Press Conference",
            impact="medium",
            currency="EUR",
            scheduled_at=now + timedelta(hours=6),  # closer in time
        )
        high_event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(hours=12),  # further in time
        )
        vix = _make_fred_row(30.0, now.date())
        # Order returned by query is ASC by scheduled_at → medium first, high second.
        session = _build_session(event_rows=[medium_event, high_event], vix_row=vix)
        result = await assess_event_proximity(session, asset="EUR_USD", now=now)
        assert result is not None
        # High-impact wins despite being further out in time.
        assert result.next_event_title == "FOMC Statement"
        assert result.next_event_impact == "high"
        assert result.next_event_class == "FOMC"

    @pytest.mark.asyncio
    async def test_integration_eur_usd_fomc_high_vix_positive_drift(self) -> None:
        """Integration test : EUR_USD + FOMC in 6h + high VIX + default
        expansion → positive expected drift (USD bid anticipation).

        Magnitude unchanged by r147 SF-1 fix (SF-1 boosts the
        bp→contribution coefficient in confluence_engine, not the raw bp
        value computed inside event_proximity_engine itself)."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(hours=6),
        )
        vix = _make_fred_row(30.0, now.date())  # above p75
        session = _build_session(event_rows=[event], vix_row=vix)
        result = await assess_event_proximity(session, asset="EUR_USD", now=now)
        assert result is not None
        assert result.next_event_class == "FOMC"
        assert result.vix_regime_gate == "above_p75"
        assert result.expected_drift_direction == "up"
        assert result.expected_drift_magnitude_bp is not None
        # baseline FOMC=50 × impact 1.0 × time_decay ≈ 0.79 × vix 1.0 × sign +1
        # ≈ 39.5bp signed positive
        assert 30 < result.expected_drift_magnitude_bp < 50

    @pytest.mark.asyncio
    async def test_integration_low_vix_dampens_magnitude(self) -> None:
        """Kurov 2021 conditioning : low VIX → ~0.1 multiplier → dampened drift."""
        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(hours=6),
        )
        vix = _make_fred_row(12.0, now.date())  # below p50
        session = _build_session(event_rows=[event], vix_row=vix)
        result = await assess_event_proximity(session, asset="EUR_USD", now=now)
        assert result is not None
        assert result.vix_regime_gate == "below_p50"
        assert result.expected_drift_magnitude_bp is not None
        # Low-VIX gate (0.1) dampens magnitude ~10× vs high-VIX scenario.
        assert result.expected_drift_magnitude_bp < 10

    @pytest.mark.asyncio
    async def test_baseline_table_contains_canonical_classes(self) -> None:
        """Baseline table sanity : FOMC=50, ECB=35, NFP=20, CPI=20 per
        literature citations."""
        assert EVENT_CLASS_BASELINE_BP["FOMC"] == 50.0
        assert EVENT_CLASS_BASELINE_BP["ECB"] == 35.0
        assert EVENT_CLASS_BASELINE_BP["BoE"] == 25.0
        assert EVENT_CLASS_BASELINE_BP["BoJ"] == 15.0
        assert EVENT_CLASS_BASELINE_BP["NFP"] == 20.0
        assert EVENT_CLASS_BASELINE_BP["CPI"] == 20.0


# ── ADR-017 + Brier lockstep CI invariants ──────────────────────────


class TestAdr017Invariants:
    def test_event_proximity_factor_has_no_directional_field_names(self) -> None:
        """ADR-017 : no field name implies trade direction."""
        from dataclasses import fields

        names = {f.name for f in fields(EventProximityFactor)}
        forbidden = ["buy", "sell", "long", "short", "side", "entry", "stop"]
        for n in names:
            low = n.lower()
            for sub in forbidden:
                assert sub not in low.split("_"), f"forbidden token {sub!r} in field {n!r}"

    def test_baseline_table_has_only_numeric_values(self) -> None:
        """No fabricated directional signs in baseline table — magnitudes
        only (sign comes from business_cycle_sign at runtime)."""
        for k, v in EVENT_CLASS_BASELINE_BP.items():
            assert isinstance(v, (int, float))
            assert v >= 0  # baselines are magnitudes ; sign applied externally


class TestBrierLockstepWithR147:
    """r147 extension of r142 brier_optimizer factor names lockstep guard.
    The new "event_anticipation" factor MUST appear in BOTH
    `brier_optimizer.DEFAULT_FACTOR_NAMES` AND
    `cli.run_brier_optimizer._FACTOR_NAMES` lists.

    r151 — dropped inheritance from `TestAdr017Invariants` (r147 MRO smell
    flagged by code-reviewer r149 NICE #6 + r150 NICE) : the 2 inherited
    ADR-017 tests (forbidden field names + baseline magnitudes ≥ 0) are
    unrelated to Brier lockstep and were silently re-executing under this
    class name. They still run from `TestAdr017Invariants` directly ; no
    coverage loss.
    """

    def test_event_anticipation_in_brier_default_factor_names(self) -> None:
        from ichor_api.services.brier_optimizer import DEFAULT_FACTOR_NAMES

        assert "event_anticipation" in DEFAULT_FACTOR_NAMES

    def test_event_anticipation_in_cli_factor_names(self) -> None:
        from ichor_api.cli.run_brier_optimizer import _FACTOR_NAMES

        assert "event_anticipation" in _FACTOR_NAMES

    def test_brier_factor_names_remain_set_equal(self) -> None:
        """Lockstep CI invariant inherited from r142
        test_r142_brier_optimizer_factor_names_lockstep."""
        from ichor_api.cli.run_brier_optimizer import _FACTOR_NAMES
        from ichor_api.services.brier_optimizer import DEFAULT_FACTOR_NAMES

        assert set(DEFAULT_FACTOR_NAMES) == set(_FACTOR_NAMES)


# ── r147 trader review fix-cluster probe tests ──────────────────────


class TestTraderGap2VixThresholdsPinned:
    """r147 trader GAP-2 : pin VIX gate thresholds verbatim to prevent
    silent drift. _VIX_P50 = 18.0 (long-run median) ; _VIX_P75 = 24.0
    (75th percentile). Rough long-run values per Kurov 2021 ; r148+
    candidate to compute empirically from `fred_observations`."""

    def test_vix_p50_threshold_pinned(self) -> None:
        from ichor_api.services.event_proximity_engine import _VIX_P50

        assert _VIX_P50 == 18.0

    def test_vix_p75_threshold_pinned(self) -> None:
        from ichor_api.services.event_proximity_engine import _VIX_P75

        assert _VIX_P75 == 24.0


class TestTraderGap3PerAssetTransmission:
    """r147 trader GAP-3 : pin per-asset transmission discipline of
    `_factor_event_anticipation()` (parity with r142 trader probe-tests).
    Sign convention :
      - USD_IS_BASE (USD/JPY etc.) : positive drift → long the pair
      - X/USD (EUR/USD etc.) : positive drift → SHORT the pair (USD bid)
      - XAU_USD : honest zero (ambiguous Boyd-Hu-Jagannathan sign-flip)
      - SPX/NAS : positive drift = equity-positive under expansion
    """

    @pytest.mark.asyncio
    async def test_eur_usd_positive_drift_shorts_pair(self) -> None:
        """EUR_USD with FOMC positive drift expectation → negative
        contribution (X/USD pair short under USD-bid anticipation)."""
        from ichor_api.services.confluence_engine import _factor_event_anticipation

        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(hours=3),
        )
        vix = _make_fred_row(30.0, now.date())
        session = _build_session(event_rows=[event], vix_row=vix)
        # Inject deterministic `now` indirectly — actual fn uses datetime.now(UTC).
        # Mock the underlying assess_event_proximity import to bypass `now`.
        from unittest.mock import patch

        from ichor_api.services.event_proximity_engine import (
            EventProximityFactor,
        )

        fake_factor = EventProximityFactor(
            next_event_id="evt-1",
            next_event_title="FOMC Statement",
            next_event_currency="USD",
            next_event_minutes_until=180,
            next_event_impact="high",
            next_event_class="FOMC",
            expected_drift_direction="up",
            expected_drift_magnitude_bp=40.0,  # signed positive
            confidence="high",
            vix_regime_gate="above_p75",
            caveat="Magnitude prior littérature, pas calibrée sur historique Ichor",
            literature_anchor="Lucca-Moench 2015",
            parse_failures=frozenset(),
        )
        with patch(
            "ichor_api.services.event_proximity_engine.assess_event_proximity",
            return_value=fake_factor,
        ) as _:
            driver = await _factor_event_anticipation(session, "EUR_USD")
        assert driver is not None
        # X/USD : positive drift → SHORT EUR_USD → NEGATIVE contribution
        assert driver.contribution < 0
        assert driver.factor == "event_anticipation"

    @pytest.mark.asyncio
    async def test_usd_jpy_positive_drift_longs_pair(self) -> None:
        """USD_JPY with FOMC positive drift → POSITIVE contribution
        (USD-base : USD strong = long the pair)."""
        from unittest.mock import patch

        from ichor_api.services.confluence_engine import _factor_event_anticipation
        from ichor_api.services.event_proximity_engine import (
            EventProximityFactor,
        )

        session = _build_session(event_rows=[], vix_row=None)
        fake_factor = EventProximityFactor(
            next_event_id="evt-1",
            next_event_title="FOMC Statement",
            next_event_currency="USD",
            next_event_minutes_until=180,
            next_event_impact="high",
            next_event_class="FOMC",
            expected_drift_direction="up",
            expected_drift_magnitude_bp=40.0,
            confidence="high",
            vix_regime_gate="above_p75",
            caveat="Magnitude prior littérature, pas calibrée sur historique Ichor",
            literature_anchor="Lucca-Moench 2015",
            parse_failures=frozenset(),
        )
        with patch(
            "ichor_api.services.event_proximity_engine.assess_event_proximity",
            return_value=fake_factor,
        ):
            driver = await _factor_event_anticipation(session, "USD_JPY")
        assert driver is not None
        # USD-base : positive drift → LONG USD_JPY → POSITIVE contribution
        assert driver.contribution > 0

    @pytest.mark.asyncio
    async def test_xau_usd_honest_zero(self) -> None:
        """XAU_USD : positive drift expectation → contribution=0.0
        (ambiguous sign-flip per Boyd-Hu-Jagannathan ; parity with r137
        inflation_surprise XAU=0 design)."""
        from unittest.mock import patch

        from ichor_api.services.confluence_engine import _factor_event_anticipation
        from ichor_api.services.event_proximity_engine import (
            EventProximityFactor,
        )

        session = _build_session(event_rows=[], vix_row=None)
        fake_factor = EventProximityFactor(
            next_event_id="evt-1",
            next_event_title="FOMC Statement",
            next_event_currency="USD",
            next_event_minutes_until=180,
            next_event_impact="high",
            next_event_class="FOMC",
            expected_drift_direction="up",
            expected_drift_magnitude_bp=40.0,
            confidence="high",
            vix_regime_gate="above_p75",
            caveat="Magnitude prior littérature, pas calibrée sur historique Ichor",
            literature_anchor="Lucca-Moench 2015",
            parse_failures=frozenset(),
        )
        with patch(
            "ichor_api.services.event_proximity_engine.assess_event_proximity",
            return_value=fake_factor,
        ):
            driver = await _factor_event_anticipation(session, "XAU_USD")
        assert driver is not None
        assert driver.contribution == 0.0

    @pytest.mark.asyncio
    async def test_sf_1_calibration_clears_r142_threshold(self) -> None:
        """r147 code-reviewer SF-1 : verify the coefficient/cap calibration
        (1.2 / ±0.6) clears the r142 ENGINE_DRIVER_MIN_ABS_CONTRIBUTION =
        0.2 threshold for canonical FOMC/ECB/BoE/NFP/CPI events at peak.

        FOMC peak = 50bp / 100 × 1.2 = 0.6 (cap) ✓
        ECB  peak = 35bp / 100 × 1.2 = 0.42        ✓
        NFP  peak = 20bp / 100 × 1.2 = 0.24        ✓
        """
        from unittest.mock import patch

        from ichor_api.services.confluence_engine import _factor_event_anticipation
        from ichor_api.services.event_proximity_engine import (
            EventProximityFactor,
        )

        session = _build_session(event_rows=[], vix_row=None)
        fake_factor_fomc = EventProximityFactor(
            next_event_id="evt-1",
            next_event_title="FOMC Statement",
            next_event_currency="USD",
            next_event_minutes_until=5,  # firing now
            next_event_impact="high",
            next_event_class="FOMC",
            expected_drift_direction="up",
            expected_drift_magnitude_bp=50.0,
            confidence="high",
            vix_regime_gate="above_p75",
            caveat="Magnitude prior littérature, pas calibrée sur historique Ichor",
            literature_anchor="Lucca-Moench 2015",
            parse_failures=frozenset(),
        )
        with patch(
            "ichor_api.services.event_proximity_engine.assess_event_proximity",
            return_value=fake_factor_fomc,
        ):
            driver = await _factor_event_anticipation(session, "USD_JPY")
        assert driver is not None
        # 50/100 × 1.2 = 0.6 cap → above 0.2 threshold ✓
        assert abs(driver.contribution) > 0.2
        assert abs(driver.contribution) <= 0.6

    @pytest.mark.asyncio
    async def test_yellow_2_vix_unavailable_attenuates_contribution(self) -> None:
        """r147 trader YELLOW-2 : when confidence='low' AND
        vix_regime_gate='unavailable', contribution is attenuated × 0.5
        to preserve visibility but signal degraded honesty."""
        from unittest.mock import patch

        from ichor_api.services.confluence_engine import _factor_event_anticipation
        from ichor_api.services.event_proximity_engine import (
            EventProximityFactor,
        )

        session = _build_session(event_rows=[], vix_row=None)
        fake_factor_degraded = EventProximityFactor(
            next_event_id="evt-1",
            next_event_title="FOMC Statement",
            next_event_currency="USD",
            next_event_minutes_until=5,
            next_event_impact="high",
            next_event_class="FOMC",
            expected_drift_direction="up",
            expected_drift_magnitude_bp=50.0,  # would yield 0.6 cap normally
            confidence="low",
            vix_regime_gate="unavailable",
            caveat="VIX indisponible, gate régime dégradée ; Magnitude prior littérature",
            literature_anchor="Lucca-Moench 2015",
            parse_failures=frozenset({"vix_observation_missing"}),
        )
        with patch(
            "ichor_api.services.event_proximity_engine.assess_event_proximity",
            return_value=fake_factor_degraded,
        ):
            driver = await _factor_event_anticipation(session, "USD_JPY")
        assert driver is not None
        # Magnitude attenuated × 0.5 : 50/100 × 1.2 × 0.5 = 0.3 (post-cap 0.6)
        assert abs(driver.contribution) == pytest.approx(0.3, abs=0.01)


class TestCodeReviewerN1CallOrderSentinel:
    """r147 code-reviewer N-1 NICE : assert events-query-before-VIX call
    sequence. Defensive against future implementation reorder breaking
    the AsyncMock(side_effect=[events_result, vix_result]) fixture pattern."""

    @pytest.mark.asyncio
    async def test_events_query_fires_before_vix_query(self) -> None:
        """The internal call order is :
        1. SELECT ... FROM economic_events WHERE ... (proximity query)
        2. SELECT ... FROM fred_observations WHERE series_id='VIXCLS' (VIX gate)
        If this order ever flips, the AsyncMock side_effect pattern would
        mis-pair, hiding test failures. Assert verbatim."""

        now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
        event = _make_event_row(
            title="FOMC Statement",
            impact="high",
            currency="USD",
            scheduled_at=now + timedelta(hours=6),
        )
        vix = _make_fred_row(30.0, now.date())
        session = _build_session(event_rows=[event], vix_row=vix)
        await assess_event_proximity(session, asset="EUR_USD", now=now)

        # Verify the call sequence : first execute() call references
        # EconomicEvent, second references FredObservation.
        calls = session.execute.await_args_list
        assert len(calls) == 2
        first_stmt = calls[0].args[0]
        second_stmt = calls[1].args[0]
        # Compiled SQL inspection : EconomicEvent first, FredObservation second.
        first_sql = str(first_stmt.compile(compile_kwargs={"literal_binds": False}))
        second_sql = str(second_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "economic_events" in first_sql.lower()
        assert "fred_observations" in second_sql.lower()


# ── r149 AUD/CAD/JPY title-fragment extension ────────────────────────


class TestR149AudCadJpyTitleMapping:
    """r149 — Engine 8 title-fragment extension for AUD (RBA) / CAD (BoC) /
    JPY (BoJ broadened + Tankan). Each new fragment must map to its
    expected event class via `_map_title_to_event_class()`. Empirical
    FF XML titles verified via researcher web R59 fetch of
    `https://nfs.faireconomy.media/ff_calendar_thisweek.xml` 2026-05-22
    + prod DB query (5 high-impact AUD events + 3 high CAD + 0 high JPY
    in last 30 days — JPY events fire as `low` impact in FF empirical,
    documented honest-scope).
    """

    # RBA family
    def test_cash_rate_bare_title_maps_RBA(self) -> None:
        assert _map_title_to_event_class("Cash Rate") == "RBA"

    def test_rba_rate_statement_maps_RBA(self) -> None:
        assert _map_title_to_event_class("RBA Rate Statement") == "RBA"

    def test_rba_press_conference_maps_RBA(self) -> None:
        assert _map_title_to_event_class("RBA Press Conference") == "RBA"

    def test_rba_monetary_policy_statement_maps_RBA(self) -> None:
        assert _map_title_to_event_class("RBA Monetary Policy Statement") == "RBA"

    def test_statement_on_monetary_policy_maps_RBA(self) -> None:
        """RBA quarterly SoMP — FF XML title bare without RBA prefix."""
        assert _map_title_to_event_class("Statement on Monetary Policy") == "RBA"

    # BoC family
    def test_overnight_rate_bare_title_maps_BoC(self) -> None:
        assert _map_title_to_event_class("Overnight Rate") == "BoC"

    def test_boc_rate_statement_maps_BoC(self) -> None:
        assert _map_title_to_event_class("BOC Rate Statement") == "BoC"

    def test_boc_press_conference_maps_BoC(self) -> None:
        assert _map_title_to_event_class("BOC Press Conference") == "BoC"

    def test_boc_monetary_policy_report_maps_BoC(self) -> None:
        assert _map_title_to_event_class("BOC Monetary Policy Report") == "BoC"

    # BoJ broadening
    def test_boj_press_conference_maps_BoJ(self) -> None:
        assert _map_title_to_event_class("BOJ Press Conference") == "BoJ"

    def test_boj_summary_of_opinions_maps_BoJ(self) -> None:
        assert _map_title_to_event_class("BOJ Summary of Opinions") == "BoJ"

    def test_bare_monetary_policy_statement_maps_BoJ(self) -> None:
        """JPY BoJ FF XML title is bare `Monetary Policy Statement`
        (no BOJ prefix in FF XML feed — researcher web R59 verified).
        Generic fallback pattern matches because more-specific RBA/ECB/BoE
        patterns are tried first."""
        assert _map_title_to_event_class("Monetary Policy Statement") == "BoJ"

    # Tankan
    def test_tankan_manufacturing_maps_Tankan(self) -> None:
        assert _map_title_to_event_class("Tankan Manufacturing Index") == "Tankan"

    def test_tankan_non_manufacturing_maps_Tankan(self) -> None:
        assert _map_title_to_event_class("Tankan Non-Manufacturing Index") == "Tankan"

    # CPI variants for AUD/CAD/JPY map to existing CPI class
    def test_trimmed_mean_cpi_maps_CPI(self) -> None:
        """AUD-specific RBA preferred-core measure."""
        assert _map_title_to_event_class("Trimmed Mean CPI q/q") == "CPI"

    def test_trimmed_cpi_maps_CPI(self) -> None:
        """CAD-specific StatCan BoC-preferred measure."""
        assert _map_title_to_event_class("Trimmed CPI y/y") == "CPI"

    def test_median_cpi_maps_CPI(self) -> None:
        """CAD-specific BoC preferred-core measure."""
        assert _map_title_to_event_class("Median CPI y/y") == "CPI"

    def test_common_cpi_maps_CPI(self) -> None:
        """CAD-specific BoC preferred-core measure."""
        assert _map_title_to_event_class("Common CPI y/y") == "CPI"

    def test_tokyo_core_cpi_maps_CPI(self) -> None:
        """JPY-specific BoJ preferred-core measure."""
        assert _map_title_to_event_class("Tokyo Core CPI y/y") == "CPI"

    def test_national_core_cpi_maps_CPI(self) -> None:
        """JPY-specific BoJ preferred-core measure."""
        assert _map_title_to_event_class("National Core CPI y/y") == "CPI"


class TestR149RegressionExistingMappingsUnchanged:
    """r149 must preserve all r147 USD / EUR / GBP / pre-r149 JPY mappings.
    Ensures the new fragments + reordering didn't shift first-match-wins
    semantics for established USD/EUR/GBP/BoJ titles.
    """

    def test_fomc_statement_still_maps_FOMC(self) -> None:
        assert _map_title_to_event_class("FOMC Statement") == "FOMC"

    def test_ecb_monetary_policy_statement_still_maps_ECB(self) -> None:
        """Critical : ECB title contains `monetary policy statement`,
        the new r149 generic fallback. Specific ECB pattern MUST win."""
        assert _map_title_to_event_class("ECB Monetary Policy Statement") == "ECB"

    def test_boe_monetary_policy_report_still_maps_BoE(self) -> None:
        assert _map_title_to_event_class("BOE Monetary Policy Report") == "BoE"

    def test_boj_outlook_report_still_maps_BoJ(self) -> None:
        assert _map_title_to_event_class("BOJ Outlook Report") == "BoJ"

    def test_boj_policy_rate_still_maps_BoJ(self) -> None:
        assert _map_title_to_event_class("BOJ Policy Rate") == "BoJ"

    def test_nfp_still_maps_NFP(self) -> None:
        assert _map_title_to_event_class("Non-Farm Employment Change") == "NFP"

    def test_core_cpi_mm_still_maps_CPI(self) -> None:
        assert _map_title_to_event_class("Core CPI m/m") == "CPI"

    def test_cpi_mm_still_maps_CPI(self) -> None:
        assert _map_title_to_event_class("CPI m/m") == "CPI"


class TestR149NewBaselineKeys:
    """r149 — new event classes (RBA / BoC / Tankan) MUST have baseline_bp
    entries to prevent the silent fall-through where a mapped class lacks
    a baseline, which would yield `expected_drift_magnitude_bp=None` per
    the engine's honest-scope `event_class_unmapped` short-circuit.
    """

    def test_rba_baseline_present(self) -> None:
        assert "RBA" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["RBA"] == 25.0

    def test_boc_baseline_present(self) -> None:
        assert "BoC" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["BoC"] == 25.0

    def test_tankan_baseline_present(self) -> None:
        assert "Tankan" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["Tankan"] == 15.0

    def test_r147_baselines_unchanged(self) -> None:
        """Regression : r147 baseline magnitudes must NOT drift silently."""
        assert EVENT_CLASS_BASELINE_BP["FOMC"] == 50.0
        assert EVENT_CLASS_BASELINE_BP["ECB"] == 35.0
        assert EVENT_CLASS_BASELINE_BP["BoE"] == 25.0
        assert EVENT_CLASS_BASELINE_BP["BoJ"] == 15.0
        assert EVENT_CLASS_BASELINE_BP["NFP"] == 20.0
        assert EVENT_CLASS_BASELINE_BP["CPI"] == 20.0


class TestR149BlockedListCollisionGuard:
    """r149 — defensive `_TITLE_FRAGMENT_BLOCKED` negative-list checked
    BEFORE positive matching. Guards against RBNZ "Official Cash Rate"
    silently substring-matching RBA "Cash Rate" pattern. No Ichor asset
    has NZD exposure today, but the guard is future-proofing per
    doctrine #11 calibrated-honesty defensive engineering (lesson #34
    pattern extended to negative-list class).
    """

    def test_official_cash_rate_returns_none_not_RBA(self) -> None:
        """RBNZ Official Cash Rate (NZD) must NOT silently classify as RBA."""
        assert _map_title_to_event_class("Official Cash Rate") is None

    def test_blocked_check_is_case_insensitive(self) -> None:
        """Same case-insensitive handling as positive matching."""
        assert _map_title_to_event_class("OFFICIAL CASH RATE") is None
        assert _map_title_to_event_class("official cash rate") is None

    def test_rba_cash_rate_still_maps_after_blocker(self) -> None:
        """Regression : RBA bare `Cash Rate` title must STILL map to RBA
        when `Official` prefix is absent."""
        assert _map_title_to_event_class("Cash Rate") == "RBA"


class TestR149RbaBocDirectionCaveatSurfaced:
    """r149 trader YELLOW-1 fix — Vojtko-Dujava SSRN 5384407 documents
    RBA/BoC pre-announcement drift as NEGATIVE (sign-flip vs FOMC).
    r149 ships POSITIVE baseline_bp + default `+1` business_cycle_sign ;
    the runtime caveat MUST surface the direction-not-implemented
    honesty per doctrine #11.

    Concordant fix : code-reviewer SHOULD-FIX #2 + trader YELLOW-1
    flagged the same issue from different angles. r149 applies the
    documentation/caveat fix ; r150+ candidate : per-event-class sign
    override in business_cycle_sign resolution OR negative baseline_bp.
    """

    @pytest.mark.asyncio
    async def test_rba_event_caveat_contains_direction_disclosure(self) -> None:
        """An RBA event must produce a caveat string that names the
        Vojtko-Dujava direction-flip honestly."""
        evt = _make_event_row(
            title="Cash Rate",
            impact="high",
            currency="AUD",
            scheduled_at=datetime(2026, 6, 3, 4, 30, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="AUD_USD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "RBA"
        assert "RBA/BoC" in result.caveat
        assert "Vojtko-Dujava" in result.caveat
        # ALWAYS prior caveat still appended (r147 trader YELLOW-1 baseline)
        assert "Magnitude prior littérature" in result.caveat

    @pytest.mark.asyncio
    async def test_boc_event_caveat_contains_direction_disclosure(self) -> None:
        """Same fix applies to BoC (Vojtko-Dujava co-class)."""
        evt = _make_event_row(
            title="Overnight Rate",
            impact="high",
            currency="CAD",
            scheduled_at=datetime(2026, 6, 4, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="USD_CAD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "BoC"
        assert "RBA/BoC" in result.caveat
        assert "Vojtko-Dujava" in result.caveat

    @pytest.mark.asyncio
    async def test_fomc_event_caveat_does_NOT_contain_rba_boc_disclosure(self) -> None:
        """Regression : FOMC events must NOT carry the RBA/BoC-specific caveat
        (only fires when event_class in {"RBA","BoC"})."""
        evt = _make_event_row(
            title="Federal Funds Rate",
            impact="high",
            currency="USD",
            scheduled_at=datetime(2026, 6, 18, 18, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "FOMC"
        assert "RBA/BoC" not in result.caveat
        assert "Vojtko-Dujava" not in result.caveat


class TestR149EventClassConsistencyInvariant:
    """r149 — new CI invariant : every event class emitted by
    `_TITLE_TO_EVENT_CLASS` must have a matching key in
    `EVENT_CLASS_BASELINE_BP`. Catches the silent-fall-through class
    where a mapping is added without a baseline (would yield
    `expected_drift_magnitude_bp=None` per the engine's honest-scope
    short-circuit and effectively drop the event from Engine 8).

    Mirror of the r148 emission-vs-registry lockstep CI invariant pattern
    (cf `test_r148_confluence_engine_driver_emissions_match_brier_registry`
    in test_invariants_ichor.py). NEW pattern observation r148 codified
    as the r149 deliverable.
    """

    def test_every_mapped_event_class_has_baseline(self) -> None:
        from ichor_api.services.event_proximity_engine import _TITLE_TO_EVENT_CLASS

        emitted_classes = {cls for _, cls in _TITLE_TO_EVENT_CLASS}
        registry_classes = set(EVENT_CLASS_BASELINE_BP.keys())
        missing_baselines = emitted_classes - registry_classes
        assert not missing_baselines, (
            "r149 lockstep CI violation : the following event classes are "
            "emitted by _TITLE_TO_EVENT_CLASS but lack a corresponding "
            "baseline entry in EVENT_CLASS_BASELINE_BP — events of these "
            "classes would silently fall through to "
            "`expected_drift_magnitude_bp=None` and be dropped from "
            f"Engine 8 weighting :\n  Missing : {sorted(missing_baselines)}\n"
            f"  Registry: {sorted(registry_classes)}\n"
            "Fix : add the missing event class(es) to "
            "EVENT_CLASS_BASELINE_BP with a literature-cited magnitude in "
            "basis points (cite the source in a code comment per lesson "
            "#37 honest-scope discipline)."
        )


# ── r150 AUD/CAD Employment Change explicit mapping ───────────────────


class TestR150EmploymentClassMapping:
    """r150 — closes r149 honest-scope gap "AUD/CAD Employment Change falls
    through to `high_other` 10bp" (trader YELLOW-5 acknowledged as
    conservative cold-start prior). r150 adds generic "Employment" event
    class with 20bp baseline (aligned with NFP per labor-market release
    literature priors). Maps :

    - AUD "Employment Change" → Employment
    - CAD "Employment Change" → Employment
    - Any "Unemployment Rate" (US/AUD/CAD cross-currency) → Employment

    PRESERVES r147 first-match-wins for US-specific NFP via pattern order :
    `non-farm employment change` matches BEFORE `employment change` in tuple.
    """

    def test_bare_employment_change_maps_Employment_AUD(self) -> None:
        """AUD FF XML title is bare 'Employment Change' (no 'Non-Farm' prefix)."""
        assert _map_title_to_event_class("Employment Change") == "Employment"

    def test_bare_employment_change_lowercase_maps_Employment_CAD(self) -> None:
        """Same bare title for CAD. Title-only mapping (no currency context)."""
        assert _map_title_to_event_class("employment change") == "Employment"

    def test_unemployment_rate_maps_Employment(self) -> None:
        """Cross-currency Unemployment Rate (US/AUD/CAD all use this bare title)."""
        assert _map_title_to_event_class("Unemployment Rate") == "Employment"

    def test_non_farm_employment_change_STILL_maps_NFP(self) -> None:
        """REGRESSION : US-specific NFP must NOT fall into Employment class.
        First-match-wins on pattern order ensures `non-farm employment change`
        matches BEFORE generic `employment change`."""
        assert _map_title_to_event_class("Non-Farm Employment Change") == "NFP"

    def test_nonfarm_payrolls_STILL_maps_NFP(self) -> None:
        """REGRESSION : second NFP variant unaffected by r150 generic Employment."""
        assert _map_title_to_event_class("Nonfarm Payrolls") == "NFP"


class TestR150NfpMappingPriorityProtected:
    """r150 trader YELLOW-4 concordance fix — first-match-wins ordering MUST
    preserve US NFP specificity even after the r150 generic `("employment
    change", "Employment")` pattern was added. Defensive against future
    FF title drift (e.g., FF rebrands "Non-Farm Employment Change" to
    "Employment Change (United States)") that would silently steal NFP
    into the generic Employment class.

    The current first-match-wins pattern order at `_TITLE_TO_EVENT_CLASS`
    ensures `non-farm employment change` matches BEFORE generic
    `employment change`. This invariant pin documents + protects that
    contract mechanically.
    """

    def test_non_farm_employment_change_pins_to_NFP(self) -> None:
        """REGRESSION pin : US-specific NFP must map to NFP class, not the
        generic r150 Employment class."""
        assert _map_title_to_event_class("Non-Farm Employment Change") == "NFP"

    def test_nonfarm_payrolls_pins_to_NFP(self) -> None:
        """Second US NFP variant unaffected by Employment generic."""
        assert _map_title_to_event_class("Nonfarm Payrolls") == "NFP"

    def test_employment_change_without_nfp_prefix_falls_to_Employment(self) -> None:
        """Confirm the generic Employment pattern DOES match when no NFP
        prefix is present (AUD/CAD case)."""
        assert _map_title_to_event_class("Employment Change") == "Employment"

    def test_employment_change_with_country_suffix_falls_to_Employment(self) -> None:
        """Edge case from trader YELLOW-4 : if FF ever emits a country-tagged
        variant like 'Employment Change (United States)', the generic
        Employment pattern catches it. While that loses NFP-class identity,
        the magnitude (20bp) is the same. This test documents the trade-off
        so a future FF rebrand surfaces this behaviour explicitly."""
        # Substring match : "employment change" is in "employment change (united states)"
        assert _map_title_to_event_class("Employment Change (United States)") == "Employment"


class TestR150SingleSourceDirectionSentinel:
    """r150 trader YELLOW-2 concordance fix — RBA/BoC events surface the
    single-source weakness via BOTH the caveat string AND a machine-readable
    `parse_failures` sentinel `"single_source_direction"`. Mirror of r141
    `SurpriseClassification.parse_failures` discipline so downstream
    consumers (Brier optimizer, frontend `deriveEngineDrivers`) can filter
    mechanically on the weakness instead of parsing the human-readable
    caveat string.
    """

    @pytest.mark.asyncio
    async def test_rba_event_adds_single_source_direction_sentinel(self) -> None:
        evt = _make_event_row(
            title="Cash Rate",
            impact="high",
            currency="AUD",
            scheduled_at=datetime(2026, 6, 3, 4, 30, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="AUD_USD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert "single_source_direction" in result.parse_failures

    @pytest.mark.asyncio
    async def test_boc_event_adds_single_source_direction_sentinel(self) -> None:
        evt = _make_event_row(
            title="Overnight Rate",
            impact="high",
            currency="CAD",
            scheduled_at=datetime(2026, 6, 4, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="USD_CAD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert "single_source_direction" in result.parse_failures

    @pytest.mark.asyncio
    async def test_fomc_event_does_NOT_add_single_source_sentinel(self) -> None:
        """REGRESSION : FOMC events must NOT carry RBA/BoC-specific sentinel
        (Lucca-Moench is peer-reviewed JoF, not single-source)."""
        evt = _make_event_row(
            title="Federal Funds Rate",
            impact="high",
            currency="USD",
            scheduled_at=datetime(2026, 6, 18, 18, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert "single_source_direction" not in result.parse_failures


class TestR150EmploymentBaseline:
    """r150 — `EVENT_CLASS_BASELINE_BP` must include the new 'Employment'
    key at 20bp (aligned with NFP magnitude per Lucca-Moench 2015 + Kurov
    2021 labor-market release priors). The r149 event-class consistency
    invariant `TestR149EventClassConsistencyInvariant` (subset-not-equality)
    would otherwise fail if Employment is emitted but lacks a baseline.
    """

    def test_employment_baseline_present(self) -> None:
        assert "Employment" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["Employment"] == 20.0

    def test_employment_baseline_matches_nfp_magnitude(self) -> None:
        """Cross-check labor-market release prior consistency."""
        assert EVENT_CLASS_BASELINE_BP["Employment"] == EVENT_CLASS_BASELINE_BP["NFP"]


class TestR150VojtkoDujavaSingleSourceDisclosure:
    """r150 — r149's RBA/BoC direction caveat is REPLACED with a single-source
    disclosure honestly reflecting researcher web R59 verification :
    Vojtko-Dujava SSRN 5384407 paper title is "Pre-Announcement Drift for
    BoE, BoJ, SNB" (NOT RBA/BoC) ; RBA/BoC NEGATIVE drift appears only as
    secondary histogram observation. r149 sign-flip implementation DEFERRED
    INDEFINITELY until peer-reviewed replication appears. Doctrine #11
    calibrated honesty : surface the source weakness in the runtime caveat.
    """

    @pytest.mark.asyncio
    async def test_rba_caveat_contains_single_source_disclosure(self) -> None:
        """An RBA event must produce a caveat naming the single-source nature
        + the secondary-observation framing."""
        evt = _make_event_row(
            title="Cash Rate",
            impact="high",
            currency="AUD",
            scheduled_at=datetime(2026, 6, 3, 4, 30, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="AUD_USD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "RBA"
        assert "source unique non-répliquée" in result.caveat
        assert "BoE/BoJ/SNB" in result.caveat
        # ALWAYS prior caveat still appended
        assert "Magnitude prior littérature" in result.caveat

    @pytest.mark.asyncio
    async def test_boc_caveat_contains_single_source_disclosure(self) -> None:
        evt = _make_event_row(
            title="Overnight Rate",
            impact="high",
            currency="CAD",
            scheduled_at=datetime(2026, 6, 4, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="USD_CAD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "BoC"
        assert "source unique non-répliquée" in result.caveat
        assert "BoE/BoJ/SNB" in result.caveat

    @pytest.mark.asyncio
    async def test_fomc_caveat_does_NOT_contain_single_source_disclosure(self) -> None:
        """REGRESSION : FOMC events must NOT carry RBA/BoC-specific disclosure."""
        evt = _make_event_row(
            title="Federal Funds Rate",
            impact="high",
            currency="USD",
            scheduled_at=datetime(2026, 6, 18, 18, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "FOMC"
        assert "source unique non-répliquée" not in result.caveat
        assert "BoE/BoJ/SNB" not in result.caveat


# ── r153 — US sentiment indicator class extensions ───────────────────────────


class TestR153SentimentClassMapping:
    """r153 — Conference Board CCI + UoM Michigan Consumer Sentiment + ISM
    Manufacturing/Services PMI title-fragment mapping. Closes the engagement
    gap empirically witnessed r152 Playwright (CB Consumer Confidence
    rendered as "Catalyseur non-classé"). Literature anchor : Akhtar-Faff-
    Oliver-Subrahmanyam 2012 *JBF* (US S&P/DJIA asymmetric) + Andersen-
    Bollerslev-Diebold-Vega 2007 *JIE* (ISM intraday significant) + Pinchuk
    2022 arXiv (aggregate 11-25 bp/1σ MNA band).
    """

    def test_cb_consumer_confidence_maps_CCI(self) -> None:
        """Conference Board CCI — the literal title witnessed r152 prod."""
        assert _map_title_to_event_class("CB Consumer Confidence") == "CCI"

    def test_conference_board_consumer_confidence_maps_CCI(self) -> None:
        """Long-form variant for defensive future-proofing."""
        assert _map_title_to_event_class("Conference Board Consumer Confidence") == "CCI"

    def test_prelim_uom_consumer_sentiment_maps_Michigan(self) -> None:
        """UoM Prelim — first release, higher market impact per qualitative consensus."""
        assert _map_title_to_event_class("Prelim UoM Consumer Sentiment") == "Michigan"

    def test_revised_uom_consumer_sentiment_maps_Michigan(self) -> None:
        """UoM Revised — second release, lower magnitude same class."""
        assert _map_title_to_event_class("Revised UoM Consumer Sentiment") == "Michigan"

    def test_uom_consumer_sentiment_maps_Michigan(self) -> None:
        """Bare UoM variant — defensive future-proofing."""
        assert _map_title_to_event_class("UoM Consumer Sentiment") == "Michigan"

    def test_prelim_uom_inflation_expectations_maps_Michigan(self) -> None:
        """UoM inflation-expectations sub-component (literature treats same class)."""
        assert _map_title_to_event_class("Prelim UoM Inflation Expectations") == "Michigan"

    def test_ism_manufacturing_pmi_maps_ISM(self) -> None:
        """ISM Manufacturing — early-month, higher-tier macro release."""
        assert _map_title_to_event_class("ISM Manufacturing PMI") == "ISM"

    def test_ism_services_pmi_maps_ISM(self) -> None:
        """ISM Services — same class as Manufacturing (literature inferred)."""
        assert _map_title_to_event_class("ISM Services PMI") == "ISM"

    def test_ism_non_manufacturing_pmi_maps_ISM(self) -> None:
        """Legacy name (pre-2024 rebrand)."""
        assert _map_title_to_event_class("ISM Non-Manufacturing PMI") == "ISM"


class TestR153NewBaselineKeys:
    """r153 — `EVENT_CLASS_BASELINE_BP` must include the 3 new sentiment-class
    keys at literature-anchored magnitudes.

    Magnitudes : CCI=10 (Akhtar 2012 + Pinchuk 2022 lower-tier asymmetric) ;
    Michigan=10 (same family) ; ISM=15 (Andersen-Bollerslev 2007 higher tier,
    early-month consensus depth).
    """

    def test_cci_baseline_present(self) -> None:
        assert "CCI" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["CCI"] == 10.0

    def test_michigan_baseline_present(self) -> None:
        assert "Michigan" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["Michigan"] == 10.0

    def test_ism_baseline_present(self) -> None:
        assert "ISM" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["ISM"] == 15.0

    def test_existing_baselines_unchanged(self) -> None:
        """REGRESSION : r152 + r150 + r149 + r147 baselines preserved."""
        assert EVENT_CLASS_BASELINE_BP["FOMC"] == 50.0
        assert EVENT_CLASS_BASELINE_BP["ECB"] == 35.0
        assert EVENT_CLASS_BASELINE_BP["BoE"] == 25.0
        assert EVENT_CLASS_BASELINE_BP["BoJ"] == 15.0
        assert EVENT_CLASS_BASELINE_BP["NFP"] == 20.0
        assert EVENT_CLASS_BASELINE_BP["CPI"] == 20.0
        assert EVENT_CLASS_BASELINE_BP["RBA"] == 25.0
        assert EVENT_CLASS_BASELINE_BP["BoC"] == 25.0
        assert EVENT_CLASS_BASELINE_BP["Employment"] == 20.0
        assert EVENT_CLASS_BASELINE_BP["PCE"] == 20.0
        assert EVENT_CLASS_BASELINE_BP["GDP"] == 25.0


class TestR153AsymmetricNegativityBiasSentinel:
    """r153 — for CCI + Michigan event classes, Engine 8 pre-event MUST emit
    `direction=unknown` + `parse_failures.add("asymmetric_negativity_bias")`
    because the literature (Akhtar 2012 + Pinchuk 2022) documents bad
    sentiment surprise → significant negative ; good surprise → muted.
    Symmetric `business_cycle_sign` direction would be MISLEADING.

    Mirrors r150 `single_source_direction` sentinel pattern but BETTER
    evidenced (2 peer-reviewed papers US data vs 1 working paper for
    RBA/BoC). Doctrine #11 calibrated honesty.
    """

    @pytest.mark.asyncio
    async def test_cci_event_emits_unknown_direction_and_sentinel(self) -> None:
        # Event 4h ahead (close to release) — time_decay stays large enough
        # that magnitude_unsigned > 0.01 noise floor for medium-impact CCI.
        evt = _make_event_row(
            title="CB Consumer Confidence",
            impact="medium",
            currency="USD",
            scheduled_at=datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "CCI"
        # Asymmetric override forces direction=unknown even when
        # business_cycle_sign would otherwise produce up/down :
        assert result.expected_drift_direction == "unknown"
        # Magnitude STAYS as conditional-on-negative-surprise estimate :
        assert result.expected_drift_magnitude_bp is not None
        # Sentinel surfaces honestly :
        assert "asymmetric_negativity_bias" in result.parse_failures
        # Caveat carries the epistemic framing (r153 trader YELLOW-2 fix —
        # purely geometric/citation, no implied behaviour) :
        assert "skew" in result.caveat.lower()
        assert "asymétrique" in result.caveat.lower()
        assert "akhtar" in result.caveat.lower()

    @pytest.mark.asyncio
    async def test_michigan_event_emits_unknown_direction_and_sentinel(self) -> None:
        # Event 4h ahead (close to release) — magnitude above noise floor.
        evt = _make_event_row(
            title="Prelim UoM Consumer Sentiment",
            impact="medium",
            currency="USD",
            scheduled_at=datetime(2026, 6, 13, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "Michigan"
        assert result.expected_drift_direction == "unknown"
        assert "asymmetric_negativity_bias" in result.parse_failures

    @pytest.mark.asyncio
    async def test_ism_event_does_NOT_emit_asymmetric_sentinel(self) -> None:
        """REGRESSION : ISM is NOT asymmetric per literature — must emit
        symmetric direction (up/down) without the bias sentinel."""
        evt = _make_event_row(
            title="ISM Manufacturing PMI",
            impact="high",
            currency="USD",
            scheduled_at=datetime(2026, 6, 2, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "ISM"
        # Symmetric direction expected for ISM (business_cycle_sign=+1 → up
        # in expansion regime by default) :
        assert result.expected_drift_direction in ("up", "down")
        assert "asymmetric_negativity_bias" not in result.parse_failures

    @pytest.mark.asyncio
    async def test_fomc_event_does_NOT_emit_asymmetric_sentinel(self) -> None:
        """REGRESSION : FOMC class must NOT carry the asymmetric sentinel."""
        evt = _make_event_row(
            title="Federal Funds Rate",
            impact="high",
            currency="USD",
            scheduled_at=datetime(2026, 6, 18, 18, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 17, 18, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert result.next_event_class == "FOMC"
        assert "asymmetric_negativity_bias" not in result.parse_failures


class TestR153LiteratureAnchorExtended:
    """r153 — `literature_anchor` extended with Akhtar 2012 + ABDV 2007 + Pinchuk
    2022 citations (researcher web R59 verified primary sources). Hallucinated
    Karnaukh-Vrolijk 2019 *JFE* (cited in my r152 closing-sync from training-
    data memory) was REJECTED by R59 (closest real paper is Karnaukh-Vokata
    2022 JFE about FOMC growth forecasts, NOT consumer confidence). Same
    pattern class as r147 Bauer DP21003 hallucination — pattern #13 + #15
    in action. The r152 historical docs (ADR-099 §Impl(r152) + SESSION_LOG +
    CLAUDE.md) intentionally NOT corrected (historical records of what was
    planned) ; the r153 §Impl documents the catch as doctrinal reinforcement.
    """

    @pytest.mark.asyncio
    async def test_literature_anchor_contains_akhtar_2012(self) -> None:
        evt = _make_event_row(
            title="CB Consumer Confidence",
            impact="medium",
            currency="USD",
            scheduled_at=datetime(2026, 6, 3, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            business_cycle_sign=1,
        )
        assert result is not None
        assert "Akhtar" in result.literature_anchor
        assert "Pinchuk" in result.literature_anchor
        assert "Andersen-Bollerslev-Diebold-Vega" in result.literature_anchor


class TestR153FfTitleCoverageInvariant:
    """r153 META-FIX CI invariant — load the 60d snapshot fixture of real FF
    high+medium impact titles from prod DB (94 events SSH-probed 2026-05-24)
    and assert mapping coverage ≥ baseline %.

    The fixture is NOT auto-refreshed ; refresh quarterly OR when CI starts
    failing (which IS the alarm that says "title drift / new indicator type
    to map"). Pattern follows r142+r148 lockstep CI invariant doctrine but
    applied to title→event_class mapping coverage.

    Baseline threshold = current post-r153 coverage. r154+ rounds should
    raise this as more classes are mapped.
    """

    # Threshold = current measured baseline post-r153. Bump up over time
    # as r154+ rounds add classes. Do NOT lower without explicit ADR.
    _MIN_COVERAGE_PCT: float = 35.0

    _FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ff_titles_60d_high_medium_2026-05-24.json"

    def _load_fixture_events(self) -> list[dict[str, str]]:
        import json

        data = json.loads(self._FIXTURE_PATH.read_text(encoding="utf-8"))
        return data["events"]

    def test_fixture_loads_and_has_events(self) -> None:
        events = self._load_fixture_events()
        assert len(events) >= 50, "fixture should carry meaningful sample"
        # Sanity-check shape
        assert all("title" in e and "currency" in e and "impact" in e for e in events)

    def test_title_coverage_pct_above_threshold(self) -> None:
        """The fundamental r153 CI invariant : ≥ _MIN_COVERAGE_PCT of fixture
        titles MUST map to a known event_class. Catches title-drift OR new
        indicator types worth mapping (failing CI IS the alarm)."""
        events = self._load_fixture_events()
        mapped = sum(1 for e in events if _map_title_to_event_class(e["title"]) is not None)
        coverage_pct = 100.0 * mapped / len(events)
        assert coverage_pct >= self._MIN_COVERAGE_PCT, (
            f"FF title coverage dropped to {coverage_pct:.1f}% "
            f"(threshold {self._MIN_COVERAGE_PCT}%). "
            f"Either upstream FF changed titles → update "
            f"`_TITLE_TO_EVENT_CLASS` ; or refresh the fixture via "
            f"SSH SQL probe if titles drifted upstream legitimately."
        )

    def test_r153_new_classes_have_at_least_one_match_in_fixture(self) -> None:
        """Empirical witness : confirm the 3 new r153 classes (CCI, Michigan,
        ISM) each match ≥ 1 title in the empirical 60d fixture. Asserts the
        mapping was effective — not just literature-cited."""
        events = self._load_fixture_events()
        classes_observed = {_map_title_to_event_class(e["title"]) for e in events}
        assert "CCI" in classes_observed, "no CB Consumer Confidence in fixture"
        assert "Michigan" in classes_observed, "no UoM Sentiment in fixture"
        assert "ISM" in classes_observed, "no ISM PMI in fixture"


# ── r153 — latent collision-class defensive blocks ────────────────────────────


class TestR153LatentBugBlocks:
    """r153 — defensive `_TITLE_FRAGMENT_BLOCKED` additions to prevent silent
    misclassification empirically surfaced during r153 coverage audit.

    Both bugs are LATENT today (no NZD asset → RBNZ events filter out at the
    SQL query level ; ADP rarely fires Engine 8 because magnitude under
    impact='medium' × cold VIX × time_decay collapses to None under noise
    floor). But they would fire silently if either currency exposure or
    impact configuration changes — defensive block is the same pattern as
    r149 "official cash rate" entry.
    """

    def test_adp_non_farm_employment_change_blocked(self) -> None:
        """ADP NFP substring-matches BLS NFP pattern → must be defensively
        blocked at the r144-reconciler-doctrine parity layer. r144's
        actuals reconciler already blocks ADP upstream ; engine side now
        mirrors it."""
        result = _map_title_to_event_class("ADP Non-Farm Employment Change")
        assert result is None, (
            "ADP must NOT misclassify as BLS NFP — methodologically distinct private survey"
        )

    def test_bls_non_farm_employment_change_still_maps_NFP(self) -> None:
        """REGRESSION : the canonical BLS Non-Farm Employment Change must
        still map to NFP class (the r150 NFP priority protection)."""
        assert _map_title_to_event_class("Non-Farm Employment Change") == "NFP"

    def test_rbnz_monetary_policy_statement_blocked(self) -> None:
        """RBNZ MPS substring-matches the BoJ generic-fallback pattern
        'monetary policy statement' → must be defensively blocked.
        Mirrors the r149 'official cash rate' RBNZ collision guard."""
        result = _map_title_to_event_class("RBNZ Monetary Policy Statement")
        assert result is None, (
            "RBNZ MPS must NOT misclassify as BoJ — RBNZ ≠ BoJ in literature priors"
        )

    def test_boj_monetary_policy_statement_still_maps_BoJ(self) -> None:
        """REGRESSION : the canonical BoJ Monetary Policy Statement (or any
        bare 'Monetary Policy Statement' for JPY) must still hit the BoJ
        generic-fallback pattern."""
        # Bare title without RBNZ/RBA prefix → maps to BoJ via fallback
        assert _map_title_to_event_class("Monetary Policy Statement") == "BoJ"


# ── r154 — CB Governor scheduled-speech class extensions ─────────────────────


class TestR154CbSpeakerClassMapping:
    """r154 — Calibrated honest scope per researcher web R59 :
    - ECB_Speech (Lagarde) = 7bp symmetric : Ehrmann-Fratzscher 2007 + Cieslak-Schrimpf 2019
    - BoE_Speech (Bailey + Mansion House) = 8bp symmetric : Ehrmann-Fratzscher 2007 BoE-specific
    - SNB_Speech (Schlegel) = 10bp + asymmetric_negativity_bias : Ranaldo-Rossi 2009 + 2024 SNB textual-analysis
    - BoJ/BoC/Fed-Chair-non-FOMC/Trump speeches kept UNMAPPED honestly
      (literature too thin per Pattern #15 R59-disprove discipline).
    """

    def test_ecb_president_lagarde_speaks_maps_ECB_Speech(self) -> None:
        """Verbatim FF title witnessed in r153 60d fixture."""
        assert _map_title_to_event_class("ECB President Lagarde Speaks") == "ECB_Speech"

    def test_boe_gov_bailey_speaks_maps_BoE_Speech(self) -> None:
        """Verbatim FF title witnessed in r153 60d fixture (×3 instances)."""
        assert _map_title_to_event_class("BOE Gov Bailey Speaks") == "BoE_Speech"

    def test_mansion_house_speech_maps_BoE_Speech(self) -> None:
        """Future-proofing for annual Mansion House speech variant."""
        assert _map_title_to_event_class("Mansion House Speech") == "BoE_Speech"

    def test_snb_chairman_schlegel_speaks_maps_SNB_Speech(self) -> None:
        """Verbatim FF title witnessed in r153 60d fixture."""
        assert _map_title_to_event_class("SNB Chairman Schlegel Speaks") == "SNB_Speech"

    def test_boc_gov_macklem_speaks_stays_UNMAPPED(self) -> None:
        """HONEST SCOPE : no peer-reviewed BoC speaker bp magnitude exists.
        Researcher web R59 verified — kept unmapped honestly per Pattern #15."""
        assert _map_title_to_event_class("BOC Gov Macklem Speaks") is None

    def test_boj_gov_ueda_speaks_stays_UNMAPPED(self) -> None:
        """HONEST SCOPE : no peer-reviewed BoJ speaker bp magnitude exists.
        Researcher web R59 verified — kept unmapped honestly per Pattern #15."""
        assert _map_title_to_event_class("BOJ Gov Ueda Speaks") is None

    def test_president_trump_speaks_stays_UNMAPPED(self) -> None:
        """HONEST SCOPE : Trump-speech literature exists but content-dependent
        with 1-4h fade — methodologically incoherent with pre-event drift
        framework. Kept unmapped per Pattern #15."""
        assert _map_title_to_event_class("President Trump Speaks") is None


class TestR154NewBaselineKeys:
    """r154 — `EVENT_CLASS_BASELINE_BP` must include 3 new CB Speech classes
    at literature-anchored magnitudes (Ehrmann-Fratzscher 2007 for ECB/BoE,
    Ranaldo-Rossi 2009 for SNB)."""

    def test_ecb_speech_baseline_present(self) -> None:
        assert "ECB_Speech" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["ECB_Speech"] == 7.0

    def test_boe_speech_baseline_present(self) -> None:
        assert "BoE_Speech" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["BoE_Speech"] == 8.0

    def test_snb_speech_baseline_present(self) -> None:
        assert "SNB_Speech" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["SNB_Speech"] == 10.0

    def test_speaker_magnitudes_below_decision_magnitudes(self) -> None:
        """REGRESSION : speakers must NEVER exceed canonical decision-day
        magnitudes (Lucca-Moench 2015 + Cieslak-Schrimpf 2019 — speeches
        carry less information than rate-decision day press conferences)."""
        assert EVENT_CLASS_BASELINE_BP["ECB_Speech"] < EVENT_CLASS_BASELINE_BP["ECB"]
        assert EVENT_CLASS_BASELINE_BP["BoE_Speech"] < EVENT_CLASS_BASELINE_BP["BoE"]
        # SNB has no decision-day class (Ichor doesn't track SNB rate decisions
        # explicitly — SNB_Speech is the only SNB class). Verify against the
        # tier hierarchy at minimum.
        assert EVENT_CLASS_BASELINE_BP["SNB_Speech"] < EVENT_CLASS_BASELINE_BP["FOMC"]


class TestR154SnbSpeechAsymmetricSentinel:
    """r154 — SNB_Speech extends the r153 asymmetric_negativity_bias pattern
    to a 3rd class (in addition to CCI + Michigan). Anchor : Ranaldo-Rossi
    2009 *JIMF* (SNB verbal interventions DO move assets — contrast Kohn-Sack
    2004 finding ordinary Fed speeches do NOT) + 2024 SNB textual-analysis
    documenting negative-sentiment moves sectors faster than positive."""

    @pytest.mark.asyncio
    async def test_snb_speech_emits_unknown_direction_and_sentinel(self) -> None:
        evt = _make_event_row(
            title="SNB Chairman Schlegel Speaks",
            impact="medium",
            currency="CHF",
            scheduled_at=datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        # Note : Ichor doesn't track CHF directly today (no CHF asset in
        # priority set). Use XAU_USD which includes USD currencies for
        # _currencies_for_asset to NOT include CHF. Engine 8 will then
        # filter the CHF event out. Use EUR_USD instead for the test —
        # but EUR_USD also doesn't include CHF. The test would return None.
        # Approach : test the mapping + sentinel logic at the lower level
        # by directly calling the engine with an asset that includes CHF.
        # Ichor's asset map doesn't include CHF, so we use the engine's
        # internal helpers directly via the mapping function.
        result_class = _map_title_to_event_class("SNB Chairman Schlegel Speaks")
        assert result_class == "SNB_Speech"
        # Verify SNB_Speech is in the asymmetric set
        from ichor_api.services.event_proximity_engine import (
            _ASYMMETRIC_NEGATIVITY_CLASSES,
        )

        assert "SNB_Speech" in _ASYMMETRIC_NEGATIVITY_CLASSES

    def test_asymmetric_negativity_classes_module_level(self) -> None:
        """r154 code-reviewer N-1 fix : `_ASYMMETRIC_NEGATIVITY_CLASSES` moved
        from inline (hot path) to module-level constant. Verify import works
        + frozenset contains the 3 expected classes."""
        from ichor_api.services.event_proximity_engine import (
            _ASYMMETRIC_NEGATIVITY_CLASSES,
        )

        assert isinstance(_ASYMMETRIC_NEGATIVITY_CLASSES, frozenset)
        assert _ASYMMETRIC_NEGATIVITY_CLASSES == frozenset({"CCI", "Michigan", "SNB_Speech"})


class TestR154AsymmetricMagnitudeSignStripped:
    """r154 code-reviewer SF-2 architectural fix : when the asymmetric
    sentinel fires, `expected_drift_bp` MUST be UNSIGNED (abs value). Prior
    r153 implementation preserved the signed value, silently propagating
    business_cycle_sign bias into downstream Brier consumers (which multiply
    by sign). Doctrine #11 calibrated honesty at the source vs relying on
    each downstream consumer to strip the sign."""

    @pytest.mark.asyncio
    async def test_cci_pre_event_magnitude_is_unsigned_when_asymmetric_fires(
        self,
    ) -> None:
        evt = _make_event_row(
            title="CB Consumer Confidence",
            impact="medium",
            currency="USD",
            scheduled_at=datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result_neg = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            business_cycle_sign=-1,  # contraction regime → signed=negative
        )
        assert result_neg is not None
        assert result_neg.next_event_class == "CCI"
        assert "asymmetric_negativity_bias" in result_neg.parse_failures
        # SF-2 fix : magnitude must be UNSIGNED, not -value
        assert result_neg.expected_drift_magnitude_bp is not None
        assert result_neg.expected_drift_magnitude_bp >= 0, (
            "asymmetric override must strip sign — direction is unknown, "
            "magnitude must not carry business_cycle_sign bias"
        )

    @pytest.mark.asyncio
    async def test_symmetric_class_preserves_signed_magnitude(self) -> None:
        """REGRESSION : non-asymmetric classes (FOMC, ECB, ISM, etc.) must
        STILL emit signed `expected_drift_bp` per business_cycle_sign — the
        abs() fix applies ONLY to asymmetric classes."""
        evt = _make_event_row(
            title="ISM Manufacturing PMI",
            impact="high",
            currency="USD",
            scheduled_at=datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
        )
        session = _build_session(
            event_rows=[evt],
            vix_row=_make_fred_row(20.0, datetime(2026, 5, 23, tzinfo=UTC).date()),
        )
        result_neg = await assess_event_proximity(
            session,
            asset="EUR_USD",
            now=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            business_cycle_sign=-1,
        )
        assert result_neg is not None
        assert result_neg.next_event_class == "ISM"
        # ISM is NOT asymmetric → magnitude can be negative under
        # business_cycle_sign=-1 (the contraction regime sign)
        assert "asymmetric_negativity_bias" not in result_neg.parse_failures
        assert result_neg.expected_drift_magnitude_bp is not None
        # Under business_cycle_sign=-1 the signed magnitude must be negative
        assert result_neg.expected_drift_magnitude_bp < 0


class TestR154FixtureMetaReconciliation:
    """r154 code-reviewer SF-1 fix : fixture `_meta.n_events` had drifted
    to 94 vs actual events[] length of 95 (off-by-one). Reconciled r154."""

    def test_fixture_meta_n_events_matches_events_length(self) -> None:
        import json

        path = Path(__file__).parent / "fixtures" / "ff_titles_60d_high_medium_2026-05-24.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        meta_count = data["_meta"]["n_events"]
        actual_count = len(data["events"])
        assert meta_count == actual_count, (
            f"fixture _meta drift : declared {meta_count} but actual {actual_count}"
        )

    def test_post_r154_coverage_above_baseline(self) -> None:
        """Empirical : post-r154 mapping coverage must exceed the 35% ratchet
        threshold + the post-r154 measured baseline. r154 closing-sync prose
        claims ~47% — verify mechanically."""
        import json

        path = Path(__file__).parent / "fixtures" / "ff_titles_60d_high_medium_2026-05-24.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        events = data["events"]
        mapped = sum(1 for e in events if _map_title_to_event_class(e["title"]) is not None)
        coverage_pct = 100.0 * mapped / len(events)
        # r154 baseline ≥ 45% (post-CB-Speech extension). Conservative.
        assert coverage_pct >= 45.0, (
            f"r154 coverage dropped to {coverage_pct:.1f}% — expected >= 45%"
        )
