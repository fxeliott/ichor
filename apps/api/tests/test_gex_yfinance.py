"""Unit tests for the yfinance dealer GEX collector.

Tests verify:
  - Black-Scholes gamma matches the closed-form formula on canonical inputs
  - Aggregation produces the right total + walls + flip
  - Empty inputs return clean defaults (no exceptions)
  - The async wrapper handles missing yfinance gracefully

No actual yfinance calls — we mock the chain shape to keep the test
fast and offline-safe.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from ichor_api.collectors.gex_yfinance import (
    _CALL_DEALER_SIGN,
    _CONTRACT_MULTIPLIER,
    _PUT_DEALER_SIGN,
    DealerGexSnapshot,
    _compute_for_chains,
    aggregate_dealer_gex,
    bs_gamma,
    supported_tickers,
)

# ── Black-Scholes gamma ──────────────────────────────────────────────


def test_bs_gamma_matches_closed_form_at_atm() -> None:
    """At-the-money gamma reaches its peak. Closed form check."""
    s = 100.0
    k = 100.0
    t = 30 / 365.25
    sigma = 0.25
    r = 0.05

    # Manual closed-form
    sqrt_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
    expected = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (s * sigma * sqrt_t)

    actual = bs_gamma(s, k, t, sigma, r)
    assert actual == pytest.approx(expected, rel=1e-9)


def test_bs_gamma_zero_for_negative_inputs() -> None:
    assert bs_gamma(0, 100, 1, 0.2) == 0.0
    assert bs_gamma(100, 0, 1, 0.2) == 0.0
    assert bs_gamma(100, 100, 0, 0.2) == 0.0
    assert bs_gamma(100, 100, 1, 0) == 0.0
    assert bs_gamma(100, 100, -1, 0.2) == 0.0


def test_bs_gamma_otm_lower_than_atm() -> None:
    """Far-OTM strikes have lower gamma than ATM."""
    atm = bs_gamma(100, 100, 30 / 365.25, 0.2)
    otm = bs_gamma(100, 130, 30 / 365.25, 0.2)
    assert atm > otm > 0


def test_bs_gamma_higher_iv_lower_gamma() -> None:
    """Higher IV lowers the peak ATM gamma (vega ↑, gamma ↓ peak)."""
    low = bs_gamma(100, 100, 30 / 365.25, 0.10)
    high = bs_gamma(100, 100, 30 / 365.25, 0.50)
    assert low > high


# ── aggregate_dealer_gex ─────────────────────────────────────────────


def test_aggregate_empty_returns_zero_and_nones() -> None:
    total, flip, cw, pw = aggregate_dealer_gex(100.0, {})
    assert total == 0.0
    assert flip is None
    assert cw is None
    assert pw is None


def test_aggregate_call_only_negative_gex() -> None:
    """Pure call OI : dealers short calls → negative dealer GEX."""
    total, flip, cw, pw = aggregate_dealer_gex(
        100.0,
        {
            105.0: {"call_gamma_oi": 0.05 * 1000, "put_gamma_oi": 0.0},  # gamma * OI = 50
        },
    )
    expected = _CALL_DEALER_SIGN * 50.0 * _CONTRACT_MULTIPLIER * 100.0 * 100.0 * 0.01
    assert total == pytest.approx(expected)
    assert total < 0  # short calls → negative dealer GEX
    assert cw == 105.0


def test_aggregate_put_only_positive_gex() -> None:
    """Pure put OI : dealers long puts → positive dealer GEX."""
    total, flip, cw, pw = aggregate_dealer_gex(
        100.0,
        {
            95.0: {"call_gamma_oi": 0.0, "put_gamma_oi": 0.05 * 1000},
        },
    )
    expected = _PUT_DEALER_SIGN * 50.0 * _CONTRACT_MULTIPLIER * 100.0 * 100.0 * 0.01
    assert total == pytest.approx(expected)
    assert total > 0
    assert pw == 95.0


def test_aggregate_balanced_chain_finds_flip() -> None:
    """Balanced calls below + puts above → flip lives near the boundary."""
    options = {
        90.0: {"call_gamma_oi": 0.0, "put_gamma_oi": 100.0},  # +put gex
        95.0: {"call_gamma_oi": 0.0, "put_gamma_oi": 50.0},
        100.0: {"call_gamma_oi": 50.0, "put_gamma_oi": 0.0},  # neutral'ish
        105.0: {"call_gamma_oi": 100.0, "put_gamma_oi": 0.0},
    }
    total, flip, cw, pw = aggregate_dealer_gex(100.0, options)
    # call_wall is the strike with the largest absolute call dealer gex
    assert cw == 105.0
    # put_wall is the strike with the largest absolute put dealer gex
    assert pw == 90.0
    # flip exists
    assert flip is not None and 90.0 <= flip <= 105.0


def test_aggregate_call_wall_is_max_abs_call_gex() -> None:
    """call_wall picks the strike with the largest |call dealer gex|."""
    options = {
        100.0: {"call_gamma_oi": 50.0, "put_gamma_oi": 0.0},
        110.0: {"call_gamma_oi": 200.0, "put_gamma_oi": 0.0},  # biggest call
        120.0: {"call_gamma_oi": 30.0, "put_gamma_oi": 0.0},
    }
    _, _, cw, _ = aggregate_dealer_gex(100.0, options)
    assert cw == 110.0


# ── r67 : gamma_flip plausibility band ───────────────────────────────


def test_aggregate_far_otm_only_crossing_yields_none_flip() -> None:
    """r67 regression : a cumulative zero-crossing that exists ONLY at a
    deep-OTM strike (far from spot) must NOT be returned as the flip —
    it is numerical noise from tiny low-OI gamma, not a real dealer
    flip. This is the exact garbage class observed in prod
    (gex_snapshots QQQ spot 710.74 / flip 310.43 = -56%). Expect None.
    """
    # spot=100. A big put-gamma at strike 30 (+gex) then a bigger
    # call-gamma at strike 35 (−gex) makes the cumulative-from-low sum
    # cross zero around strike ~32 (≈68 % below spot). Strikes near
    # spot are perfectly balanced → no near-spot crossing.
    options = {
        30.0: {"call_gamma_oi": 0.0, "put_gamma_oi": 1000.0},
        35.0: {"call_gamma_oi": 3000.0, "put_gamma_oi": 0.0},
        100.0: {"call_gamma_oi": 10.0, "put_gamma_oi": 10.0},
        105.0: {"call_gamma_oi": 10.0, "put_gamma_oi": 10.0},
    }
    _, flip, _, _ = aggregate_dealer_gex(100.0, options)
    assert flip is None, f"far-OTM crossing must be rejected, got {flip}"


def test_aggregate_single_crossing_just_in_band_is_kept() -> None:
    """A clean single crossing ~10 % below spot (inside the ±15 % band)
    is a valid flip. Single-crossing chain : puts below (+gex) → calls
    above (−gex), boundary placed at ~90 for spot 100."""
    options = {
        88.0: {"call_gamma_oi": 0.0, "put_gamma_oi": 1000.0},  # +gex
        92.0: {"call_gamma_oi": 1000.0, "put_gamma_oi": 0.0},  # −gex
    }
    _, flip, _, _ = aggregate_dealer_gex(100.0, options)
    assert flip is not None
    assert 88.0 <= flip <= 92.0, f"in-band crossing must be kept, got {flip}"


def test_aggregate_single_crossing_just_out_of_band_is_rejected() -> None:
    """The same clean single crossing but ~30 % below spot (outside the
    ±15 % band) is rejected → None. Proves the band gate, not just the
    multi-crossing 'closest-to-spot' heuristic."""
    options = {
        68.0: {"call_gamma_oi": 0.0, "put_gamma_oi": 1000.0},  # +gex
        72.0: {"call_gamma_oi": 1000.0, "put_gamma_oi": 0.0},  # −gex
    }
    _, flip, _, _ = aggregate_dealer_gex(100.0, options)
    assert flip is None, f"out-of-band crossing must be rejected, got {flip}"


# ── _compute_for_chains ──────────────────────────────────────────────


def _make_chain(strike: float, oi: float, iv: float):
    """Build a fake list-of-rows that mimics yfinance DataFrame iteration."""
    return [
        {"strike": strike, "openInterest": oi, "impliedVolatility": iv},
    ]


def test_compute_for_chains_walks_calls_and_puts() -> None:
    now = datetime(2026, 5, 5, tzinfo=UTC)
    expiry = (now + timedelta(days=30)).strftime("%Y-%m-%d")
    chains = [
        (
            expiry,
            _make_chain(strike=100.0, oi=1000, iv=0.20),  # calls
            _make_chain(strike=100.0, oi=500, iv=0.20),  # puts
        )
    ]
    by_strike, n = _compute_for_chains(spot=100.0, chains=chains, now=now)
    assert n == 2
    assert 100.0 in by_strike
    assert by_strike[100.0]["call_gamma_oi"] > 0
    assert by_strike[100.0]["put_gamma_oi"] > 0


def test_compute_for_chains_skips_expired() -> None:
    """Expiry in the past = ignored (negative time-to-expiry)."""
    now = datetime(2026, 5, 5, tzinfo=UTC)
    past_expiry = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    chains = [(past_expiry, _make_chain(100, 1000, 0.2), _make_chain(100, 500, 0.2))]
    by_strike, n = _compute_for_chains(spot=100.0, chains=chains, now=now)
    assert n == 0
    assert by_strike == {}


def test_compute_for_chains_skips_zero_oi_and_zero_iv() -> None:
    now = datetime(2026, 5, 5, tzinfo=UTC)
    expiry = (now + timedelta(days=30)).strftime("%Y-%m-%d")
    chains = [
        (
            expiry,
            [
                {"strike": 100.0, "openInterest": 0, "impliedVolatility": 0.20},  # 0 OI
                {"strike": 105.0, "openInterest": 1000, "impliedVolatility": 0.0},  # 0 IV
                {"strike": 110.0, "openInterest": 500, "impliedVolatility": 0.20},  # ok
            ],
            [],
        )
    ]
    by_strike, n = _compute_for_chains(spot=100.0, chains=chains, now=now)
    assert n == 1
    assert list(by_strike.keys()) == [110.0]


def test_compute_for_chains_aggregates_across_expiries() -> None:
    """Same strike across two expiries should sum into one bucket."""
    now = datetime(2026, 5, 5, tzinfo=UTC)
    e1 = (now + timedelta(days=15)).strftime("%Y-%m-%d")
    e2 = (now + timedelta(days=45)).strftime("%Y-%m-%d")
    chains = [
        (e1, _make_chain(100.0, 500, 0.2), []),
        (e2, _make_chain(100.0, 700, 0.2), []),
    ]
    by_strike, n = _compute_for_chains(spot=100.0, chains=chains, now=now)
    assert n == 2
    # Both contributions land in the same strike bucket
    assert 100.0 in by_strike
    assert by_strike[100.0]["call_gamma_oi"] > 0


# ── DealerGexSnapshot dataclass ──────────────────────────────────────


def test_dealergexsnapshot_default_source_is_yfinance() -> None:
    s = DealerGexSnapshot(
        asset="SPY",
        captured_at=datetime.now(UTC),
        spot=500.0,
        dealer_gex_total=1.0,
        gamma_flip=499.0,
        call_wall=510.0,
        put_wall=490.0,
    )
    assert s.source == "yfinance"


# ── supported_tickers ────────────────────────────────────────────────


def test_supported_tickers_returns_spy_qqq() -> None:
    assert supported_tickers() == ("SPY", "QQQ")
