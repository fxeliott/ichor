"""Pure-parsing tests for cftc_tff collector.

No network. Sample Socrata response fixed at module top, parser
exercised in isolation.
"""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.cftc_tff import (
    CFTC_TFF_SODA_URL,
    MARKET_TO_ASSET,
    TRACKED_MARKET_CODES,
    CftcTffObservation,
    _to_int,
    parse_socrata_response,
)


# Verified live 2026-05-08 — trimmed real Socrata response for EUR_FX.
_FIXTURE_OK: list[dict] = [
    {
        # NOTE: Dealer + Nonrept + TotRept use "_all" suffix;
        # AssetMgr + LevMoney + OtherRept do NOT. CFTC schema legacy.
        "id": "row1",
        "report_date_as_yyyy_mm_dd": "2026-04-28T00:00:00.000",
        "cftc_contract_market_code": "099741",
        "market_and_exchange_names": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
        "commodity_name": "CURRENCY",
        "commodity_subgroup_name": "CURRENCY",
        "open_interest_all": "750000",
        "dealer_positions_long_all": "120000",
        "dealer_positions_short_all": "180000",
        "asset_mgr_positions_long": "200000",
        "asset_mgr_positions_short": "50000",
        "lev_money_positions_long": "150000",
        "lev_money_positions_short": "220000",
        "other_rept_positions_long": "80000",
        "other_rept_positions_short": "40000",
        "nonrept_positions_long_all": "30000",
        "nonrept_positions_short_all": "90000",
    },
    {
        "id": "row2",
        "report_date_as_yyyy_mm_dd": "2026-04-21T00:00:00.000",
        "cftc_contract_market_code": "088691",
        "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
        "commodity_name": "PRECIOUS METALS",
        "open_interest_all": "550,000",  # Yes, with commas — Socrata sometimes does this
        "dealer_positions_long_all": "10000",
        "dealer_positions_short_all": "85000",
        "asset_mgr_positions_long": "220000",
        "asset_mgr_positions_short": "5000",
        "lev_money_positions_long": "65000",
        "lev_money_positions_short": "95000",
        "other_rept_positions_long": "25000",
        "other_rept_positions_short": "20000",
        "nonrept_positions_long_all": "15000",
        "nonrept_positions_short_all": "25000",
    },
]


_FIXTURE_MISSING_DATE: list[dict] = [
    {"id": "row1", "open_interest_all": "100000"},  # no report_date_as_yyyy_mm_dd
]


def test_to_int_handles_socrata_string_quirks() -> None:
    """Socrata returns numerics as strings, sometimes with commas, sometimes
    empty / dot for missing. _to_int swallows all of these to 0."""
    assert _to_int("123") == 123
    assert _to_int("1,234") == 1234
    assert _to_int(None) == 0
    assert _to_int("") == 0
    assert _to_int(".") == 0
    assert _to_int("not-a-number") == 0
    assert _to_int(42) == 42


def test_parse_returns_tff_observations() -> None:
    rows = parse_socrata_response(_FIXTURE_OK)
    assert len(rows) == 2
    assert all(isinstance(r, CftcTffObservation) for r in rows)


def test_parse_extracts_typed_fields_correctly() -> None:
    rows = parse_socrata_response(_FIXTURE_OK)
    eur = next(r for r in rows if r.market_code == "099741")
    assert eur.report_date == date(2026, 4, 28)
    assert eur.market_name == "EURO FX - CHICAGO MERCANTILE EXCHANGE"
    assert eur.commodity_name == "CURRENCY"
    assert eur.open_interest == 750_000
    assert eur.dealer_long == 120_000
    assert eur.lev_money_long == 150_000
    assert eur.lev_money_short == 220_000


def test_parse_handles_comma_separated_numerics() -> None:
    """Socrata occasionally returns '1,234,567' style. _to_int strips
    the commas before int() — the gold row uses this format."""
    rows = parse_socrata_response(_FIXTURE_OK)
    gold = next(r for r in rows if r.market_code == "088691")
    assert gold.open_interest == 550_000


def test_parse_skips_rows_with_missing_report_date() -> None:
    rows = parse_socrata_response(_FIXTURE_MISSING_DATE)
    assert rows == []


def test_parse_handles_non_list_payload() -> None:
    """Defensive: if Socrata changes shape, return []."""
    assert parse_socrata_response({}) == []
    assert parse_socrata_response(None) == []  # type: ignore[arg-type]


def test_url_constant_is_socrata_endpoint() -> None:
    assert CFTC_TFF_SODA_URL.startswith("https://publicreporting.cftc.gov/resource/")
    assert CFTC_TFF_SODA_URL.endswith(".json")
    assert "gpe5-46if" in CFTC_TFF_SODA_URL


def test_tracked_market_codes_match_asset_map() -> None:
    """Every code in the whitelist must have an asset_code mapping."""
    for code in TRACKED_MARKET_CODES:
        assert code in MARKET_TO_ASSET, f"missing asset mapping for code {code!r}"


def test_tracked_market_codes_includes_8_phase1_assets() -> None:
    """The Phase 1 8-asset universe must all be tracked + treasuries."""
    asset_codes = set(MARKET_TO_ASSET.values())
    # Phase 1 universe (per `apps/api/src/ichor_api/cli/run_session_cards_batch.py`):
    for asset in (
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "SPX500_USD",
        "NAS100_USD",
    ):
        assert asset in asset_codes, f"Phase 1 asset {asset} not in MARKET_TO_ASSET values"
