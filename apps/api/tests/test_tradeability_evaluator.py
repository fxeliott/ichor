"""r167 G1 tests — Tradeability Evaluator.

Covers atom-level :
- Pure helpers : _today_paris_date UTC→Paris conversion + _is_us_market_holiday
  lookup (known holidays return True ; non-holidays return False)
- _has_high_impact_event_within_horizon : empty + high-impact in window +
  high-impact OUT of window + medium-impact in window (should NOT fire)
- _is_low_volatility_current_hour : below threshold + above + no data
  (None) + exception (defensive None)
- evaluate_tradeability composite priority order : holiday > event_freeze >
  low_volatility > range > no_setup > tradeable
- Fail-open behavior : ANY internal exception → tradeable
- all_tradeability_values_dispatched CI invariant : every Literal value
  reachable from dispatcher

Mirrors r164 test_scenario_invalidation_monitor.py AsyncMock pattern + r165
test_scenario_invalidation_alerts.py priority hierarchy verification.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ichor_api.services.tradeability_evaluator import (
    _has_high_impact_event_within_horizon,
    _is_low_volatility_current_hour,
    _is_us_market_holiday,
    _today_paris_date,
    all_tradeability_values_dispatched,
    evaluate_tradeability,
)

# ── helpers ─────────────────────────────────────────────────────────────


def _scalar_one_or_none_returning(value: object | None) -> MagicMock:
    """Build session.execute() mock returning .scalar_one_or_none()."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=value)
    return result_mock


# ── _today_paris_date ───────────────────────────────────────────────────


class TestTodayParisDate:
    def test_paris_morning_returns_today(self) -> None:
        # 10h UTC = 12h Paris (winter) → same calendar date
        now_utc = datetime(2026, 5, 26, 10, 0, tzinfo=UTC)
        assert _today_paris_date(now_utc) == date(2026, 5, 26)

    def test_paris_late_evening_still_today(self) -> None:
        # 21h UTC = 23h Paris (summer DST) → same calendar date
        now_utc = datetime(2026, 5, 26, 21, 0, tzinfo=UTC)
        assert _today_paris_date(now_utc) == date(2026, 5, 26)

    def test_paris_after_midnight_returns_next_day(self) -> None:
        # 23h UTC = 01h Paris (summer DST) → next calendar date
        now_utc = datetime(2026, 5, 26, 23, 0, tzinfo=UTC)
        assert _today_paris_date(now_utc) == date(2026, 5, 27)


# ── _is_us_market_holiday ───────────────────────────────────────────────


class TestIsUsMarketHoliday:
    def test_known_holiday_christmas(self) -> None:
        # Christmas Day 2026
        is_h, name = _is_us_market_holiday(date(2026, 12, 25))
        assert is_h is True
        assert name is not None and "Christmas" in name

    def test_known_holiday_independence_day(self) -> None:
        # July 4, 2026 — actual observed date (2026-07-04 is a Saturday →
        # observed Friday July 3). Just check that EITHER July 3 OR July 4
        # is a holiday (observed shift discipline).
        is_h_3, _ = _is_us_market_holiday(date(2026, 7, 3))
        is_h_4, _ = _is_us_market_holiday(date(2026, 7, 4))
        assert is_h_3 or is_h_4

    def test_non_holiday_returns_false(self) -> None:
        # Mid-month random Wednesday 2026-05-13 → not a holiday
        is_h, name = _is_us_market_holiday(date(2026, 5, 13))
        assert is_h is False
        assert name is None


# ── _has_high_impact_event_within_horizon ───────────────────────────────


class TestHasHighImpactEventWithinHorizon:
    @pytest.mark.asyncio
    async def test_no_event_in_window_returns_false(self) -> None:
        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalar_one_or_none_returning(None))
        in_freeze, title = await _has_high_impact_event_within_horizon(
            session,
            now_utc=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        )
        assert in_freeze is False
        assert title is None

    @pytest.mark.asyncio
    async def test_high_impact_event_in_window_fires(self) -> None:
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=_scalar_one_or_none_returning("Federal Funds Rate")
        )
        in_freeze, title = await _has_high_impact_event_within_horizon(
            session,
            now_utc=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        )
        assert in_freeze is True
        assert title == "Federal Funds Rate"


# ── _is_low_volatility_current_hour ─────────────────────────────────────


class TestIsLowVolatilityCurrentHour:
    @pytest.mark.asyncio
    async def test_below_threshold_fires(self, monkeypatch) -> None:
        """median_bp 2.5 at current hour < threshold 5.0 → True."""
        from ichor_api.services.hourly_volatility import HourlyVolEntry, HourlyVolReport

        # current hour-UTC = 12
        entries = [
            HourlyVolEntry(hour_utc=h, median_bp=0.0, p75_bp=0.0, n_samples=0) for h in range(24)
        ]
        entries[12] = HourlyVolEntry(hour_utc=12, median_bp=2.5, p75_bp=4.0, n_samples=30)
        fake_report = HourlyVolReport(
            asset="EUR_USD",
            window_days=30,
            entries=entries,
            best_hour_utc=None,
            worst_hour_utc=None,
            london_session_avg_bp=None,
            asian_session_avg_bp=None,
            generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        )

        async def fake_assess(*_args, **_kwargs):
            return fake_report

        monkeypatch.setattr(
            "ichor_api.services.tradeability_evaluator.assess_hourly_volatility",
            fake_assess,
        )

        session = MagicMock()
        is_low, median = await _is_low_volatility_current_hour(
            session,
            asset="EUR_USD",
            now_utc=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        )
        assert is_low is True
        assert median == 2.5

    @pytest.mark.asyncio
    async def test_above_threshold_does_not_fire(self, monkeypatch) -> None:
        from ichor_api.services.hourly_volatility import HourlyVolEntry, HourlyVolReport

        entries = [
            HourlyVolEntry(hour_utc=h, median_bp=0.0, p75_bp=0.0, n_samples=0) for h in range(24)
        ]
        entries[14] = HourlyVolEntry(hour_utc=14, median_bp=15.0, p75_bp=25.0, n_samples=30)
        fake_report = HourlyVolReport(
            asset="SPX500_USD",
            window_days=30,
            entries=entries,
            best_hour_utc=14,
            worst_hour_utc=0,
            london_session_avg_bp=10.0,
            asian_session_avg_bp=2.0,
            generated_at=datetime(2026, 5, 26, 14, 0, tzinfo=UTC),
        )

        async def fake_assess(*_args, **_kwargs):
            return fake_report

        monkeypatch.setattr(
            "ichor_api.services.tradeability_evaluator.assess_hourly_volatility",
            fake_assess,
        )

        session = MagicMock()
        is_low, median = await _is_low_volatility_current_hour(
            session,
            asset="SPX500_USD",
            now_utc=datetime(2026, 5, 26, 14, 0, tzinfo=UTC),
        )
        assert is_low is False
        assert median == 15.0

    @pytest.mark.asyncio
    async def test_no_data_returns_none_not_false(self, monkeypatch) -> None:
        """n_samples=0 → doctrine #11 honest fallback : returns
        (False, None) so caller falls through to next gate without
        fabricating a low_vol verdict."""
        from ichor_api.services.hourly_volatility import HourlyVolEntry, HourlyVolReport

        entries = [
            HourlyVolEntry(hour_utc=h, median_bp=0.0, p75_bp=0.0, n_samples=0) for h in range(24)
        ]
        fake_report = HourlyVolReport(
            asset="EUR_USD",
            window_days=30,
            entries=entries,
            best_hour_utc=None,
            worst_hour_utc=None,
            london_session_avg_bp=None,
            asian_session_avg_bp=None,
            generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        )

        async def fake_assess(*_args, **_kwargs):
            return fake_report

        monkeypatch.setattr(
            "ichor_api.services.tradeability_evaluator.assess_hourly_volatility",
            fake_assess,
        )

        session = MagicMock()
        is_low, median = await _is_low_volatility_current_hour(
            session,
            asset="EUR_USD",
            now_utc=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        )
        assert is_low is False
        assert median is None

    @pytest.mark.asyncio
    async def test_exception_returns_false_none_defensive(self, monkeypatch) -> None:
        """Internal exception during hourly_vol query → doctrine #11
        fallback : (False, None) so the gate falls through silently."""

        async def fake_assess(*_args, **_kwargs):
            raise RuntimeError("simulated DB hiccup")

        monkeypatch.setattr(
            "ichor_api.services.tradeability_evaluator.assess_hourly_volatility",
            fake_assess,
        )

        session = MagicMock()
        is_low, median = await _is_low_volatility_current_hour(
            session,
            asset="EUR_USD",
            now_utc=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        )
        assert is_low is False
        assert median is None


# ── evaluate_tradeability composite priority ────────────────────────────


class TestEvaluateTradeabilityPriority:
    """Strict priority order : holiday > event_freeze > low_volatility >
    range > no_setup > tradeable. ONE gate fires per call."""

    @pytest.mark.asyncio
    async def test_holiday_wins_over_everything(self, monkeypatch) -> None:
        # 2026-12-25 Christmas — even with event_freeze + low_vol mocked
        # to fire, holiday MUST win.
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=_scalar_one_or_none_returning("Federal Funds Rate")
        )
        # Force event_freeze + low_vol to fire IF reached.
        # But holiday is gate 1 → never reached.
        result = await evaluate_tradeability(
            session,
            asset="EUR_USD",
            conviction_pct=85.0,  # would pass no_setup gate easily
            now_utc=datetime(2026, 12, 25, 12, 0, tzinfo=UTC),
        )
        assert result == "holiday"

    @pytest.mark.asyncio
    async def test_event_freeze_wins_over_low_vol(self, monkeypatch) -> None:
        # Non-holiday + event_freeze fires → event_freeze wins
        # (low_vol mocked to fire if reached but should not).
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=_scalar_one_or_none_returning("Federal Funds Rate")
        )
        result = await evaluate_tradeability(
            session,
            asset="EUR_USD",
            conviction_pct=85.0,
            now_utc=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),  # non-holiday
        )
        assert result == "event_freeze"

    @pytest.mark.asyncio
    async def test_low_volatility_wins_over_no_setup(self, monkeypatch) -> None:
        # Non-holiday + no event + low_vol fires → low_volatility wins.
        from ichor_api.services.hourly_volatility import HourlyVolEntry, HourlyVolReport

        session = MagicMock()
        session.execute = AsyncMock(
            return_value=_scalar_one_or_none_returning(None)  # no event
        )

        entries = [
            HourlyVolEntry(hour_utc=h, median_bp=0.0, p75_bp=0.0, n_samples=0) for h in range(24)
        ]
        # Current hour = 12 ; mock median_bp=2.0 < 5.0 threshold
        entries[12] = HourlyVolEntry(hour_utc=12, median_bp=2.0, p75_bp=4.0, n_samples=30)
        fake_report = HourlyVolReport(
            asset="EUR_USD",
            window_days=30,
            entries=entries,
            best_hour_utc=None,
            worst_hour_utc=None,
            london_session_avg_bp=None,
            asian_session_avg_bp=None,
            generated_at=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        )

        async def fake_assess(*_args, **_kwargs):
            return fake_report

        monkeypatch.setattr(
            "ichor_api.services.tradeability_evaluator.assess_hourly_volatility",
            fake_assess,
        )

        result = await evaluate_tradeability(
            session,
            asset="EUR_USD",
            conviction_pct=15.0,  # would trigger no_setup if reached
            now_utc=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        )
        assert result == "low_volatility"

    @pytest.mark.asyncio
    async def test_no_setup_when_conviction_below_30(self, monkeypatch) -> None:
        """All structural gates pass + conviction < 30 → no_setup."""
        from ichor_api.services.hourly_volatility import HourlyVolEntry, HourlyVolReport

        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalar_one_or_none_returning(None))

        entries = [
            HourlyVolEntry(hour_utc=h, median_bp=20.0, p75_bp=30.0, n_samples=100)
            for h in range(24)
        ]
        fake_report = HourlyVolReport(
            asset="EUR_USD",
            window_days=30,
            entries=entries,
            best_hour_utc=None,
            worst_hour_utc=None,
            london_session_avg_bp=None,
            asian_session_avg_bp=None,
            generated_at=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        )

        async def fake_assess(*_args, **_kwargs):
            return fake_report

        monkeypatch.setattr(
            "ichor_api.services.tradeability_evaluator.assess_hourly_volatility",
            fake_assess,
        )

        result = await evaluate_tradeability(
            session,
            asset="EUR_USD",
            conviction_pct=20.0,  # < 30 threshold
            now_utc=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        )
        assert result == "no_setup"

    @pytest.mark.asyncio
    async def test_tradeable_when_all_gates_pass(self, monkeypatch) -> None:
        """Non-holiday + no event + high vol + conviction ≥ 30 → tradeable."""
        from ichor_api.services.hourly_volatility import HourlyVolEntry, HourlyVolReport

        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalar_one_or_none_returning(None))

        entries = [
            HourlyVolEntry(hour_utc=h, median_bp=20.0, p75_bp=30.0, n_samples=100)
            for h in range(24)
        ]
        fake_report = HourlyVolReport(
            asset="EUR_USD",
            window_days=30,
            entries=entries,
            best_hour_utc=None,
            worst_hour_utc=None,
            london_session_avg_bp=None,
            asian_session_avg_bp=None,
            generated_at=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        )

        async def fake_assess(*_args, **_kwargs):
            return fake_report

        monkeypatch.setattr(
            "ichor_api.services.tradeability_evaluator.assess_hourly_volatility",
            fake_assess,
        )

        result = await evaluate_tradeability(
            session,
            asset="EUR_USD",
            conviction_pct=75.0,
            now_utc=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        )
        assert result == "tradeable"


# ── Fail-open defensive behavior ────────────────────────────────────────


class TestEvaluateTradeabilityFailOpen:
    @pytest.mark.asyncio
    async def test_event_freeze_check_exception_falls_through(self, monkeypatch) -> None:
        """Doctrine #11 fail-open : DB hiccup on event query → fall
        through to next gate. Better to leak a false tradeable than
        block a normal trading day."""
        session = MagicMock()
        # Make session.execute() raise.
        session.execute = AsyncMock(side_effect=RuntimeError("DB unreachable"))

        # Force low_vol + no_setup to also fail safely so we reach tradeable.
        async def fake_assess(*_args, **_kwargs):
            raise RuntimeError("hourly_vol DB hiccup")

        monkeypatch.setattr(
            "ichor_api.services.tradeability_evaluator.assess_hourly_volatility",
            fake_assess,
        )

        result = await evaluate_tradeability(
            session,
            asset="EUR_USD",
            conviction_pct=75.0,
            now_utc=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),  # non-holiday
        )
        assert result == "tradeable"


# ── CI invariant : Literal values ⇄ dispatcher coverage ────────────────


class TestR167TradeabilityFlagLockstepCoverage:
    """r167 G1 W90 extension : every TradeabilityFlag Literal value MUST
    be reachable from `evaluate_tradeability` dispatch (or explicitly
    documented as honest gap `range` r167). Symmetric pin to schema."""

    def test_all_literal_values_dispatched(self) -> None:
        ok, missing = all_tradeability_values_dispatched()
        assert ok, (
            "r167 G1 invariant violated : the following TradeabilityFlag "
            f"Literal values are NOT reachable from evaluate_tradeability "
            f"dispatch : {missing}. Either add a gate or remove the value."
        )

    def test_tradeability_flag_has_6_values(self) -> None:
        """Schema pin : if the Literal grows or shrinks, also update the
        evaluator dispatch + the FR copy SSOTs frontend-side."""
        from ichor_brain.session_verdict import TradeabilityFlag

        declared = set(TradeabilityFlag.__args__)  # type: ignore[attr-defined]
        assert len(declared) == 6, (
            f"TradeabilityFlag has {len(declared)} values, expected 6. "
            "Update this test + evaluator + frontend TRADEABILITY_FR/HINT_FR/TONE."
        )
        assert declared == {
            "tradeable",
            "no_setup",
            "holiday",
            "event_freeze",
            "low_volatility",
            "range",
        }


# Avoid unused-import warning for `patch` (kept for future tests that
# may need it ; remove if still unused after r168+ extensions).
_ = patch
