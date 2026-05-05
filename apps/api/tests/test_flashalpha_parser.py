"""Pure-parsing tests for the FlashAlpha GEX collector."""

from __future__ import annotations

from datetime import UTC, datetime

from ichor_api.collectors.flashalpha import (
    GexSnapshot,
    parse_gex_response,
    supported_tickers,
)


def test_supported_tickers_returns_single_name_set() -> None:
    """Free-tier WATCHED_TICKERS — index/ETF tickers (SPX/NDX/SPY/QQQ)
    require Basic+ on FlashAlpha as of 2026-05-05, so the watch list
    falls back to single-name large-caps (AAPL/MSFT). The actual GEX
    market signal is computed via collectors.gex_yfinance instead.
    """
    tickers = supported_tickers()
    assert len(tickers) >= 1
    # Single names only on free tier
    for t in tickers:
        assert t not in ("SPX", "NDX", "SPY", "QQQ")


def test_parse_canonical_response() -> None:
    body = {
        "ticker": "SPX",
        "as_of": "2026-05-04T20:00:00Z",
        "spot": 5187.0,
        "total_gex_usd": 1_350_000_000,
        "gamma_flip": 5160.0,
        "call_wall": 5250.0,
        "put_wall": 5100.0,
        "zero_gamma": 5180.0,
    }
    snap = parse_gex_response("SPX", body)
    assert isinstance(snap, GexSnapshot)
    assert snap.ticker == "SPX"
    assert snap.spot == 5187.0
    assert snap.total_gex_usd == 1.35e9
    assert snap.gamma_flip == 5160.0
    assert snap.call_wall == 5250.0
    assert snap.put_wall == 5100.0
    assert snap.zero_gamma == 5180.0
    assert snap.as_of == datetime(2026, 5, 4, 20, 0, 0, tzinfo=UTC)


def test_parse_tolerates_camelcase_keys() -> None:
    body = {
        "ticker": "NDX",
        "timestamp": "2026-05-04T20:00:00Z",
        "underlying": 18_400.0,
        "totalGEX": -2_400_000_000,
        "gammaFlip": 18_300.0,
        "callWall": 18_700.0,
        "putWall": 18_100.0,
        "zeroGamma": 18_310.0,
    }
    snap = parse_gex_response("NDX", body)
    assert snap is not None
    assert snap.spot == 18_400.0
    assert snap.total_gex_usd == -2.4e9
    assert snap.gamma_flip == 18_300.0
    assert snap.call_wall == 18_700.0


def test_parse_returns_none_on_non_dict() -> None:
    assert parse_gex_response("SPX", "garbage") is None  # type: ignore[arg-type]
    assert parse_gex_response("SPX", []) is None  # type: ignore[arg-type]


def test_parse_handles_missing_optional_fields() -> None:
    body = {"ticker": "SPX", "spot": 5180.0}
    snap = parse_gex_response("SPX", body)
    assert snap is not None
    assert snap.spot == 5180.0
    assert snap.total_gex_usd is None
    assert snap.gamma_flip is None


def test_parse_safe_float_on_garbage_values() -> None:
    body = {"ticker": "SPX", "spot": "not-a-number", "total_gex_usd": None}
    snap = parse_gex_response("SPX", body)
    assert snap is not None
    assert snap.spot is None
    assert snap.total_gex_usd is None


def test_parse_falls_back_to_now_on_bad_iso() -> None:
    body = {"ticker": "SPX", "as_of": "not-a-date"}
    snap = parse_gex_response("SPX", body)
    assert snap is not None
    # as_of becomes "now" — sanity check it's recent (within 5 minutes)
    delta = abs((datetime.now(UTC) - snap.as_of).total_seconds())
    assert delta < 300
