"""Unit tests for `services.brier_multiclass` — K=7 multi-class Brier."""

from __future__ import annotations

import pytest
from ichor_api.services.brier_multiclass import (
    BS_UNIFORM_PER_OBS,
    BrierScore,
    K,
    brier_climatology,
    brier_mean,
    brier_one,
    brier_persistence,
    climatology_frequencies,
    compute_brier_scoreboard,
    one_hot,
)
from ichor_brain.scenarios import BUCKET_LABELS

# ─────────────────────── invariants K + baseline ────────────────────────


def test_K_constant_pins_7() -> None:
    assert K == 7
    assert len(BUCKET_LABELS) == K


def test_uniform_baseline_per_obs_matches_analytic() -> None:
    # K=7 : 6/49 + 36/49 = 42/49 ≈ 0.8571 (sum-across-classes).
    expected = (K - 1) / (K * K) + ((K - 1) / K) ** 2
    assert BS_UNIFORM_PER_OBS == pytest.approx(expected, abs=1e-12)
    assert BS_UNIFORM_PER_OBS == pytest.approx(42 / 49, abs=1e-12)


# ─────────────────────── one_hot + brier_one ────────────────────────


def test_one_hot_position_matches_bucket_labels_order() -> None:
    for i, label in enumerate(BUCKET_LABELS):
        oh = one_hot(label)
        assert oh[i] == 1.0
        assert sum(oh) == 1.0
        for j, v in enumerate(oh):
            if j != i:
                assert v == 0.0


def test_brier_one_perfect_prediction_is_zero() -> None:
    # Perfect : prob 1.0 on realized bucket, 0 elsewhere → 0.
    for label in BUCKET_LABELS:
        probs = list(one_hot(label))
        assert brier_one(probs, label) == 0.0


def test_brier_one_completely_wrong_prediction_is_two() -> None:
    # Worst : prob 1.0 on wrong bucket, 0 on realized → 2.0 per obs.
    probs = list(one_hot("crash_flush"))
    assert brier_one(probs, "melt_up") == 2.0


def test_brier_one_uniform_prediction_matches_constant() -> None:
    # Uniform 1/7 prediction on any realized bucket → BS_UNIFORM_PER_OBS.
    probs = [1.0 / K] * K
    for label in BUCKET_LABELS:
        assert brier_one(probs, label) == pytest.approx(BS_UNIFORM_PER_OBS, abs=1e-12)


def test_brier_one_rejects_wrong_k() -> None:
    with pytest.raises(ValueError, match="needs 7 probs"):
        brier_one([0.5, 0.5], "base")


# ─────────────────────── brier_mean ───────────────────────


def test_brier_mean_empty_returns_zero() -> None:
    assert brier_mean([]) == 0.0


def test_brier_mean_perfect_predictions_is_zero() -> None:
    preds = [(list(one_hot(b)), b) for b in BUCKET_LABELS]
    assert brier_mean(preds) == 0.0


def test_brier_mean_uniform_predictions_matches_constant() -> None:
    preds = [([1.0 / K] * K, b) for b in BUCKET_LABELS]
    assert brier_mean(preds) == pytest.approx(BS_UNIFORM_PER_OBS, abs=1e-12)


# ─────────────────────── climatology ───────────────────────


def test_climatology_empty_falls_back_to_uniform() -> None:
    freq = climatology_frequencies([])
    assert freq == [1.0 / K] * K


def test_climatology_frequencies_in_canonical_order() -> None:
    realized = ["base", "base", "mild_bull", "base", "strong_bear"]
    freq = climatology_frequencies(realized)
    # base appears 3/5, mild_bull 1/5, strong_bear 1/5, rest 0.
    expected = {
        "crash_flush": 0.0,
        "strong_bear": 1 / 5,
        "mild_bear": 0.0,
        "base": 3 / 5,
        "mild_bull": 1 / 5,
        "strong_bull": 0.0,
        "melt_up": 0.0,
    }
    for i, label in enumerate(BUCKET_LABELS):
        assert freq[i] == pytest.approx(expected[label], abs=1e-12)


def test_brier_climatology_constant_distribution_is_zero() -> None:
    # All obs are "base" → climatology is all-mass-on-base → perfect
    # prediction on every obs → 0.
    realized = ["base"] * 50
    assert brier_climatology(realized) == 0.0


def test_brier_climatology_empty_falls_back_to_uniform() -> None:
    assert brier_climatology([]) == BS_UNIFORM_PER_OBS


# ─────────────────────── persistence ───────────────────────


def test_brier_persistence_constant_sequence_near_zero() -> None:
    # Single bucket throughout : t=0 uniform, t=1..n-1 perfect.
    # As n→∞ the uniform-on-t=0 term vanishes.
    realized = ["base"] * 252
    score = brier_persistence(realized)
    assert 0.0 < score < 0.01  # mostly perfect, with t=0 uniform


def test_brier_persistence_alternating_sequence_is_high() -> None:
    # Alternating buckets → persistence always wrong → 2.0 each (after t=0).
    realized = ["base", "strong_bull"] * 10
    score = brier_persistence(realized)
    assert score > 1.5  # roughly 2.0 except t=0 uniform contribution


def test_brier_persistence_short_sequence_falls_back_to_uniform() -> None:
    assert brier_persistence([]) == BS_UNIFORM_PER_OBS
    assert brier_persistence(["base"]) == BS_UNIFORM_PER_OBS


# ─────────────────────── BrierScore skill metrics ───────────────────────


def test_brier_score_skill_vs_uniform_zero_when_score_equals_uniform() -> None:
    s = BrierScore(n_obs=10, score=BS_UNIFORM_PER_OBS)
    assert s.skill_vs_uniform == pytest.approx(0.0)


def test_brier_score_skill_vs_uniform_positive_when_score_lower() -> None:
    s = BrierScore(n_obs=10, score=BS_UNIFORM_PER_OBS / 2)
    assert s.skill_vs_uniform == pytest.approx(0.5)


def test_brier_score_skill_vs_climatology_none_when_no_baseline() -> None:
    s = BrierScore(n_obs=10, score=0.5)
    assert s.skill_vs_climatology is None


def test_brier_score_skill_vs_climatology_present_when_baseline_set() -> None:
    s = BrierScore(n_obs=10, score=0.5, score_climatology=0.7)
    expected = 1.0 - 0.5 / 0.7
    assert s.skill_vs_climatology == pytest.approx(expected)


# ─────────────────────── compute_brier_scoreboard ───────────────────────


def test_scoreboard_all_baselines_present_when_data_sufficient() -> None:
    preds = [([1.0 / K] * K, b) for b in BUCKET_LABELS] * 4  # 28 obs
    sb = compute_brier_scoreboard(preds)
    assert sb.n_obs == 28
    assert sb.score_climatology is not None
    assert sb.score_persistence is not None
    assert sb.score_uniform == BS_UNIFORM_PER_OBS


def test_scoreboard_empty_predictions() -> None:
    sb = compute_brier_scoreboard([])
    assert sb.n_obs == 0
    assert sb.score == 0.0


# ─────────────────────── ADR-085 invariants ───────────────────────


def test_canonical_bucket_count_pinned_at_7() -> None:
    # Pin K against silent drift if BUCKET_LABELS is mutated.
    assert K == 7
    assert len(BUCKET_LABELS) == 7
    # All Brier functions should reject inputs of wrong K.
    with pytest.raises(ValueError):
        brier_one([1.0] * 6, "base")
    with pytest.raises(ValueError):
        brier_one([1.0] * 8, "base")
