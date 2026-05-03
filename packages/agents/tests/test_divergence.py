"""Pure tests for the prediction-market divergence detector."""

from __future__ import annotations

import pytest

from ichor_agents.predictions import (
    DivergenceAlert,
    PredictionMarket,
    detect_divergences,
    jaccard_similarity,
    match_across_venues,
    normalize_question,
    tokenize,
)


# ─────────────────────────── Normalization / tokenize ──────────────────


def test_normalize_lowercases_and_drops_punctuation() -> None:
    assert normalize_question("Will the Fed cut rates in May 2026?") == (
        "will the fed cut rates in may 2026"
    )


def test_normalize_collapses_whitespace_and_dashes() -> None:
    assert normalize_question(
        "  US-CHINA  trade   deal  by   Q3?  "
    ) == "us china trade deal by q3"


def test_tokenize_removes_stopwords() -> None:
    toks = tokenize("Will the Fed cut rates by May 2026?")
    assert "will" not in toks  # stopword
    assert "the" not in toks
    assert "by" not in toks
    assert "fed" in toks
    assert "cut" in toks
    assert "rates" in toks


def test_tokenize_removes_yes_no_market_noise() -> None:
    toks = tokenize("Yes/No market : Fed cut event contract")
    assert "yes" not in toks
    assert "no" not in toks
    assert "market" not in toks
    assert "event" not in toks
    assert "contract" not in toks
    assert "fed" in toks


# ─────────────────────────── Jaccard similarity ────────────────────────


def test_jaccard_identical_token_lists() -> None:
    a = ["fed", "cut", "rates"]
    assert jaccard_similarity(a, list(a)) == pytest.approx(1.0)


def test_jaccard_zero_overlap() -> None:
    assert jaccard_similarity(["fed", "cut"], ["bitcoin", "halving"]) == 0.0


def test_jaccard_partial_overlap() -> None:
    # {fed, cut, rate} ∩ {fed, cut} = {fed, cut} ; ∪ = {fed, cut, rate} → 2/3
    assert jaccard_similarity(["fed", "cut", "rate"], ["fed", "cut"]) == pytest.approx(
        2 / 3
    )


def test_jaccard_empty_returns_zero() -> None:
    assert jaccard_similarity([], []) == 0.0
    assert jaccard_similarity(["fed"], []) == 0.0


# ─────────────────────────── Matching ──────────────────────────────────


def _pm(venue, mid, question, price):
    return PredictionMarket(venue=venue, market_id=mid, question=question, yes_price=price)


def test_match_across_three_venues_on_similar_question() -> None:
    poly = [_pm("polymarket", "p1", "Will the Fed cut rates by May 2026?", 0.62)]
    kal = [_pm("kalshi", "k1", "Fed rate cut by May 2026 ?", 0.47)]
    man = [_pm("manifold", "m1", "Fed cut rates in May 2026", 0.55)]
    out = match_across_venues(poly, kal, man, threshold=0.5)
    assert len(out) == 1
    m = out[0]
    assert set(m.by_venue.keys()) == {"polymarket", "kalshi", "manifold"}
    assert m.similarity >= 0.5


def test_match_polymarket_only_no_match_dropped() -> None:
    """A Polymarket question with no Kalshi/Manifold counterpart is not
    surfaced (no cross-venue signal)."""
    poly = [_pm("polymarket", "p1", "Will Bitcoin halving cause a rally?", 0.7)]
    kal = [_pm("kalshi", "k1", "Will the Fed cut rates by May 2026?", 0.5)]
    man = [_pm("manifold", "m1", "Recession before 2027 ?", 0.3)]
    out = match_across_venues(poly, kal, man, threshold=0.55)
    # Polymarket bitcoin solo : not in output (orphans aren't surfaced)
    assert all(
        "bitcoin" not in m.representative_question.lower() for m in out
    )


def test_match_kalshi_manifold_orphan_when_polymarket_absent() -> None:
    """Kalshi ↔ Manifold pairs without Polymarket still match."""
    poly: list[PredictionMarket] = []
    kal = [_pm("kalshi", "k1", "Will Trump win 2028 ?", 0.45)]
    man = [_pm("manifold", "m1", "Trump win 2028 election", 0.40)]
    out = match_across_venues(poly, kal, man, threshold=0.55)
    assert len(out) == 1
    assert "polymarket" not in out[0].by_venue
    assert set(out[0].by_venue.keys()) == {"kalshi", "manifold"}


def test_match_threshold_excludes_low_similarity() -> None:
    poly = [_pm("polymarket", "p1", "Fed cut rates May 2026", 0.6)]
    # Question with only 1 shared token (cut) — low Jaccard
    kal = [_pm("kalshi", "k1", "Will Suez Canal stay open in 2026 ?", 0.7)]
    man: list[PredictionMarket] = []
    out = match_across_venues(poly, kal, man, threshold=0.55)
    assert out == []


def test_match_does_not_double_count_kalshi_market() -> None:
    """A Kalshi market matched to one Polymarket cannot be reused."""
    poly = [
        _pm("polymarket", "p1", "Fed cut rates May 2026", 0.6),
        _pm("polymarket", "p2", "Fed cut rates 2026 May", 0.65),
    ]
    kal = [_pm("kalshi", "k1", "Fed cut rates 2026 May", 0.5)]
    man: list[PredictionMarket] = []
    out = match_across_venues(poly, kal, man, threshold=0.55)
    matched_with_kal = sum(1 for m in out if "kalshi" in m.by_venue)
    assert matched_with_kal == 1


def test_match_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        match_across_venues([], [], [], threshold=1.5)
    with pytest.raises(ValueError):
        match_across_venues([], [], [], threshold=-0.1)


# ─────────────────────────── Divergence detection ──────────────────────


def _matched(by_venue):
    from ichor_agents.predictions import MatchedMarket

    rep = next(iter(by_venue.values())).question
    return MatchedMarket(
        representative_question=rep,
        similarity=0.9,
        by_venue=by_venue,
    )


def test_divergence_detects_high_gap() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "Fed cut May 2026", 0.62),
                "kalshi": _pm("kalshi", "k1", "Fed cut May 2026", 0.47),
                "manifold": _pm("manifold", "m1", "Fed cut May 2026", 0.55),
            }
        )
    ]
    alerts = detect_divergences(matched, gap_threshold=0.05)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.gap == pytest.approx(0.15)
    assert a.high[0] == "polymarket"
    assert a.low[0] == "kalshi"


def test_divergence_below_threshold_dropped() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "Fed cut May 2026", 0.50),
                "kalshi": _pm("kalshi", "k1", "Fed cut May 2026", 0.51),
            }
        )
    ]
    alerts = detect_divergences(matched, gap_threshold=0.05)
    assert alerts == []


def test_divergence_skips_when_only_one_venue_has_price() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "X ?", 0.62),
                "kalshi": _pm("kalshi", "k1", "X ?", None),
            }
        )
    ]
    assert detect_divergences(matched, gap_threshold=0.01) == []


def test_divergence_sorted_by_gap_desc() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "Q1 ?", 0.50),
                "kalshi": _pm("kalshi", "k1", "Q1 ?", 0.40),
            }
        ),
        _matched(
            {
                "polymarket": _pm("polymarket", "p2", "Q2 ?", 0.80),
                "kalshi": _pm("kalshi", "k2", "Q2 ?", 0.50),
            }
        ),
    ]
    alerts = detect_divergences(matched, gap_threshold=0.05)
    assert len(alerts) == 2
    assert alerts[0].gap > alerts[1].gap  # bigger gap first


def test_divergence_rejects_invalid_gap_threshold() -> None:
    with pytest.raises(ValueError):
        detect_divergences([], gap_threshold=-0.1)
    with pytest.raises(ValueError):
        detect_divergences([], gap_threshold=2.0)


# ─────────────────────────── End-to-end smoke ──────────────────────────


def test_end_to_end_three_venue_divergence_smoke() -> None:
    """Realistic Fed-cut scenario with prices reflecting the
    *Maduro-trade*-style decentralized vs regulated divergence."""
    poly = [_pm("polymarket", "p_fed", "Will Fed cut rates by May 2026 ?", 0.62)]
    kal = [_pm("kalshi", "k_fed", "Fed cuts rates May 2026", 0.47)]
    man = [_pm("manifold", "m_fed", "Fed rate cut 2026 May", 0.55)]
    matched = match_across_venues(poly, kal, man, threshold=0.5)
    alerts = detect_divergences(matched, gap_threshold=0.05)
    assert len(alerts) == 1
    assert isinstance(alerts[0], DivergenceAlert)
    assert alerts[0].gap >= 0.15
