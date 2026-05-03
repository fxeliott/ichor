"""Pure-parsing tests for Kalshi + Manifold collectors."""

from __future__ import annotations

from ichor_api.collectors.kalshi import _cents_to_prob, _parse_iso, WATCHED_TICKERS
from ichor_api.collectors.manifold import WATCHED_SLUGS


def test_kalshi_cents_to_prob() -> None:
    assert _cents_to_prob(45) == 0.45
    assert _cents_to_prob(100) == 1.0
    assert _cents_to_prob(0) == 0.0
    assert _cents_to_prob(None) is None


def test_kalshi_cents_to_prob_handles_garbage() -> None:
    assert _cents_to_prob("not-a-number") is None  # type: ignore[arg-type]


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


def test_kalshi_watched_tickers_non_empty() -> None:
    assert len(WATCHED_TICKERS) >= 4


def test_manifold_watched_slugs_non_empty() -> None:
    assert len(WATCHED_SLUGS) >= 3
    # All slugs should be lowercase, no spaces
    for slug in WATCHED_SLUGS:
        assert slug == slug.lower()
        assert " " not in slug
