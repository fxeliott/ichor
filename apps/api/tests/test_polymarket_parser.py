"""Pure-parsing tests for the Polymarket collector.

No HTTP — payloads are fixtures shaped after real gamma-api responses
observed in 2026 (defensive parsing is the point — schema may evolve).
"""

from __future__ import annotations

from ichor_api.collectors.polymarket import (
    WATCHED_SLUGS,
    _is_macro_question,
    _parse_market,
)


# ───────────────────────── Macro keyword filter (Wave 31) ──────────────────


def test_macro_filter_matches_fed_questions() -> None:
    assert _is_macro_question("Will the Fed cut rates in June 2026?")
    assert _is_macro_question("FOMC dot plot revision Q3?")


def test_macro_filter_matches_geopolitics() -> None:
    assert _is_macro_question("Russia-Ukraine ceasefire by end of 2026?")
    assert _is_macro_question("Will Iran strike a deal with US?")


def test_macro_filter_matches_us_politics_with_macro_impact() -> None:
    assert _is_macro_question("Trump 2026 tariff > 25 % on China?")
    assert _is_macro_question("US debt ceiling fight before October?")


def test_macro_filter_rejects_sports_and_entertainment() -> None:
    assert not _is_macro_question("Will the Lakers win the NBA finals?")
    assert not _is_macro_question("Will Drake release a new album?")
    assert not _is_macro_question("UFC 300 champion?")


def test_macro_filter_rejects_empty() -> None:
    assert not _is_macro_question("")
    assert not _is_macro_question("   ")


def test_macro_filter_case_insensitive() -> None:
    assert _is_macro_question("FED HIKE COMING?")
    assert _is_macro_question("Recession in 2026?")


def test_parse_normal_binary_market() -> None:
    payload = {
        "id": "12345",
        "conditionId": "0xabc",
        "question": "Will the Fed cut rates in March 2026?",
        "closed": False,
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.62", "0.38"],
        "volume": "1234567.89",
    }
    snap = _parse_market("fed-march-2026", payload)
    assert snap is not None
    assert snap.slug == "fed-march-2026"
    assert snap.market_id == "12345"
    assert snap.question.startswith("Will the Fed")
    assert snap.outcomes == ["Yes", "No"]
    assert snap.last_prices == [0.62, 0.38]
    assert snap.yes_price == 0.62
    assert snap.volume_usd == 1234567.89
    assert snap.closed is False


def test_parse_outcomes_as_json_string() -> None:
    """gamma-api sometimes returns outcomes/outcomePrices as JSON-encoded strings."""
    payload = {
        "id": "999",
        "question": "Recession in 2026?",
        "closed": False,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.41", "0.59"]',
        "volume": "5000",
    }
    snap = _parse_market("recession-2026", payload)
    assert snap is not None
    assert snap.outcomes == ["Yes", "No"]
    assert snap.last_prices == [0.41, 0.59]


def test_parse_handles_lasttradeprices_alias() -> None:
    payload = {
        "id": "55",
        "question": "ECB cut at next meeting?",
        "closed": False,
        "outcomeNames": ["Yes", "No"],
        "lastTradePrices": [0.7, 0.3],
        "volume": 10_000,
    }
    snap = _parse_market("ecb-cut", payload)
    assert snap is not None
    assert snap.last_prices == [0.7, 0.3]


def test_parse_returns_none_when_outcomes_missing() -> None:
    snap = _parse_market("broken", {"id": "1", "question": "?", "closed": False})
    assert snap is None


def test_parse_returns_none_when_lengths_mismatch() -> None:
    payload = {
        "id": "1",
        "question": "?",
        "closed": False,
        "outcomes": ["Yes", "No", "Maybe"],
        "outcomePrices": ["0.5", "0.5"],
    }
    snap = _parse_market("bad", payload)
    assert snap is None


def test_parse_handles_missing_volume() -> None:
    payload = {
        "id": "1",
        "question": "?",
        "closed": True,
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.99", "0.01"],
    }
    snap = _parse_market("dust", payload)
    assert snap is not None
    assert snap.volume_usd is None
    assert snap.closed is True


def test_yes_price_when_no_data() -> None:
    payload = {
        "id": "1",
        "question": "?",
        "closed": False,
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.5", "0.5"],
    }
    snap = _parse_market("ok", payload)
    assert snap is not None
    assert snap.yes_price == 0.5


def test_watched_slugs_unique_and_nonempty() -> None:
    assert len(WATCHED_SLUGS) >= 4
    assert len(set(WATCHED_SLUGS)) == len(WATCHED_SLUGS)
    for slug in WATCHED_SLUGS:
        assert slug == slug.lower()
        assert " " not in slug
