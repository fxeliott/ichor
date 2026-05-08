"""Pure-parsing tests for treasury_tic collector.

No HTTP. Fixtures shaped after real Treasury mfhhis01.txt observed
2026-05-08 (TAB-separated, 12 columns months × years header pattern).
"""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.treasury_tic import (
    MFH_HISTORY_URL,
    TreasuryTicHolding,
    parse_mfh_history,
)


_FIXTURE_OK = (
    "\t\t\tMAJOR FOREIGN HOLDERS OF TREASURY SECURITIES\t\t\t\t\t\t\t\t\t\t\t\n"
    "\t\t\t    (in billions of dollars)\t\t\t\t\t\t\t\t\t\t\t\n"
    "\t\t\tHOLDINGS 1/ AT END OF PERIOD\t\t\t\t\t\t\t\t\t\t\t\n"
    "\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
    "\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
    "\tDec\tNov\tOct\tSep\t\n"
    "Country\t2025\t2025\t2025\t2025\t\n"
    "\t------\t------\t------\t------\t\n"
    "\t\t\t\t\t\n"
    "Japan\t1185.5\t1202.7\t1200\t1189.3\t\n"
    "China, Mainland\t731.0\t735.0\t738.0\t740.0\t\n"
    "United Kingdom\t800.0\t790.0\t785.0\t780.0\t\n"
    "Grand Total\t9000.0\t8950.0\t8900.0\t8850.0\t\n"
    "\t\t\t\t\t\n"
    "Of which:\t\t\t\t\t\n"
    " For. Official\t4000.0\t3990.0\t3980.0\t3970.0\t\n"
    "\n"
    "Department of the Treasury/Federal Reserve Board\n"
    "February 18, 2026\n"
    "\n"
    " 1/  The data in this table are collected primarily...\n"
)


def test_parse_extracts_all_country_month_records() -> None:
    rows = parse_mfh_history(_FIXTURE_OK)
    # 4 countries (Japan/China/UK/Grand Total) × 4 months = 16 records
    assert len(rows) == 16


def test_parse_typed_fields() -> None:
    rows = parse_mfh_history(_FIXTURE_OK)
    japan_dec = next(
        r for r in rows
        if r.country == "Japan" and r.observation_month == date(2025, 12, 1)
    )
    assert japan_dec.holdings_bn_usd == 1185.5
    assert isinstance(japan_dec, TreasuryTicHolding)


def test_parse_handles_china_mainland_label_with_comma() -> None:
    rows = parse_mfh_history(_FIXTURE_OK)
    china = [r for r in rows if r.country == "China, Mainland"]
    assert len(china) == 4
    assert all(r.holdings_bn_usd > 700 for r in china)


def test_parse_stops_at_footer_of_which_marker() -> None:
    """The 'Of which:' line and below must NOT be parsed as country rows."""
    rows = parse_mfh_history(_FIXTURE_OK)
    countries = {r.country for r in rows}
    assert "For. Official" not in countries
    assert "Department of the Treasury" not in str(countries)


def test_parse_multi_month_periods_distinct() -> None:
    rows = parse_mfh_history(_FIXTURE_OK)
    months = {r.observation_month for r in rows}
    assert months == {
        date(2025, 12, 1),
        date(2025, 11, 1),
        date(2025, 10, 1),
        date(2025, 9, 1),
    }


def test_parse_empty_payload_returns_empty_list() -> None:
    assert parse_mfh_history("") == []


def test_parse_garbage_returns_empty_list() -> None:
    assert parse_mfh_history("not a TIC file at all") == []


def test_url_constant_is_canonical_treasury() -> None:
    assert MFH_HISTORY_URL.startswith("https://ticdata.treasury.gov")
    assert "mfhhis01.txt" in MFH_HISTORY_URL
