"""Pure tests for the deterministic comparable-event key derivation.

These pin the ticker grammar parsing and the conventionalized question-text
patterns that let the cross-venue matcher align Kalshi/Polymarket/Manifold on
the same macro event without embeddings — and, just as importantly, refuse to
emit a key when the class or period is not certain (zero fabrication).
"""

from __future__ import annotations

import pytest
from ichor_agents.predictions.event_key import (
    event_class_of,
    event_key,
    is_laddered_key,
    kalshi_event_key,
    text_event_key,
)

# ─────────────────────────── Kalshi ticker grammar ─────────────────────────


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("KXFED-26JUN-T4.25", "fed_rate:2026-06"),
        ("KXFED-26JUN-T4.00", "fed_rate:2026-06"),  # sibling strike, same event
        ("KXCPIYOY-26MAR-T3.1", "cpi:2026-03"),
        ("KXU3-26JUN-T4.2", "unemployment:2026-06"),
        ("KXWRECSS-26", "recession:2026"),  # annual → year only
        ("KXWRECSS-26DEC", "recession:2026"),  # month in ticker dropped (annual)
        ("KXFOMC-27JAN-T2.5", "fed_rate:2027-01"),
    ],
)
def test_kalshi_event_key_parses_known_series(ticker: str, expected: str) -> None:
    assert kalshi_event_key(ticker) == expected


def test_kalshi_strike_ladder_collapses_to_one_event() -> None:
    """All strikes of one Fed meeting share a single event key (so they group
    and dedupe rather than each masquerading as a distinct event)."""
    ladder = ["KXFED-26JUN-T4.25", "KXFED-26JUN-T4.00", "KXFED-26JUN-T3.75"]
    keys = {kalshi_event_key(t) for t in ladder}
    assert keys == {"fed_rate:2026-06"}


def test_kalshi_event_key_unknown_series_is_none() -> None:
    assert kalshi_event_key("KXNBA-26JUN-LAKERS") is None
    assert kalshi_event_key("INXD-26JUN") is None


def test_kalshi_event_key_empty_or_no_period_is_none() -> None:
    assert kalshi_event_key("") is None
    assert kalshi_event_key("KXFED") is None  # no period segment → no guess


# ─────────────────────────── Question-text patterns ────────────────────────


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Will the Fed cut rates in June 2026?", "fed_rate:2026-06"),
        ("Fed rate cut by May 2026 ?", "fed_rate:2026-05"),
        ("FOMC holds in 2026 March", "fed_rate:2026-03"),
        ("US recession in 2026?", "recession:2026"),
        ("Will there be a recession by June 2026?", "recession:2026"),  # annual → year
        ("CPI inflation rate above 3% in June 2026", "cpi:2026-06"),
        ("Unemployment rate June 2026", "unemployment:2026-06"),
        ("Fed decision Q2 2026", "fed_rate:2026-q2"),  # quarter kept distinct
    ],
)
def test_text_event_key_parses_conventional_macro(question: str, expected: str) -> None:
    assert text_event_key(question) == expected


def test_text_event_key_no_macro_class_is_none() -> None:
    # The witnessed false-match class: non-macro names share generic tokens but
    # neither is a macro event → no key (so the matcher will not align them on
    # an event key; a separate salient-token gate handles their Jaccard match).
    assert text_event_key("Will Jordan Brunson win the title?") is None
    assert text_event_key("Will JD Vance run in 2028?") is None  # election, not in macro set


def test_text_event_key_macro_class_without_period_is_none() -> None:
    # Right class, but no confident period → refuse to guess.
    assert text_event_key("Will the Fed cut rates?") is None
    assert text_event_key("CPI inflation print this month") is None


def test_text_event_key_empty_is_none() -> None:
    assert text_event_key("") is None


# ─────────────────────────── Dispatch + helpers ────────────────────────────


def test_event_key_kalshi_prefers_ticker_then_text() -> None:
    # Kalshi: ticker wins even if the title text is vague.
    assert event_key("kalshi", "KXFED-26JUN-T4.25", "Fed funds upper bound") == "fed_rate:2026-06"
    # Kalshi with unknown ticker falls back to the title text.
    assert (
        event_key("kalshi", "KXNBA-26JUN", "Will the Fed cut in June 2026?") == "fed_rate:2026-06"
    )


def test_event_key_polymarket_manifold_use_text() -> None:
    assert (
        event_key("polymarket", "fed-cut-june", "Will the Fed cut in June 2026?")
        == "fed_rate:2026-06"
    )
    assert event_key("manifold", "slug-x", "US recession in 2026?") == "recession:2026"


def test_cross_venue_keys_align_on_same_event() -> None:
    """The core property: a Kalshi Fed strike and a Polymarket Fed binary land
    on the same class+period key (so the precision gate groups them as the
    same event rather than treating them as unrelated)."""
    kal = event_key("kalshi", "KXFED-26JUN-T4.25", "Fed funds rate June 2026")
    poly = event_key("polymarket", "fed-cut-jun", "Will the Fed cut rates in June 2026?")
    assert kal == poly == "fed_rate:2026-06"


def test_event_class_of() -> None:
    assert event_class_of("fed_rate:2026-06") == "fed_rate"
    assert event_class_of("recession:2026") == "recession"
    assert event_class_of(None) is None
    assert event_class_of("nonsense") is None


def test_is_laddered_key() -> None:
    # Fed/CPI/unemployment are per-strike ladders on Kalshi → must not be
    # blindly fused with a binary; recession is binary-equivalent.
    assert is_laddered_key("fed_rate:2026-06") is True
    assert is_laddered_key("cpi:2026-06") is True
    assert is_laddered_key("unemployment:2026-06") is True
    assert is_laddered_key("recession:2026") is False
    assert is_laddered_key(None) is False
