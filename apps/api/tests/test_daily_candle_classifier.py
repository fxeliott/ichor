"""r168b G4 tests for ``daily_candle_classifier`` — pure mechanical
candle classification + Garman-Klass 1980 variance + composite
range-bound rule consumed by ``tradeability_evaluator`` Gate 4.

Eliot's §IV.4 verbatim mandate : « Bougie d'incertitude après baisse →
fin baisse probable » + §VIII « avoid range markets ». r168b mechanises
this through a composite rule (uncertainty candle AND compressed
Garman-Klass variance) that unblocks the ``TradeabilityFlag = "range"``
literal which returned ``always False`` since r167 ship.

Pattern #15 R59 doctrinal posture preserved : the tests never assert
"Nison body/range = 0.7 is the right threshold" — they assert
mechanical dispatch given inputs. The HONEST_SENTINEL caveat
(Marshall-Young-Rose 2006 *JBF* DOI 10.1016/j.jbankfin.2005.08.001
NULL result) is itself pinned as an invariant.

Garman-Klass 1980 *J. Business* DOI 10.1086/296072 formula coefficients
are pinned via numerical verification on a canonical OHLC fixture so
any future formula drift (e.g., Yang-Zhang 2000 swap) fails CI.
"""

from __future__ import annotations

import math
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.daily_candle_classifier import (
    _BODY_RATIO_MOMENTUM,
    _BODY_RATIO_UNCERTAINTY,
    _ENGULFING_BODY_MULTIPLIER,
    _RANGE_GK_COMPRESSION_RATIO,
    _RANGE_MIN_BARS_REQUIRED,
    classify_daily_candle,
    garman_klass_variance,
    is_range_bound,
)

# ───────────────────────── classify_daily_candle dispatch ───────────────────


class TestR168bClassifyDailyCandleMomentum:
    """Body/range >= 0.7 → momentum (sign of body determines bull/bear)."""

    def test_momentum_bull_full_body(self) -> None:
        """Strong bullish candle : open=100, close=110, range body
        ratio = 10/10 = 1.0 → momentum_bull."""
        result = classify_daily_candle(
            prev_ohlc=None,
            curr_ohlc=(100.0, 110.0, 100.0, 110.0),
        )
        assert result.kind == "momentum_bull"
        assert result.body_to_range_ratio == pytest.approx(1.0)
        assert result.honest_sentinel == "low_signal_confidence_candle"

    def test_momentum_bear_full_body(self) -> None:
        """Strong bearish candle : body/range = 1.0, close < open."""
        result = classify_daily_candle(
            prev_ohlc=None,
            curr_ohlc=(110.0, 110.0, 100.0, 100.0),
        )
        assert result.kind == "momentum_bear"
        assert result.body_to_range_ratio == pytest.approx(1.0)

    def test_momentum_bull_at_threshold(self) -> None:
        """Body/range exactly at the 0.7 threshold → still momentum
        (inclusive comparison)."""
        # body = 7, range = 10
        result = classify_daily_candle(
            prev_ohlc=None,
            curr_ohlc=(100.0, 110.0, 100.0, 107.0),
        )
        assert result.body_to_range_ratio == pytest.approx(0.7)
        assert result.kind == "momentum_bull"


class TestR168bClassifyDailyCandleUncertainty:
    """Body/range < 0.3 → uncertainty (doji-like)."""

    def test_uncertainty_small_body(self) -> None:
        """Doji-like : body=1, range=10, ratio=0.1 → uncertainty."""
        result = classify_daily_candle(
            prev_ohlc=None,
            curr_ohlc=(100.0, 110.0, 100.0, 101.0),
        )
        assert result.kind == "uncertainty"
        assert result.body_to_range_ratio == pytest.approx(0.1)

    def test_degenerate_zero_range_yields_uncertainty(self) -> None:
        """High == low (range = 0) — should NOT raise, returns
        uncertainty with explicit degenerate rationale (doctrine #11
        honest-fallback)."""
        result = classify_daily_candle(
            prev_ohlc=None,
            curr_ohlc=(100.0, 100.0, 100.0, 100.0),
        )
        assert result.kind == "uncertainty"
        assert result.body_to_range_ratio == 0.0
        assert "degenerate" in result.rationale.lower()


class TestR168bClassifyDailyCandleEngulfing:
    """Engulfing requires prev_ohlc + body > 1.5x prev body + sign flip."""

    def test_engulfing_bull(self) -> None:
        """Prev bear small body, curr bull body 2x larger → engulfing_bull."""
        prev = (105.0, 106.0, 100.0, 100.0)  # bear, body=5
        curr = (100.0, 115.0, 100.0, 113.0)  # bull, body=13, range=15
        result = classify_daily_candle(prev_ohlc=prev, curr_ohlc=curr)
        # 13 > 5 * 1.5 = 7.5 ; bull ; prev bear → engulfing_bull
        assert result.kind == "engulfing_bull"

    def test_engulfing_bear(self) -> None:
        """Prev bull small body, curr bear body 2x larger → engulfing_bear."""
        prev = (100.0, 106.0, 100.0, 105.0)  # bull, body=5
        curr = (113.0, 115.0, 100.0, 100.0)  # bear, body=13, range=15
        result = classify_daily_candle(prev_ohlc=prev, curr_ohlc=curr)
        assert result.kind == "engulfing_bear"

    def test_engulfing_priority_over_momentum(self) -> None:
        """Engulfing check runs BEFORE momentum — when both conditions
        could match, engulfing wins (priority ladder)."""
        prev = (100.0, 101.0, 100.0, 100.5)  # tiny bull body=0.5
        curr = (110.0, 110.0, 100.0, 100.0)  # full bear, body=10, range=10
        # body_ratio = 1.0 >= 0.7 (could be momentum_bear)
        # AND body 10 > 0.5 * 1.5 = 0.75, prev bull, curr bear → engulfing_bear wins
        result = classify_daily_candle(prev_ohlc=prev, curr_ohlc=curr)
        assert result.kind == "engulfing_bear"

    def test_no_engulfing_without_prev_ohlc(self) -> None:
        """When prev_ohlc=None, engulfing is not detected — falls
        through to momentum/uncertainty/neutral dispatch."""
        result = classify_daily_candle(
            prev_ohlc=None,
            curr_ohlc=(110.0, 110.0, 100.0, 100.0),  # full bear
        )
        assert result.kind == "momentum_bear"  # NOT engulfing_bear

    def test_engulfing_rejected_when_no_sign_flip(self) -> None:
        """Same direction does NOT engulf even if body is 2x larger."""
        prev = (100.0, 102.0, 100.0, 101.0)  # bull, body=1
        curr = (100.0, 110.0, 100.0, 109.0)  # bull, body=9 > 1.5
        result = classify_daily_candle(prev_ohlc=prev, curr_ohlc=curr)
        # bull → bull, no flip → NOT engulfing ; body/range=0.9 → momentum_bull
        assert result.kind == "momentum_bull"


class TestR168bClassifyDailyCandleNeutral:
    """Mid-body (0.3 <= body/range < 0.7) → neutral (default)."""

    def test_neutral_mid_body(self) -> None:
        """body=5, range=10, ratio=0.5 → neutral."""
        result = classify_daily_candle(
            prev_ohlc=None,
            curr_ohlc=(100.0, 110.0, 100.0, 105.0),
        )
        assert result.kind == "neutral"
        assert result.body_to_range_ratio == pytest.approx(0.5)


class TestR168bHonestSentinelInvariant:
    """EVERY classification output carries the HONEST_SENTINEL flag.
    Pattern #15 doctrine #12 anti-recidive : Marshall-Young-Rose 2006
    NULL result NEVER lets the classification surface without the
    caveat."""

    @pytest.mark.parametrize(
        "ohlc,expected_kind",
        [
            ((100.0, 110.0, 100.0, 110.0), "momentum_bull"),
            ((110.0, 110.0, 100.0, 100.0), "momentum_bear"),
            ((100.0, 110.0, 100.0, 101.0), "uncertainty"),
            ((100.0, 110.0, 100.0, 105.0), "neutral"),
            ((100.0, 100.0, 100.0, 100.0), "uncertainty"),  # degenerate
        ],
    )
    def test_honest_sentinel_always_populated(
        self, ohlc: tuple[float, float, float, float], expected_kind: str
    ) -> None:
        result = classify_daily_candle(prev_ohlc=None, curr_ohlc=ohlc)
        assert result.kind == expected_kind
        assert result.honest_sentinel == "low_signal_confidence_candle"


# ───────────────────────── Garman-Klass formula ─────────────────────────────


class TestR168bGarmanKlassFormula:
    """Pin the Garman-Klass 1980 *J. Business* DOI 10.1086/296072
    formula coefficients via numerical verification. Drift on either
    coefficient (0.5 or 2·ln2−1 ≈ 0.38629) fails CI."""

    def test_canonical_formula_numeric_match(self) -> None:
        """Canonical OHLC : O=100, H=110, L=95, C=105.
        ln(H/L) = ln(110/95) ≈ 0.14660
        ln(C/O) = ln(105/100) ≈ 0.04879
        σ² = 0.5 · 0.14660² − 0.38629 · 0.04879²
            ≈ 0.5 · 0.02149 − 0.38629 · 0.00238
            ≈ 0.01075 − 0.00092
            ≈ 0.00983
        """
        result = garman_klass_variance(100.0, 110.0, 95.0, 105.0)
        assert result is not None
        # Compute expected analytically
        expected = 0.5 * math.log(110 / 95) ** 2 - (2 * math.log(2) - 1) * math.log(105 / 100) ** 2
        assert result == pytest.approx(expected, rel=1e-9)

    def test_negative_price_returns_none(self) -> None:
        """Non-positive prices → None (NEVER raises)."""
        assert garman_klass_variance(-1.0, 110.0, 95.0, 105.0) is None
        assert garman_klass_variance(100.0, 110.0, -95.0, 105.0) is None

    def test_zero_price_returns_none(self) -> None:
        """Zero in any field → None."""
        assert garman_klass_variance(0.0, 110.0, 95.0, 105.0) is None
        assert garman_klass_variance(100.0, 110.0, 0.0, 105.0) is None

    def test_high_below_low_returns_none(self) -> None:
        """High < Low → degenerate bar → None."""
        assert garman_klass_variance(100.0, 95.0, 110.0, 105.0) is None

    def test_high_equals_low_yields_zero_first_term(self) -> None:
        """When H == L, the range term is zero — variance is just
        the close-to-open drift term (could be 0 if C==O too)."""
        result = garman_klass_variance(100.0, 100.0, 100.0, 100.0)
        assert result == pytest.approx(0.0, abs=1e-12)


# ───────────────────────── is_range_bound async rule ────────────────────────


def _fake_market_row(open_: float, high: float, low: float, close: float):
    """Build a MagicMock that mimics a MarketDataBar row for testing
    ``is_range_bound`` without DB hit."""
    row = MagicMock()
    row.open = open_
    row.high = high
    row.low = low
    row.close = close
    row.bar_date = date(2026, 5, 26)
    return row


class TestR168bIsRangeBound:
    """Composite range-bound rule : uncertainty candle AND GK variance
    < 80% trailing-30d GK mean. Tests use mocked async session."""

    @pytest.mark.asyncio
    async def test_returns_false_on_insufficient_data(self) -> None:
        """Less than 31 bars in window → (False, None) honest fallback."""
        session = AsyncMock()
        result_proxy = MagicMock()
        result_proxy.scalars.return_value.all.return_value = [
            _fake_market_row(100.0, 110.0, 95.0, 105.0)
        ] * 5  # only 5 bars, need 31
        session.execute = AsyncMock(return_value=result_proxy)

        is_range_flag, reason = await is_range_bound(session, asset="EUR_USD")

        assert is_range_flag is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_returns_false_when_not_uncertainty(self) -> None:
        """31+ bars but latest is momentum (not uncertainty) → False."""
        session = AsyncMock()
        # Latest = strong momentum bull (body/range=1.0)
        bars = [_fake_market_row(100.0, 110.0, 100.0, 110.0)] + [
            _fake_market_row(100.0, 110.0, 95.0, 105.0) for _ in range(31)
        ]
        result_proxy = MagicMock()
        result_proxy.scalars.return_value.all.return_value = bars
        session.execute = AsyncMock(return_value=result_proxy)

        is_range_flag, reason = await is_range_bound(session, asset="EUR_USD")

        assert is_range_flag is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_returns_true_when_uncertainty_and_gk_compressed(self) -> None:
        """Latest uncertainty candle + compressed GK variance → True."""
        session = AsyncMock()
        # Latest = uncertainty candle with TIGHT range (low GK var)
        # body/range = 0.1 (uncertainty) ; very tight range → low GK
        latest = _fake_market_row(100.0, 100.05, 99.95, 100.01)
        # Trailing 30 = wide-range candles → high GK var
        trailing = [_fake_market_row(100.0, 120.0, 80.0, 110.0) for _ in range(31)]
        result_proxy = MagicMock()
        result_proxy.scalars.return_value.all.return_value = [latest, *trailing]
        session.execute = AsyncMock(return_value=result_proxy)

        is_range_flag, reason = await is_range_bound(session, asset="EUR_USD")

        assert is_range_flag is True
        assert reason is not None
        assert "uncertainty" in reason.lower()
        assert "garman-klass" in reason.lower()

    @pytest.mark.asyncio
    async def test_returns_false_when_uncertainty_but_high_vol(self) -> None:
        """Uncertainty candle but wide range (high GK) — single-channel
        signal not sufficient (AND discipline)."""
        session = AsyncMock()
        # Wide-range uncertainty (body small but range huge)
        latest = _fake_market_row(100.0, 120.0, 80.0, 102.0)
        # Trailing similar wide-range → trailing mean similar to current
        trailing = [_fake_market_row(100.0, 120.0, 80.0, 110.0) for _ in range(31)]
        result_proxy = MagicMock()
        result_proxy.scalars.return_value.all.return_value = [latest, *trailing]
        session.execute = AsyncMock(return_value=result_proxy)

        is_range_flag, reason = await is_range_bound(session, asset="EUR_USD")

        # body/range = 2/40 = 0.05 → uncertainty ; but GK NOT compressed
        # below 80% trailing mean → False
        assert is_range_flag is False


# ───────────────────── CI invariant : threshold constants ───────────────────


class TestR168bThresholdConstants:
    """Pin the threshold constants. Drift caught by mechanical assertion."""

    def test_body_ratio_momentum_threshold(self) -> None:
        """0.7 = Nison retail convention (HONEST_SENTINEL applies)."""
        assert _BODY_RATIO_MOMENTUM == 0.7

    def test_body_ratio_uncertainty_threshold(self) -> None:
        assert _BODY_RATIO_UNCERTAINTY == 0.3

    def test_engulfing_body_multiplier(self) -> None:
        assert _ENGULFING_BODY_MULTIPLIER == 1.5

    def test_gk_compression_ratio(self) -> None:
        """0.8 = statistical convention (~1σ below mean)."""
        assert _RANGE_GK_COMPRESSION_RATIO == 0.8

    def test_min_bars_required_matches_trailing_plus_current(self) -> None:
        """Window discipline : 30 trailing + 1 current = 31."""
        assert _RANGE_MIN_BARS_REQUIRED == 31


# ───────────────────── CI invariant : Literal lockstep ──────────────────────


def test_daily_candle_kind_literal_lockstep_with_classifier_dispatch() -> None:
    """Pin the 6 DailyCandleKind Literal values vs the classifier's
    possible return values. Adding a new Literal without a corresponding
    dispatch branch fails this test (W90-style mechanical invariant)."""
    from ichor_api.services.daily_candle_classifier import DailyCandleKind

    declared = set(DailyCandleKind.__args__)  # type: ignore[attr-defined]
    dispatched = {
        "momentum_bull",
        "momentum_bear",
        "uncertainty",
        "engulfing_bull",
        "engulfing_bear",
        "neutral",
    }
    missing = declared - dispatched
    extra = dispatched - declared
    assert not missing, (
        f"DailyCandleKind Literal values not reachable from dispatch: {sorted(missing)}"
    )
    assert not extra, f"Dispatch returns values not in DailyCandleKind Literal: {sorted(extra)}"


def test_tradeability_evaluator_imports_is_range_bound() -> None:
    """Symmetric pin : tradeability_evaluator.py MUST import
    is_range_bound and call it at the Gate 4 wire-point. Drift catches
    a future edit that accidentally reverts to the r167 honest-gap
    ``is_range = False`` placeholder."""
    from ichor_api.services import tradeability_evaluator

    # Module-level import attribute (only present if "from . import" landed)
    assert hasattr(tradeability_evaluator, "is_range_bound"), (
        "tradeability_evaluator.py MUST import is_range_bound from "
        "daily_candle_classifier — r168b wire-point regression."
    )
