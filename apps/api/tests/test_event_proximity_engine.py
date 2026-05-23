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


class TestBrierLockstepWithR147(TestAdr017Invariants):
    """r147 extension of r142 brier_optimizer factor names lockstep guard.
    The new "event_anticipation" factor MUST appear in BOTH
    `brier_optimizer.DEFAULT_FACTOR_NAMES` AND
    `cli.run_brier_optimizer._FACTOR_NAMES` lists.
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
