"""Pure-parsing tests for CFTC COT collector."""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.cot import (
    MARKET_CODE_TO_ASSET,
    _parse_disagg_csv,
    _parse_int,
)


def test_parse_int_handles_commas() -> None:
    assert _parse_int("1,234,567") == 1234567


def test_parse_int_handles_empty_dot() -> None:
    assert _parse_int("") == 0
    assert _parse_int(".") == 0
    assert _parse_int("-") == 0
    assert _parse_int(None) == 0


def test_parse_int_handles_float_string() -> None:
    assert _parse_int("123.0") == 123


def test_parse_int_handles_garbage() -> None:
    assert _parse_int("not-a-number") == 0


def test_parse_disagg_csv_extracts_basic_fields() -> None:
    body = b"""\"Market and Exchange Names\",\"CFTC Contract Market Code\",\"Report Date as YYYY-MM-DD\",\"Money Manager Longs\",\"Money Manager Shorts\",\"Producer/Merchant/Processor/User Longs\",\"Producer/Merchant/Processor/User Shorts\",\"Swap Dealer Longs\",\"Swap Dealer Shorts\",\"Other Reportable Longs\",\"Other Reportable Shorts\",\"Nonreportable Positions-Long (All)\",\"Nonreportable Positions-Short (All)\",\"Open Interest (All)\"
\"EURO FX - CHICAGO MERCANTILE EXCHANGE\",\"099741\",\"2026-04-29\",\"180000\",\"45000\",\"30000\",\"20000\",\"5000\",\"15000\",\"10000\",\"8000\",\"50000\",\"60000\",\"600000\"
\"GOLD - COMMODITY EXCHANGE INC.\",\"088691\",\"2026-04-29\",\"100000\",\"30000\",\"20000\",\"15000\",\"50000\",\"40000\",\"15000\",\"10000\",\"40000\",\"35000\",\"500000\"
"""
    rows = _parse_disagg_csv(body)
    assert len(rows) == 2

    eur = next(r for r in rows if r.market_code == "099741")
    # MM net = 180000 - 45000 = 135000
    assert eur.managed_money_net == 135_000
    # Producer net = 30000 - 20000 = 10000
    assert eur.producer_net == 10_000
    assert eur.open_interest == 600_000
    assert eur.report_date == date(2026, 4, 29)
    assert eur.market_name.startswith("EURO FX")

    gold = next(r for r in rows if r.market_code == "088691")
    assert gold.managed_money_net == 70_000
    assert gold.swap_dealer_net == 10_000


def test_parse_disagg_csv_skips_invalid_rows() -> None:
    body = b"""\"Market and Exchange Names\",\"CFTC Contract Market Code\",\"Report Date as YYYY-MM-DD\",\"Money Manager Longs\",\"Money Manager Shorts\",\"Producer/Merchant/Processor/User Longs\",\"Producer/Merchant/Processor/User Shorts\",\"Swap Dealer Longs\",\"Swap Dealer Shorts\",\"Other Reportable Longs\",\"Other Reportable Shorts\",\"Nonreportable Positions-Long (All)\",\"Nonreportable Positions-Short (All)\",\"Open Interest (All)\"
\"BAD\",\"\",\"2026-04-29\",\"100\",\"50\",\"0\",\"0\",\"0\",\"0\",\"0\",\"0\",\"0\",\"0\",\"100\"
\"\",\"099741\",\"\",\"100\",\"50\",\"0\",\"0\",\"0\",\"0\",\"0\",\"0\",\"0\",\"0\",\"100\"
\"GOLD - COMMODITY EXCHANGE INC.\",\"088691\",\"2026-04-29\",\"100\",\"50\",\"0\",\"0\",\"0\",\"0\",\"0\",\"0\",\"0\",\"0\",\"100\"
"""
    rows = _parse_disagg_csv(body)
    # Only the gold row is valid (first lacks code, second lacks date)
    assert len(rows) == 1
    assert rows[0].market_code == "088691"


def test_parse_disagg_csv_empty_body() -> None:
    assert _parse_disagg_csv(b"") == []


def test_market_code_mapping_covers_phase1_assets() -> None:
    """All 8 Phase 1 assets must have a CFTC market code mapping."""
    expected = {
        "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD",
        "XAU_USD", "US30", "US100",
    }
    mapped_assets = set(MARKET_CODE_TO_ASSET.values())
    assert expected == mapped_assets, f"Missing assets: {expected - mapped_assets}"
