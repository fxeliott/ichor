"""Pure-parsing tests for Kalshi + Manifold collectors."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_api.collectors.kalshi import (
    MACRO_SERIES,
    WATCHED_TICKERS,
    _cents_to_prob,
    _dollars_to_prob,
    _fp_to_int,
    _parse_iso,
    _parse_market,
    _yes_price,
)
from ichor_api.collectors.manifold import WATCHED_SLUGS


def test_kalshi_cents_to_prob() -> None:
    assert _cents_to_prob(45) == 0.45
    assert _cents_to_prob(100) == 1.0
    assert _cents_to_prob(0) == 0.0
    assert _cents_to_prob(None) is None


def test_kalshi_cents_to_prob_handles_garbage() -> None:
    assert _cents_to_prob("not-a-number") is None  # type: ignore[arg-type]


# ── 2026-06 schema migration (yes_bid_dollars / volume_fp) ──────────────


def test_dollars_to_prob_parses_new_schema() -> None:
    # Kalshi `*_dollars` are already in [0,1] (e.g. "0.2500"), NOT cents.
    assert _dollars_to_prob("0.2500") == 0.25
    assert _dollars_to_prob(0.52) == 0.52
    assert _dollars_to_prob("1.0000") == 1.0


def test_dollars_to_prob_rejects_out_of_range_and_garbage() -> None:
    assert _dollars_to_prob("1.5") is None  # > 1
    assert _dollars_to_prob("-0.1") is None  # < 0
    assert _dollars_to_prob(None) is None
    assert _dollars_to_prob("x") is None


def test_fp_to_int_parses_volume() -> None:
    assert _fp_to_int("9371.26") == 9371
    assert _fp_to_int(14285.16) == 14285
    assert _fp_to_int(None) is None
    assert _fp_to_int("nope") is None


def test_yes_price_prefers_mid_of_book() -> None:
    # mid(0.25, 0.43) = 0.34 — fair-value proxy
    assert _yes_price({"yes_bid_dollars": "0.2500", "yes_ask_dollars": "0.4300"}) == pytest.approx(
        0.34
    )


def test_yes_price_falls_back_to_last_then_legacy() -> None:
    assert _yes_price({"last_price_dollars": "0.5200"}) == 0.52
    # Legacy cents schema (pre-2026) still parses via the fallback
    assert _yes_price({"yes_bid": 45}) == 0.45


def test_parse_market_new_schema_real_shape() -> None:
    """A real KXFED market dict (new schema) parses to a priced snapshot."""
    now = datetime.now(UTC)
    snap = _parse_market(
        {
            "ticker": "KXFED-27APR-T4.25",
            "title": "Fed rate ≤ 4.25% by Apr 2027?",
            "yes_bid_dollars": "0.2500",
            "yes_ask_dollars": "0.4300",
            "last_price_dollars": "0.5200",
            "volume_24h_fp": "9371.26",
            "open_interest_fp": "1200.0",
            "status": "active",
        },
        now,
    )
    assert snap is not None
    assert snap.ticker == "KXFED-27APR-T4.25"
    assert snap.yes_price == pytest.approx(0.34)  # mid-of-book, not the stale last
    assert snap.volume_24h == 9371
    assert snap.open_interest == 1200


def test_parse_market_sports_multi_outcome_has_no_yes_price() -> None:
    """Sports parlay rows (no priced YES) parse but carry yes_price=None —
    discover_markets filters these out."""
    snap = _parse_market(
        {"ticker": "KXMVESPORTS-X", "title": "yes France, yes Brazil", "status": "active"},
        datetime.now(UTC),
    )
    assert snap is not None
    assert snap.yes_price is None


def test_macro_series_targets_real_macro_tickers() -> None:
    assert isinstance(MACRO_SERIES, tuple)
    assert "KXFED" in MACRO_SERIES  # Fed rate decisions
    assert "KXCPIYOY" in MACRO_SERIES  # CPI
    assert len(MACRO_SERIES) >= 8


def test_kalshi_parse_iso_valid() -> None:
    dt = _parse_iso("2026-05-03T14:30:00Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.tzinfo is not None


def test_kalshi_parse_iso_none_input() -> None:
    assert _parse_iso(None) is None
    assert _parse_iso("") is None


def test_kalshi_parse_iso_garbage() -> None:
    assert _parse_iso("not-a-date") is None


def test_kalshi_watched_tickers_is_tuple() -> None:
    """WATCHED_TICKERS is env-driven (defaults to () when no env set).
    The test validates the type contract, not emptyness — production
    Hetzner sets the env var so it's populated there."""
    assert isinstance(WATCHED_TICKERS, tuple)


def test_manifold_watched_slugs_is_tuple_lowercase() -> None:
    """WATCHED_SLUGS is env-driven. Validate type + lowercase invariant
    when populated (env-driven on Hetzner production)."""
    assert isinstance(WATCHED_SLUGS, tuple)
    for slug in WATCHED_SLUGS:
        assert slug == slug.lower(), f"slug {slug!r} not lowercase"
        assert " " not in slug
