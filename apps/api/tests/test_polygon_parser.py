"""Pure-parsing tests for the Polygon Starter collector."""

from __future__ import annotations

import pytest

from ichor_api.collectors.polygon import (
    ASSET_TO_TICKER,
    parse_aggs_response,
    supported_assets,
)


def _ok_body(*results: dict) -> dict:
    return {"status": "OK", "ticker": "C:EURUSD", "results": list(results)}


def test_supported_assets_covers_all_phase1() -> None:
    assets = set(supported_assets())
    expected = {
        "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD",
        "XAU_USD", "NAS100_USD", "SPX500_USD",
    }
    assert assets == expected


def test_asset_to_ticker_uses_correct_namespaces() -> None:
    assert ASSET_TO_TICKER["EUR_USD"].startswith("C:")  # forex
    assert ASSET_TO_TICKER["XAU_USD"].startswith("X:")   # metal
    assert ASSET_TO_TICKER["NAS100_USD"].startswith("I:")  # index


def test_parse_aggs_returns_one_bar_per_result() -> None:
    body = _ok_body(
        {
            "t": 1_762_550_400_000,  # 2025-11-08 00:00:00 UTC (epoch ms)
            "o": 1.0723,
            "h": 1.0741,
            "l": 1.0719,
            "c": 1.0735,
            "v": 1234,
            "vw": 1.0728,
            "n": 42,
        }
    )
    bars = parse_aggs_response("EUR_USD", "C:EURUSD", body)
    assert len(bars) == 1
    bar = bars[0]
    assert bar.asset == "EUR_USD"
    assert bar.ticker == "C:EURUSD"
    assert bar.open == 1.0723
    assert bar.close == 1.0735
    assert bar.volume == 1234
    assert bar.vwap == 1.0728
    assert bar.transactions == 42
    assert bar.bar_ts.year == 2025


def test_parse_aggs_normalizes_ohlc_envelope() -> None:
    """When low > min(open, close) by epsilon, the parser snaps to the
    actual envelope so the DB CHECK constraint never trips."""
    body = _ok_body(
        {
            "t": 1_762_550_400_000,
            "o": 1.0723,
            "h": 1.0735,  # high < close ! intentional bad input
            "l": 1.0730,  # low > open ! intentional bad input
            "c": 1.0740,
            "v": 100,
        }
    )
    bars = parse_aggs_response("EUR_USD", "C:EURUSD", body)
    assert len(bars) == 1
    bar = bars[0]
    assert bar.high == max(1.0723, 1.0735, 1.0730, 1.0740)
    assert bar.low == min(1.0723, 1.0735, 1.0730, 1.0740)


def test_parse_aggs_skips_rows_missing_ohlc() -> None:
    body = _ok_body(
        {"t": 1_762_550_400_000, "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.05},  # ok
        {"t": 1_762_550_460_000, "o": 1.0, "h": 1.1},  # missing l, c → drop
        {"o": 1.0, "h": 1.1, "l": 0.9, "c": 1.05},      # missing t → drop
    )
    bars = parse_aggs_response("EUR_USD", "C:EURUSD", body)
    assert len(bars) == 1


def test_parse_aggs_handles_empty_results() -> None:
    assert parse_aggs_response("EUR_USD", "C:EURUSD", {"results": []}) == []
    assert parse_aggs_response("EUR_USD", "C:EURUSD", {}) == []


def test_parse_aggs_optional_fields_default_to_none() -> None:
    body = _ok_body(
        {"t": 1_762_550_400_000, "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.05}
    )
    bar = parse_aggs_response("EUR_USD", "C:EURUSD", body)[0]
    assert bar.volume is None
    assert bar.vwap is None
    assert bar.transactions is None


def test_fetch_aggs_rejects_unknown_asset() -> None:
    """`fetch_aggs` should fail fast on an unknown asset before any HTTP call."""
    import asyncio

    from ichor_api.collectors.polygon import fetch_aggs

    from datetime import date

    async def _go() -> None:
        with pytest.raises(ValueError):
            await fetch_aggs(
                "UNKNOWN_ASSET",
                api_key="k",
                from_date=date(2025, 11, 1),
                to_date=date(2025, 11, 8),
            )

    asyncio.run(_go())
