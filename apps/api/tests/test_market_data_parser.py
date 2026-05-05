"""Pure-parsing tests for the market data Stooq adapter.

No HTTP — fixtures are realistic CSV bodies. The yfinance fallback path is
not unit-tested (heavy + network); rely on the live `cli.run_collectors
market_data` smoke run for that.
"""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.market_data import (
    STOOQ_SYMBOLS,
    YFINANCE_SYMBOLS,
    MarketDataPoint,
    parse_stooq_csv,
)

VALID_CSV = b"""Date,Open,High,Low,Close,Volume
2026-04-30,1.0850,1.0875,1.0840,1.0863,123456
2026-05-01,1.0863,1.0890,1.0855,1.0871,98765
2026-05-02,1.0871,1.0900,1.0860,1.0888,87654
"""


CSV_WITHOUT_VOLUME = b"""Date,Open,High,Low,Close
2026-04-30,1.0850,1.0875,1.0840,1.0863
2026-05-01,1.0863,1.0890,1.0855,1.0871
"""


CSV_NO_DATA = b"No data\n"


CSV_BAD_HEADER = b"unexpected,columns\nfoo,bar\n"


def test_parse_returns_three_bars() -> None:
    rows = parse_stooq_csv("EUR_USD", VALID_CSV)
    assert len(rows) == 3
    assert all(isinstance(r, MarketDataPoint) for r in rows)
    assert rows[0].asset == "EUR_USD"


def test_parse_dates_chronological() -> None:
    rows = parse_stooq_csv("EUR_USD", VALID_CSV)
    assert rows[0].bar_date == date(2026, 4, 30)
    assert rows[1].bar_date == date(2026, 5, 1)
    assert rows[2].bar_date == date(2026, 5, 2)


def test_parse_ohlc_floats() -> None:
    rows = parse_stooq_csv("EUR_USD", VALID_CSV)
    r = rows[0]
    assert r.open == 1.0850
    assert r.high == 1.0875
    assert r.low == 1.0840
    assert r.close == 1.0863
    assert r.volume == 123456.0


def test_parse_volume_optional() -> None:
    rows = parse_stooq_csv("EUR_USD", CSV_WITHOUT_VOLUME)
    assert len(rows) == 2
    assert all(r.volume is None for r in rows)


def test_parse_no_data_returns_empty() -> None:
    assert parse_stooq_csv("BAD", CSV_NO_DATA) == []


def test_parse_bad_header_returns_empty() -> None:
    assert parse_stooq_csv("EUR_USD", CSV_BAD_HEADER) == []


def test_parse_handles_blank_body() -> None:
    assert parse_stooq_csv("EUR_USD", b"") == []
    assert parse_stooq_csv("EUR_USD", b"\n\n") == []


def test_source_is_stooq() -> None:
    rows = parse_stooq_csv("EUR_USD", VALID_CSV)
    assert all(r.source == "stooq" for r in rows)


def test_fetched_at_is_set() -> None:
    rows = parse_stooq_csv("EUR_USD", VALID_CSV)
    assert all(r.fetched_at is not None for r in rows)


def test_stooq_symbols_cover_phase0_assets() -> None:
    """The 8 Phase 0 assets must all have Stooq mappings."""
    expected = {
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    }
    assert expected == set(STOOQ_SYMBOLS.keys())
    assert expected == set(YFINANCE_SYMBOLS.keys())


def test_skips_malformed_row_keeps_others() -> None:
    body = b"""Date,Open,High,Low,Close,Volume
2026-05-01,1.08,1.09,1.07,1.085,1000
2026-05-02,oops,1.09,1.07,1.085,1000
2026-05-03,1.08,1.09,1.07,1.085,1000
"""
    rows = parse_stooq_csv("EUR_USD", body)
    # Two valid rows, one skipped
    assert len(rows) == 2
    assert {r.bar_date for r in rows} == {date(2026, 5, 1), date(2026, 5, 3)}
