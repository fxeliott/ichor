"""Pure tests for correlations + hourly_volatility + brier_feedback.

Focus on the math + branching logic that doesn't require live Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_api.services.brier_feedback import (
    BrierFeedbackReport,
    GroupStat,
    _direction_realized,
    render_brier_feedback_block,
)
from ichor_api.services.correlations import (
    CorrelationMatrix,
    _pearson,
    _ref_corr,
    render_correlations_block,
)
from ichor_api.services.hourly_volatility import (
    HourlyVolEntry,
    HourlyVolReport,
    _percentile,
    render_hourly_volatility_block,
)

# ─────────────────────── correlations ──────────────────────────


def test_pearson_correlated_returns_high_value() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0] * 6  # n=30
    ys = [2.0, 4.0, 6.0, 8.0, 10.0] * 6
    c = _pearson(xs, ys)
    assert c is not None
    assert c == pytest.approx(1.0, abs=1e-6)


def test_pearson_anticorrelated_returns_negative() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0] * 6
    ys = [10.0, 8.0, 6.0, 4.0, 2.0] * 6
    c = _pearson(xs, ys)
    assert c is not None
    assert c == pytest.approx(-1.0, abs=1e-6)


def test_pearson_returns_none_with_too_few_samples() -> None:
    xs = [1.0, 2.0, 3.0]
    ys = [1.0, 2.0, 3.0]
    assert _pearson(xs, ys) is None


def test_pearson_returns_none_on_zero_variance() -> None:
    xs = [5.0] * 50
    ys = [1.0, 2.0, 3.0] * 17  # 51 elements
    ys = ys[:50]
    assert _pearson(xs, ys) is None


def test_ref_corr_lookup_works_both_orders() -> None:
    assert _ref_corr("EUR_USD", "GBP_USD") == pytest.approx(0.65)
    # Reverse order
    assert _ref_corr("GBP_USD", "EUR_USD") == pytest.approx(0.65)


def test_ref_corr_returns_none_for_unknown_pair() -> None:
    assert _ref_corr("EUR_USD", "EUR_USD") is None


def test_render_correlations_block_insufficient_data() -> None:
    m = CorrelationMatrix(
        window_days=30,
        assets=["EUR_USD", "USD_JPY"],
        matrix=[[1.0, None], [None, 1.0]],
        n_returns_used=5,
        generated_at=datetime.now(UTC),
        flags=[],
    )
    md, sources = render_correlations_block(m)
    assert "insufficient" in md.lower()
    assert sources == []


def test_render_correlations_block_with_flags() -> None:
    m = CorrelationMatrix(
        window_days=30,
        assets=["EUR_USD", "GBP_USD", "USD_JPY"],
        matrix=[
            [1.0, 0.30, -0.20],
            [0.30, 1.0, -0.15],
            [-0.20, -0.15, 1.0],
        ],
        n_returns_used=120,
        generated_at=datetime.now(UTC),
        flags=["EUR_USD/GBP_USD unusually looser : +0.30 vs ref +0.65 (-0.35)"],
    )
    md, sources = render_correlations_block(m)
    assert "EUR_USD" in md
    assert "GBP_USD" in md
    assert "0.30" in md
    assert "régime" in md.lower() or "shifts" in md.lower()
    assert "looser" in md
    assert sources == ["polygon_intraday:correlation_matrix:30d"]


# ─────────────────────── hourly_volatility ──────────────────────


def test_percentile_basic() -> None:
    xs = sorted([1.0, 2.0, 3.0, 4.0, 5.0])
    assert _percentile(xs, 50.0) == pytest.approx(3.0)
    assert _percentile(xs, 0.0) == pytest.approx(1.0)
    assert _percentile(xs, 100.0) == pytest.approx(5.0)


def test_percentile_interpolates() -> None:
    xs = sorted([1.0, 2.0, 3.0, 4.0])
    # 50th percentile of 4 elements is between idx 1 and 2 → mid of 2 and 3 = 2.5
    assert _percentile(xs, 50.0) == pytest.approx(2.5, abs=1e-6)


def test_percentile_empty() -> None:
    assert _percentile([], 50.0) == 0.0


def test_render_hourly_volatility_no_data() -> None:
    entries = [
        HourlyVolEntry(hour_utc=h, median_bp=0.0, p75_bp=0.0, n_samples=0) for h in range(24)
    ]
    r = HourlyVolReport(
        asset="EUR_USD",
        window_days=30,
        entries=entries,
        best_hour_utc=None,
        worst_hour_utc=None,
        london_session_avg_bp=None,
        asian_session_avg_bp=None,
        generated_at=datetime.now(UTC),
    )
    md, sources = render_hourly_volatility_block(r)
    assert "insufficient" in md.lower()
    assert sources == []


def test_render_hourly_volatility_full_payload() -> None:
    entries = []
    for h in range(24):
        # Simulate higher vol around London/NY hours (8-15 UTC)
        if 8 <= h <= 15:
            med, p75 = 6.0, 9.0
        elif 0 <= h <= 6:
            med, p75 = 1.5, 2.5
        else:
            med, p75 = 3.0, 5.0
        entries.append(HourlyVolEntry(hour_utc=h, median_bp=med, p75_bp=p75, n_samples=120))
    r = HourlyVolReport(
        asset="EUR_USD",
        window_days=30,
        entries=entries,
        best_hour_utc=12,
        worst_hour_utc=3,
        london_session_avg_bp=6.0,
        asian_session_avg_bp=1.5,
        generated_at=datetime.now(UTC),
    )
    md, sources = render_hourly_volatility_block(r)
    assert "EUR_USD" in md
    assert "Best hour" in md
    assert "12:00" in md
    assert "London" in md
    assert sources == ["polygon_intraday:EUR_USD@hourly_vol_30d"]


# ─────────────────────── brier_feedback ──────────────────────


def test_direction_realized_long_correct() -> None:
    assert _direction_realized("long", 1.0750, 1.0700) is True


def test_direction_realized_long_wrong() -> None:
    assert _direction_realized("long", 1.0680, 1.0700) is False


def test_direction_realized_short_correct() -> None:
    assert _direction_realized("short", 1.0680, 1.0700) is True


def test_direction_realized_neutral_returns_none() -> None:
    assert _direction_realized("neutral", 1.0750, 1.0700) is None


def test_direction_realized_handles_missing_inputs() -> None:
    assert _direction_realized(None, 1.0, 1.0) is None
    assert _direction_realized("long", None, 1.0) is None
    assert _direction_realized("long", 1.0, None) is None


def test_render_brier_feedback_no_data() -> None:
    r = BrierFeedbackReport(
        n_cards_reconciled=0,
        window_days=30,
        overall_avg_brier=None,
        by_asset=[],
        by_session_type=[],
        by_regime=[],
        high_conviction_win_rate=None,
        low_conviction_win_rate=None,
        flags=[],
    )
    md, sources = render_brier_feedback_block(r)
    assert "Aucune carte" in md
    assert sources == []


def test_render_brier_feedback_with_data() -> None:
    r = BrierFeedbackReport(
        n_cards_reconciled=24,
        window_days=30,
        overall_avg_brier=0.182,
        by_asset=[
            GroupStat(key="EUR_USD", n=4, avg_brier=0.150, win_rate=0.80),
            GroupStat(key="USD_JPY", n=3, avg_brier=0.190, win_rate=0.70),
        ],
        by_session_type=[
            GroupStat(key="pre_londres", n=12, avg_brier=0.170, win_rate=0.75),
        ],
        by_regime=[
            GroupStat(key="goldilocks", n=10, avg_brier=0.160, win_rate=0.80),
        ],
        high_conviction_win_rate=0.85,
        low_conviction_win_rate=0.40,
        flags=["Best asset : EUR_USD (Brier 0.150, n=4)"],
    )
    md, sources = render_brier_feedback_block(r)
    assert "0.1820" in md or "0.182" in md
    assert "EUR_USD" in md
    assert "pre_londres" in md
    assert "goldilocks" in md
    assert "Best asset" in md
    assert sources == ["empirical_model:brier_feedback"]
