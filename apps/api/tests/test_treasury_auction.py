"""Pure-parsing tests for the Treasury auction collector."""

from __future__ import annotations

from datetime import date, datetime

from ichor_api.collectors.treasury_auction import (
    AuctionResult,
    parse_auctions_response,
    supported_security_types,
)


def test_parse_canonical_response() -> None:
    body = {
        "data": [
            {
                "record_date": "2026-05-01",
                "issue_date": "2026-05-01",
                "security_type": "Note",
                "security_term": "2-Year",
                "high_yield": "4.250",
                "median_yield": "4.230",
                "low_yield": "4.200",
                "bid_to_cover_ratio": "2.55",
            }
        ]
    }
    out = parse_auctions_response(body)
    assert len(out) == 1
    assert out[0].security_type == "Note"
    assert out[0].high_yield == 4.250


def test_tail_bps_computation() -> None:
    """Tail = (high - median) × 100 (= bps in percentage points)."""
    import pytest

    r = AuctionResult(
        record_date=date(2026, 5, 1),
        issue_date=date(2026, 5, 1),
        security_type="Note",
        security_term="2-Year",
        high_yield=4.30,
        median_yield=4.28,
        low_yield=4.25,
        bid_to_cover_ratio=2.5,
        fetched_at=datetime(2026, 5, 5),
    )
    # tail = (4.30 - 4.28) × 100 = 2.0 bps (float-fuzz tolerant)
    assert r.tail_bps == pytest.approx(2.0, abs=1e-9)


def test_tail_bps_none_when_yields_missing() -> None:
    r = AuctionResult(
        record_date=date(2026, 5, 1),
        issue_date=date(2026, 5, 1),
        security_type="Bill",
        security_term="4-Week",
        high_yield=None,
        median_yield=4.20,
        low_yield=4.15,
        bid_to_cover_ratio=3.0,
        fetched_at=datetime(2026, 5, 5),
    )
    assert r.tail_bps is None


def test_parse_handles_null_strings() -> None:
    """fiscaldata returns 'null' strings for missing values."""
    body = {
        "data": [
            {
                "record_date": "2026-05-01",
                "issue_date": "2026-05-01",
                "security_type": "Bill",
                "security_term": "4-Week",
                "high_yield": "null",
                "median_yield": "",
                "low_yield": None,
                "bid_to_cover_ratio": "3.10",
            }
        ]
    }
    out = parse_auctions_response(body)
    assert len(out) == 1
    assert out[0].high_yield is None
    assert out[0].median_yield is None
    assert out[0].bid_to_cover_ratio == 3.10


def test_parse_skips_malformed_rows() -> None:
    body = {
        "data": [
            "garbage",
            {"record_date": "bad-date", "issue_date": "2026-05-01"},
            {"issue_date": "bad-date", "record_date": "2026-05-01"},
            {  # one valid
                "record_date": "2026-05-01",
                "issue_date": "2026-05-01",
                "security_type": "Note",
                "security_term": "5-Year",
            },
        ]
    }
    out = parse_auctions_response(body)
    assert len(out) == 1


def test_supported_security_types_canonical() -> None:
    types = supported_security_types()
    for t in ("Bill", "Note", "Bond", "FRN", "TIPS"):
        assert t in types
