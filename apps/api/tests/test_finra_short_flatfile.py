"""Tests for FINRA Reg SHO public flat-file collector path (r53).

The OAuth-gated `api.finra.org/data/group/.../regShoDaily` was the silent-dead
root cause since collector inception (r52 wave-2 subagent M). r53 ships the
free CDN flat-file alternative `cdn.finra.org/equity/regsho/daily/...`.

These tests pin parser correctness + URL pattern + symbol-filter behavior.
"""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.finra_short import (
    _FLATFILE_HEADERS,
    FINRA_FLATFILE_BASE,
    _parse_flatfile,
)

# ----- Sample fixtures (real format from Hetzner curl 2026-05-15) -----

_SAMPLE_HEAD = """\
Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
20260514|A|319623.012649|406|610811.274367|B,Q,N
20260514|AA|743219.698252|409|1601341.347542|B,Q,N
20260514|SPY|45000000.0|125000.0|130000000.0|B,Q,N
20260514|QQQ|22500000.0|98000.0|65000000.0|B,Q,N
20260514|GLD|1200000.0|5500.0|3500000.0|B,Q,N
20260514|AAAA|1015|0|2564.299229|Q
"""


# ----- URL pattern tests ----------------------------------------------


def test_flatfile_url_pattern_uses_yyyymmdd_format() -> None:
    """URL must use YYYYMMDD format (no separator) per FINRA convention."""
    url = FINRA_FLATFILE_BASE.format(date="20260514")
    assert url == "https://cdn.finra.org/equity/regsho/daily/CNMSshvol20260514.txt"
    assert "20260514" in url
    # Negative : reject ISO date drift
    bad_url = FINRA_FLATFILE_BASE.format(date="2026-05-14")
    assert bad_url != url, "URL pattern must require YYYYMMDD without dashes"


def test_flatfile_uses_https_cdn_finra_subdomain() -> None:
    """Pin URL to cdn.finra.org (CDN-cached, no rate limit) per Voie D."""
    assert FINRA_FLATFILE_BASE.startswith("https://cdn.finra.org/")
    assert "/equity/regsho/daily/CNMSshvol" in FINRA_FLATFILE_BASE


# ----- HEADERS tests --------------------------------------------------


def test_flatfile_headers_use_realistic_browser_ua() -> None:
    """Anti-WAF defense in depth — match r52 nyfed_mct UA fix pattern."""
    ua = _FLATFILE_HEADERS.get("User-Agent", "")
    assert "Chrome/" in ua, f"UA must contain Chrome version, got: {ua!r}"
    assert "compatible;" not in ua.lower(), "UA must NOT match bot-flag pattern"
    assert "ichor" not in ua.lower(), "UA must NOT contain 'ichor' (bot-URL)"


# ----- Parser tests ---------------------------------------------------


def test_parse_flatfile_filters_to_symbols_only() -> None:
    """Symbols filter must drop unrequested symbols (CDN file has all
    US equities ~10 000 rows, we only want our universe)."""
    result = _parse_flatfile(_SAMPLE_HEAD, frozenset({"SPY", "QQQ", "GLD"}))
    assert len(result) == 3
    symbols_returned = {r.symbol for r in result}
    assert symbols_returned == {"SPY", "QQQ", "GLD"}
    # Must NOT include A, AA, AAAA which were in the file
    assert "A" not in symbols_returned
    assert "AAAA" not in symbols_returned


def test_parse_flatfile_handles_float_volumes() -> None:
    """FINRA reports volumes as floats (ATS partial-share aggregation).
    Parser must coerce via int(float(x))."""
    result = _parse_flatfile(_SAMPLE_HEAD, frozenset({"SPY"}))
    assert len(result) == 1
    spy = result[0]
    assert spy.short_volume == 45000000
    assert spy.total_volume == 130000000
    assert spy.short_exempt_volume == 125000


def test_parse_flatfile_computes_short_pct() -> None:
    """short_pct = short_volume / total_volume must compute correctly
    when both non-zero."""
    result = _parse_flatfile(_SAMPLE_HEAD, frozenset({"SPY"}))
    spy = result[0]
    expected_pct = 45000000 / 130000000
    assert spy.short_pct is not None
    assert abs(spy.short_pct - expected_pct) < 1e-9


def test_parse_flatfile_skips_header_row() -> None:
    """First row is `Date|Symbol|ShortVolume|...` literal header — must
    be skipped (parsing 'Date' as a date would return None and skip)."""
    result = _parse_flatfile(_SAMPLE_HEAD, frozenset({"Date", "Symbol"}))
    # Even though we filter for "Date" symbol, the header row's Date
    # field is the literal string "Date" which fails _parse_date
    # → skipped. So no rows returned.
    assert result == []


def test_parse_flatfile_uppercase_symbol() -> None:
    """Symbols normalized to uppercase regardless of input case."""
    body = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n20260514|spy|100|0|200|B"
    result = _parse_flatfile(body, frozenset({"SPY"}))
    assert len(result) == 1
    assert result[0].symbol == "SPY"


def test_parse_flatfile_parses_yyyymmdd_date() -> None:
    """Date column is YYYYMMDD format, must parse to Python date."""
    result = _parse_flatfile(_SAMPLE_HEAD, frozenset({"SPY"}))
    assert result[0].trade_date == date(2026, 5, 14)


def test_parse_flatfile_empty_input_returns_empty_list() -> None:
    """No body → no rows (defensive)."""
    assert _parse_flatfile("", frozenset({"SPY"})) == []
    assert _parse_flatfile("\n\n", frozenset({"SPY"})) == []


def test_parse_flatfile_skips_malformed_rows() -> None:
    """Rows with <5 cells (truncated, footer text) are skipped silently."""
    body = (
        "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
        "20260514|SPY|100|0|200|B\n"
        "MALFORMED|ROW\n"  # only 2 cells — must skip
        "FileFormat=v2.0\n"  # footer pattern
    )
    result = _parse_flatfile(body, frozenset({"SPY"}))
    assert len(result) == 1
    assert result[0].symbol == "SPY"
