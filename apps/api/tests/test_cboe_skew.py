"""Pure-parsing tests for cboe_skew collector.

No network. Yahoo Finance JSON sample fixed at module top, parser
exercised in isolation. Idempotent + deterministic.
"""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.cboe_skew import (
    SKEW_CHART_URL,
    CboeSkewObservation,
    parse_chart_response,
)


# Verified live 2026-05-08 against query1.finance.yahoo.com — trimmed
# to a 3-day window. Two trading days + one null (e.g. weekend hole).
_FIXTURE_OK: dict = {
    "chart": {
        "result": [
            {
                "meta": {
                    "currency": "USD",
                    "symbol": "^SKEW",
                    "regularMarketPrice": 141.38,
                },
                # 2026-05-01 16:30 UTC (Fri close)
                # 2026-05-02 16:30 UTC (Sat — null)
                # 2026-05-04 20:30 UTC (Mon close)
                "timestamp": [1777996200, 1778082600, 1778255400],
                "indicators": {
                    "quote": [
                        {
                            "close": [141.38, None, 138.92],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}


_FIXTURE_ERROR: dict = {
    "chart": {
        "result": None,
        "error": {
            "code": "Not Found",
            "description": "No data found, symbol may be delisted",
        },
    }
}


_FIXTURE_SHAPE_DRIFT: dict = {"chart": {"result": [{}]}}  # missing timestamp/quote


def test_parse_returns_skew_observations() -> None:
    rows = parse_chart_response(_FIXTURE_OK)
    # 3 timestamps, 1 null close → 2 observations
    assert len(rows) == 2
    assert all(isinstance(r, CboeSkewObservation) for r in rows)


def test_parse_extracts_typed_fields_correctly() -> None:
    rows = parse_chart_response(_FIXTURE_OK)
    # Order preserved
    assert rows[0].skew_value == 141.38
    assert rows[1].skew_value == 138.92
    # Date conversion: 1777996200 epoch s = 2026-05-05 22:30 UTC
    # (Yahoo timestamps are at session close, not midnight)
    assert isinstance(rows[0].observation_date, date)
    assert rows[0].observation_date.year == 2026
    assert rows[0].observation_date.month == 5


def test_parse_handles_yahoo_error_payload() -> None:
    """Yahoo returns chart.error != null on missing/delisted symbol —
    parser must return [] without exception."""
    rows = parse_chart_response(_FIXTURE_ERROR)
    assert rows == []


def test_parse_handles_shape_drift_gracefully() -> None:
    """If Yahoo changes the schema, parser returns [] — collector
    convention is best-effort, never raise."""
    rows = parse_chart_response(_FIXTURE_SHAPE_DRIFT)
    assert rows == []


def test_parse_handles_empty_payload() -> None:
    rows = parse_chart_response({})
    assert rows == []


def test_url_constant_is_yahoo_chart_endpoint() -> None:
    """Sanity: the URL is what we expect (not a typo or mirror)."""
    assert SKEW_CHART_URL.startswith("https://query1.finance.yahoo.com")
    # ^ must be URL-encoded as %5E
    assert "%5ESKEW" in SKEW_CHART_URL
