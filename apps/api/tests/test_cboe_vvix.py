"""Pure-parsing tests for cboe_vvix collector. Mirror of test_cboe_skew."""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.cboe_vvix import (
    VVIX_CHART_URL,
    CboeVvixObservation,
    parse_chart_response,
)

_FIXTURE_OK: dict = {
    "chart": {
        "result": [
            {
                "meta": {
                    "currency": "USD",
                    "symbol": "^VVIX",
                    "regularMarketPrice": 95.68,
                },
                "timestamp": [1777996200, 1778082600, 1778255400],
                "indicators": {
                    "quote": [
                        {
                            "close": [95.68, None, 92.41],
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


_FIXTURE_SHAPE_DRIFT: dict = {"chart": {"result": [{}]}}


def test_parse_returns_vvix_observations() -> None:
    rows = parse_chart_response(_FIXTURE_OK)
    assert len(rows) == 2
    assert all(isinstance(r, CboeVvixObservation) for r in rows)


def test_parse_extracts_typed_fields_correctly() -> None:
    rows = parse_chart_response(_FIXTURE_OK)
    assert rows[0].vvix_value == 95.68
    assert rows[1].vvix_value == 92.41
    assert isinstance(rows[0].observation_date, date)
    assert rows[0].observation_date.year == 2026


def test_parse_handles_yahoo_error_payload() -> None:
    """Yahoo returns chart.error != null on missing/delisted symbol."""
    assert parse_chart_response(_FIXTURE_ERROR) == []


def test_parse_handles_shape_drift_gracefully() -> None:
    assert parse_chart_response(_FIXTURE_SHAPE_DRIFT) == []


def test_parse_handles_empty_payload() -> None:
    assert parse_chart_response({}) == []


def test_url_constant_is_yahoo_chart_endpoint() -> None:
    assert VVIX_CHART_URL.startswith("https://query1.finance.yahoo.com")
    assert "%5EVVIX" in VVIX_CHART_URL
