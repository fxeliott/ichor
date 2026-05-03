"""Pure-function tests for the Brier reconciliation service.

No DB / no I/O. Tests the math + edge cases.
"""

from __future__ import annotations

import math

import pytest

from ichor_api.services.brier import (
    brier_score,
    conviction_to_p_up,
    realized_direction,
    reconcile_card,
    reliability_buckets,
    summarize,
)


# ────────────────────────── conviction_to_p_up ─────────────────────────


def test_conviction_to_p_up_long_at_max() -> None:
    # 95 conviction long → 0.5 + 0.5 * 0.95 = 0.975
    assert conviction_to_p_up("long", 95) == pytest.approx(0.975)


def test_conviction_to_p_up_short_at_max() -> None:
    assert conviction_to_p_up("short", 95) == pytest.approx(0.025)


def test_conviction_to_p_up_neutral_always_50() -> None:
    for c in (0, 25, 50, 75, 95):
        assert conviction_to_p_up("neutral", c) == 0.5


def test_conviction_to_p_up_clamps_above_95() -> None:
    # The LLM should never emit > 95 (capped at parse), but defend anyway.
    assert conviction_to_p_up("long", 200) == pytest.approx(0.975)


def test_conviction_to_p_up_clamps_below_zero() -> None:
    assert conviction_to_p_up("long", -10) == 0.5


def test_conviction_to_p_up_at_zero_is_50() -> None:
    # No conviction = no informational content
    assert conviction_to_p_up("long", 0) == 0.5
    assert conviction_to_p_up("short", 0) == 0.5


# ─────────────────────────── realized_direction ────────────────────────


def test_realized_direction_up() -> None:
    assert realized_direction(open_px=1.0723, close_px=1.0801) == 1


def test_realized_direction_down() -> None:
    assert realized_direction(open_px=1.0801, close_px=1.0723) == 0


def test_realized_direction_flat_resolves_to_zero() -> None:
    assert realized_direction(open_px=1.0750, close_px=1.0750) == 0


# ─────────────────────────── brier_score ───────────────────────────────


def test_brier_perfect_long() -> None:
    # forecast 0.9, realized 1 → (0.9-1)^2 = 0.01
    assert brier_score(0.9, 1) == pytest.approx(0.01)


def test_brier_perfect_short() -> None:
    # forecast 0.1, realized 0 → (0.1-0)^2 = 0.01
    assert brier_score(0.1, 0) == pytest.approx(0.01)


def test_brier_no_skill_at_50() -> None:
    assert brier_score(0.5, 1) == pytest.approx(0.25)
    assert brier_score(0.5, 0) == pytest.approx(0.25)


def test_brier_anti_perfect() -> None:
    # forecast 0.99 long but realized down → near-1 Brier
    assert brier_score(0.99, 0) == pytest.approx(0.9801)


def test_brier_rejects_invalid_outcome() -> None:
    with pytest.raises(ValueError):
        brier_score(0.5, 2)


def test_brier_rejects_invalid_probability() -> None:
    with pytest.raises(ValueError):
        brier_score(1.5, 0)


# ─────────────────────────── reconcile_card ────────────────────────────


def test_reconcile_card_long_correct() -> None:
    out = reconcile_card(
        bias_direction="long",
        conviction_pct=80,
        open_px=1.0723,
        close_px=1.0801,
        high_px=1.0820,
        low_px=1.0712,
    )
    assert out.realized_outcome == 1
    assert out.p_up == pytest.approx(0.9)
    assert out.brier_contribution == pytest.approx(0.01)
    assert out.realized_close_session == 1.0801


def test_reconcile_card_short_wrong() -> None:
    """Short bias 80 % conviction but realized went up → Brier = 0.81."""
    out = reconcile_card(
        bias_direction="short",
        conviction_pct=80,
        open_px=1.0723,
        close_px=1.0801,
        high_px=1.0820,
        low_px=1.0712,
    )
    assert out.realized_outcome == 1
    assert out.p_up == pytest.approx(0.1)
    assert out.brier_contribution == pytest.approx(0.81)


# ─────────────────────────── summarize ─────────────────────────────────


def test_summarize_empty_returns_zero_summary() -> None:
    s = summarize([], [])
    assert s.n_cards == 0
    assert s.mean_brier == 0.0
    assert s.skill_vs_naive == 0.0


def test_summarize_basic_counts_hits() -> None:
    s = summarize(brier_contributions=[0.01, 0.04, 0.81], outcomes=[1, 1, 0])
    assert s.n_cards == 3
    assert s.hits == 2
    assert s.misses == 1
    assert s.mean_brier == pytest.approx((0.01 + 0.04 + 0.81) / 3)


def test_summarize_skill_score_positive_when_beats_naive() -> None:
    # mean Brier 0.05 → skill 1 - 0.05/0.25 = 0.8
    s = summarize(brier_contributions=[0.05] * 10, outcomes=[1] * 10)
    assert s.skill_vs_naive == pytest.approx(0.8)


def test_summarize_skill_score_negative_when_worse_than_naive() -> None:
    # mean Brier 0.5 → skill 1 - 0.5/0.25 = -1
    s = summarize(brier_contributions=[0.5] * 4, outcomes=[0] * 4)
    assert s.skill_vs_naive == pytest.approx(-1.0)


def test_summarize_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        summarize([0.1], [1, 0])


# ────────────────────────── reliability_buckets ────────────────────────


def test_reliability_buckets_empty_input() -> None:
    assert reliability_buckets([], [], n_bins=10) == []


def test_reliability_buckets_perfectly_calibrated() -> None:
    """When p exactly matches y per bucket, predicted == realized."""
    p_ups = [0.05, 0.05, 0.55, 0.55, 0.95, 0.95]
    ys = [0, 0, 1, 0, 1, 1]
    bins = reliability_buckets(p_ups, ys, n_bins=10)
    # Get bin containing 0.05, 0.55, 0.95
    for b in bins:
        assert 0.0 <= b.mean_predicted <= 1.0
        assert 0.0 <= b.mean_realized <= 1.0
    # 95% bin → 2 forecasts both up = mean_realized 1.0
    nineties = [b for b in bins if 0.9 <= b.bin_lower < 1.0]
    assert len(nineties) == 1
    assert nineties[0].count == 2
    assert nineties[0].mean_realized == pytest.approx(1.0)


def test_reliability_buckets_drops_empty_bins() -> None:
    bins = reliability_buckets([0.1, 0.9], [0, 1], n_bins=10)
    assert len(bins) == 2  # only 2 of 10 buckets populated


def test_reliability_buckets_p_one_lands_in_last_bin() -> None:
    bins = reliability_buckets([1.0], [1], n_bins=10)
    assert len(bins) == 1
    assert bins[0].bin_upper == 1.0


def test_reliability_buckets_rejects_too_few_bins() -> None:
    with pytest.raises(ValueError):
        reliability_buckets([0.5], [1], n_bins=1)


def test_reliability_buckets_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        reliability_buckets([0.5, 0.6], [1], n_bins=10)
