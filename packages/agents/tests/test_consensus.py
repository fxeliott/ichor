"""Pure tests for the cross-venue prediction-market consensus aggregator."""

from __future__ import annotations

import pytest
from ichor_agents.predictions import (
    VENUE_RELIABILITY,
    ConsensusEstimate,
    MatchedMarket,
    PredictionMarket,
    compute_consensus,
    match_across_venues,
)

# ─────────────────────────────── Helpers ───────────────────────────────


def _pm(venue, mid, question, price):
    return PredictionMarket(venue=venue, market_id=mid, question=question, yes_price=price)


def _matched(by_venue, rep=None):
    rep_q = rep if rep is not None else next(iter(by_venue.values())).question
    return MatchedMarket(representative_question=rep_q, similarity=0.9, by_venue=by_venue)


# ─────────────────────── Reliability-weighted fusion ────────────────────


def test_two_real_money_venues_equal_weight_mean() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "Fed cut May 2026", 0.60),
                "kalshi": _pm("kalshi", "k1", "Fed cut May 2026", 0.64),
            }
        )
    ]
    out = compute_consensus(matched)
    assert len(out) == 1
    c = out[0]
    assert c.consensus_prob == pytest.approx(0.62)  # equal-weight mean
    assert c.n_venues == 2
    assert c.dispersion == pytest.approx(0.04)
    assert c.confidence == "high"
    assert c.market_ids == {"polymarket": "p1", "kalshi": "k1"}


def test_manifold_play_money_barely_moves_consensus() -> None:
    """A wild Manifold price (0.20) only nudges a real-money agreement
    (both 0.60) because its weight is 0.15 — and never tanks confidence."""
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "Fed cut", 0.60),
                "kalshi": _pm("kalshi", "k1", "Fed cut", 0.60),
                "manifold": _pm("manifold", "m1", "Fed cut", 0.20),
            }
        )
    ]
    c = compute_consensus(matched)[0]
    # (1.0*0.60 + 1.0*0.60 + 0.15*0.20) / 2.15
    assert c.consensus_prob == pytest.approx(1.23 / 2.15)
    assert 0.56 < c.consensus_prob < 0.58  # far closer to 0.60 than 0.20
    assert c.n_venues == 3
    # dispersion = real-money spread (0.0), NOT the 0.40 manifold gap
    assert c.dispersion == pytest.approx(0.0)
    assert c.confidence == "high"


def test_dispersion_is_real_money_spread_not_all_venue() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "X", 0.60),
                "kalshi": _pm("kalshi", "k1", "X", 0.60),
                "manifold": _pm("manifold", "m1", "X", 0.10),
            }
        )
    ]
    c = compute_consensus(matched)[0]
    assert c.dispersion == pytest.approx(0.0)  # not 0.50
    assert c.confidence == "high"


def test_consensus_stays_in_unit_interval() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "X", 0.0),
                "kalshi": _pm("kalshi", "k1", "X", 1.0),
            }
        )
    ]
    c = compute_consensus(matched)[0]
    assert 0.0 <= c.consensus_prob <= 1.0
    assert c.consensus_prob == pytest.approx(0.5)


# ─────────────────── Malformed prices (NaN / inf / range) ───────────────


def test_nan_price_dropped_as_malformed() -> None:
    """A NaN venue price is treated as absent (upstream venues don't
    guarantee [0,1]); consensus stays finite + in [0,1]."""
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "X", float("nan")),
                "kalshi": _pm("kalshi", "k1", "X", 0.60),
                "manifold": _pm("manifold", "m1", "X", 0.50),
            }
        )
    ]
    c = compute_consensus(matched)[0]
    assert "polymarket" not in c.by_venue
    assert c.n_venues == 2
    assert 0.0 <= c.consensus_prob <= 1.0


def test_out_of_range_price_dropped() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "X", 1.5),  # > 1 = malformed
                "kalshi": _pm("kalshi", "k1", "X", 0.60),
                "manifold": _pm("manifold", "m1", "X", 0.50),
            }
        )
    ]
    c = compute_consensus(matched)[0]
    assert "polymarket" not in c.by_venue
    assert 0.0 <= c.consensus_prob <= 1.0


def test_inf_and_negative_prices_dropped() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "X", float("inf")),
                "kalshi": _pm("kalshi", "k1", "X", -0.2),  # < 0 = malformed
            }
        )
    ]
    # Both legs malformed → nothing to fuse → skipped honestly.
    assert compute_consensus(matched) == []


# ─────────────────────────── min_venues gating ─────────────────────────


def test_skips_when_only_one_venue_priced() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "X", 0.62),
                "kalshi": _pm("kalshi", "k1", "X", None),
            }
        )
    ]
    assert compute_consensus(matched) == []


def test_only_priced_venues_appear_in_by_venue() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "X", 0.62),
                "kalshi": _pm("kalshi", "k1", "X", 0.58),
                "manifold": _pm("manifold", "m1", "X", None),
            }
        )
    ]
    c = compute_consensus(matched)[0]
    assert set(c.by_venue.keys()) == {"polymarket", "kalshi"}
    assert "manifold" not in c.market_ids


def test_empty_input_empty_output() -> None:
    assert compute_consensus([]) == []


def test_min_venues_invalid_raises() -> None:
    with pytest.raises(ValueError):
        compute_consensus([], min_venues=0)


# ─────────────────────────── Confidence grading ────────────────────────


def test_high_confidence_two_real_money_tight() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p", "X", 0.60),
                "kalshi": _pm("kalshi", "k", "X", 0.62),
            }
        )
    ]
    assert compute_consensus(matched)[0].confidence == "high"


def test_medium_confidence_real_money_midrange_spread() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p", "X", 0.62),
                "kalshi": _pm("kalshi", "k", "X", 0.50),
            }
        )
    ]
    c = compute_consensus(matched)[0]
    assert c.dispersion == pytest.approx(0.12)
    assert c.confidence == "medium"


def test_low_confidence_wide_real_money_spread() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p", "X", 0.70),
                "kalshi": _pm("kalshi", "k", "X", 0.50),
            }
        )
    ]
    assert compute_consensus(matched)[0].confidence == "low"


def test_low_confidence_single_real_money_plus_manifold() -> None:
    """One real-money anchor + play-money second leg → weak prior."""
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p", "X", 0.60),
                "manifold": _pm("manifold", "m", "X", 0.40),
            }
        )
    ]
    c = compute_consensus(matched)[0]
    assert c.confidence == "low"
    assert c.dispersion == pytest.approx(0.20)  # full spread when <2 real-money


def test_low_confidence_kalshi_manifold_orphan() -> None:
    matched = [
        _matched(
            {"kalshi": _pm("kalshi", "k", "X", 0.45), "manifold": _pm("manifold", "m", "X", 0.40)}
        )
    ]
    assert compute_consensus(matched)[0].confidence == "low"


# ─────────────────────────────── Sorting ───────────────────────────────


def test_sorted_by_confidence_then_dispersion() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p_lo", "low one", 0.70),
                "kalshi": _pm("kalshi", "k_lo", "low one", 0.50),
            }
        ),  # low
        _matched(
            {
                "polymarket": _pm("polymarket", "p_hi", "high one", 0.60),
                "kalshi": _pm("kalshi", "k_hi", "high one", 0.62),
            }
        ),  # high
        _matched(
            {
                "polymarket": _pm("polymarket", "p_md", "mid one", 0.62),
                "kalshi": _pm("kalshi", "k_md", "mid one", 0.50),
            }
        ),  # medium
    ]
    out = compute_consensus(matched)
    assert [c.confidence for c in out] == ["high", "medium", "low"]


def test_two_high_sorted_by_dispersion_ascending() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p1", "wider", 0.60),
                "kalshi": _pm("kalshi", "k1", "wider", 0.66),
            }
        ),  # spread 0.06
        _matched(
            {
                "polymarket": _pm("polymarket", "p2", "tighter", 0.60),
                "kalshi": _pm("kalshi", "k2", "tighter", 0.61),
            }
        ),  # spread 0.01
    ]
    out = compute_consensus(matched)
    assert out[0].representative_question == "tighter"
    assert out[1].representative_question == "wider"


# ─────────────────────────── Reliability override ──────────────────────


def test_reliability_override_zeroes_a_venue() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p", "X", 0.60),
                "kalshi": _pm("kalshi", "k", "X", 0.40),
            }
        )
    ]
    out = compute_consensus(
        matched, reliability={"polymarket": 1.0, "kalshi": 0.0, "manifold": 0.0}
    )
    assert out[0].consensus_prob == pytest.approx(0.60)  # kalshi zero-weighted


def test_all_zero_weight_skipped() -> None:
    matched = [
        _matched(
            {
                "polymarket": _pm("polymarket", "p", "X", 0.60),
                "kalshi": _pm("kalshi", "k", "X", 0.40),
            }
        )
    ]
    out = compute_consensus(
        matched, reliability={"polymarket": 0.0, "kalshi": 0.0, "manifold": 0.0}
    )
    assert out == []


def test_default_reliability_table_values() -> None:
    assert VENUE_RELIABILITY["polymarket"] == 1.0
    assert VENUE_RELIABILITY["kalshi"] == 1.0
    assert VENUE_RELIABILITY["manifold"] < 0.5  # play-money discounted


# ─────────────────────────────── End-to-end ────────────────────────────


def test_end_to_end_matcher_then_consensus() -> None:
    poly = [_pm("polymarket", "p_fed", "Will Fed cut rates by May 2026 ?", 0.62)]
    kal = [_pm("kalshi", "k_fed", "Fed rate cut by May 2026 ?", 0.58)]
    man = [_pm("manifold", "m_fed", "Fed cut rates in May 2026", 0.55)]
    matched = match_across_venues(poly, kal, man, threshold=0.5)
    out = compute_consensus(matched)
    assert len(out) == 1
    c = out[0]
    assert isinstance(c, ConsensusEstimate)
    assert c.n_venues == 3
    assert c.confidence == "high"  # poly 0.62 / kalshi 0.58 → spread 0.04
    assert 0.55 < c.consensus_prob < 0.62
