"""Pure-parsing tests for cme_zq_futures collector. Mirror cboe_skew tests."""

from __future__ import annotations

from datetime import date

from ichor_api.collectors.cme_zq_futures import (
    ZQ_CHART_URL,
    ZqFuturesObservation,
    parse_chart_response,
)


_FIXTURE_OK: dict = {
    "chart": {
        "result": [
            {
                "meta": {"symbol": "ZQ=F", "regularMarketPrice": 96.365},
                "timestamp": [1777996200, 1778082600, 1778255400],
                "indicators": {
                    "quote": [{"close": [96.36, None, 96.40]}]
                },
            }
        ],
        "error": None,
    }
}


_FIXTURE_ERROR: dict = {
    "chart": {"result": None, "error": {"code": "Not Found"}}
}


def test_parse_returns_zq_observations() -> None:
    rows = parse_chart_response(_FIXTURE_OK)
    assert len(rows) == 2  # 1 null close skipped


def test_parse_implied_effr_formula() -> None:
    """100 - ZQ_price = implied EFFR. Wave 47 invariant."""
    rows = parse_chart_response(_FIXTURE_OK)
    assert rows[0].zq_price == 96.36
    assert abs(rows[0].implied_effr - 3.64) < 0.001
    assert rows[1].zq_price == 96.40
    assert abs(rows[1].implied_effr - 3.60) < 0.001


def test_parse_returns_typed_objects() -> None:
    rows = parse_chart_response(_FIXTURE_OK)
    assert all(isinstance(r, ZqFuturesObservation) for r in rows)
    assert isinstance(rows[0].observation_date, date)


def test_parse_handles_yahoo_error_payload() -> None:
    assert parse_chart_response(_FIXTURE_ERROR) == []


def test_parse_handles_empty_payload() -> None:
    assert parse_chart_response({}) == []


def test_url_constant_yahoo_chart_endpoint() -> None:
    assert ZQ_CHART_URL.startswith("https://query1.finance.yahoo.com")
    # ZQ=F URL-encoded
    assert "ZQ%3DF" in ZQ_CHART_URL
