"""Pure-parsing tests for the CFTC COT collector (Socrata Disaggregated).

Root-cause fix: the legacy flat-file (`f_disagg.txt`) parser used csv.DictReader
on a HEADERLESS file → zero rows in prod (the old test passed against a synthetic
header = false-green). We now mirror the proven TFF Socrata path. Field shapes
and values below are from the LIVE gold (088691) row dated 2026-06-02, verified
against resource `72hh-3qpy` on 2026-06-09.
"""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.cot import (
    MARKET_CODE_TO_ASSET,
    _to_int,
    parse_socrata_response,
)

# Real gold (088691) Socrata row, 2026-06-02 (trimmed to fields the parser reads).
_GOLD_ROW = {
    "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
    "report_date_as_yyyy_mm_dd": "2026-06-02T00:00:00.000",
    "cftc_contract_market_code": "088691",
    "open_interest_all": "326052",
    "prod_merc_positions_long": "10275",
    "prod_merc_positions_short": "30429",
    "swap_positions_long_all": "27505",
    "swap__positions_short_all": "213696",  # sic: double underscore (CFTC quirk)
    "m_money_positions_long_all": "129367",
    "m_money_positions_short_all": "17188",
    "other_rept_positions_long": "76729",
    "other_rept_positions_short": "12888",
    "nonrept_positions_long_all": "43656",
    "nonrept_positions_short_all": "13331",
}


def test_to_int_handles_commas_empty_dot_garbage() -> None:
    assert _to_int("1,234,567") == 1234567
    assert _to_int("") == 0
    assert _to_int(".") == 0
    assert _to_int(None) == 0
    assert _to_int("not-a-number") == 0
    assert _to_int("123") == 123


def test_parse_socrata_extracts_gold_fields() -> None:
    rows = parse_socrata_response([_GOLD_ROW])
    assert len(rows) == 1
    g = rows[0]
    assert g.market_code == "088691"
    assert g.report_date == date(2026, 6, 2)
    assert g.market_name.startswith("GOLD")
    assert g.open_interest == 326_052
    assert g.producer_net == 10_275 - 30_429  # -20,154 (commercials net short)
    assert g.managed_money_net == 129_367 - 17_188  # +112,179
    assert g.non_reportable_net == 43_656 - 13_331  # +30,325
    assert g.other_reportable_net == 76_729 - 12_888  # +63,841


def test_parse_socrata_reads_double_underscore_swap_short() -> None:
    # Guard the CFTC field-name quirk: swap SHORT is `swap__positions_short_all`
    # (double underscore). A single-underscore lookup would read 0 and make
    # swap_dealer_net wrong (+27,505 instead of -186,191).
    rows = parse_socrata_response([_GOLD_ROW])
    assert rows[0].swap_dealer_net == 27_505 - 213_696  # -186,191


def test_parse_socrata_skips_rows_without_code_or_date() -> None:
    no_code = {**_GOLD_ROW, "cftc_contract_market_code": ""}
    no_date = {**_GOLD_ROW, "report_date_as_yyyy_mm_dd": ""}
    rows = parse_socrata_response([no_code, no_date, _GOLD_ROW])
    assert len(rows) == 1
    assert rows[0].market_code == "088691"


def test_parse_socrata_naive_iso_date() -> None:
    row = {**_GOLD_ROW, "report_date_as_yyyy_mm_dd": "2026-06-02"}
    rows = parse_socrata_response([row])
    assert rows[0].report_date == date(2026, 6, 2)


def test_parse_socrata_not_list_and_empty() -> None:
    assert parse_socrata_response([]) == []
    assert parse_socrata_response({"oops": 1}) == []  # non-list payload → []


def test_market_code_mapping_covers_phase1_assets() -> None:
    """All 8 Phase 1 assets must have a CFTC market code mapping (unchanged)."""
    expected = {
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "US30",
        "US100",
    }
    assert expected == set(MARKET_CODE_TO_ASSET.values())
