"""Phase D W116 — Penalized Brier Score variants unit tests.

Pure-function module ; covers :

1. Binary Brier validation (p ∈ [0,1], y ∈ {0,1}).
2. Multiclass Brier sum + index validation + probability-vector
   sanity (sums to 1, components in [0,1]).
3. Ahmadian PBS superior-ordering property : the worst correct
   prediction must score ≤ the best misclassification when λ ≥ 2.
4. Strict-properness preserved : PBS at p = e_c is 0 (perfect score
   on the realized class).
5. Climatology penalty L2² distance behavior.
"""

from __future__ import annotations

import math

import pytest
from ichor_api.services.penalized_brier import (
    ahmadian_pbs,
    brier_score_binary,
    brier_score_multiclass,
    climatology_penalty,
)

# ────────────────────────── binary Brier ──────────────────────────


def test_brier_binary_perfect_zero() -> None:
    assert brier_score_binary(1.0, 1) == 0.0
    assert brier_score_binary(0.0, 0) == 0.0


def test_brier_binary_no_skill() -> None:
    assert math.isclose(brier_score_binary(0.5, 1), 0.25)
    assert math.isclose(brier_score_binary(0.5, 0), 0.25)


def test_brier_binary_rejects_p_out_of_range() -> None:
    with pytest.raises(ValueError, match=r"not in \[0, 1\]"):
        brier_score_binary(1.5, 1)


def test_brier_binary_rejects_non_binary_y() -> None:
    with pytest.raises(ValueError, match=r"realized must be 0 or 1"):
        brier_score_binary(0.5, 2)


# ────────────────────────── multiclass Brier ──────────────────────────


def test_brier_multiclass_perfect_zero() -> None:
    """p = e_c (one-hot on realized) → BS = 0."""
    p = [0.0, 0.0, 1.0, 0.0]
    assert brier_score_multiclass(p, realized_index=2) == 0.0


def test_brier_multiclass_uniform_k4_is_0_75() -> None:
    """Uniform over K=4 with truth at class 0 :
    Σ (1/4 − y_k)² = (3/4)² + 3·(1/4)² = 9/16 + 3/16 = 12/16 = 0.75."""
    p = [0.25, 0.25, 0.25, 0.25]
    assert math.isclose(brier_score_multiclass(p, 0), 0.75, abs_tol=1e-9)


def test_brier_multiclass_rejects_unnormalized() -> None:
    with pytest.raises(ValueError, match=r"must sum to 1"):
        brier_score_multiclass([0.3, 0.3, 0.3], 0)


def test_brier_multiclass_rejects_out_of_range_index() -> None:
    with pytest.raises(ValueError, match=r"realized_index="):
        brier_score_multiclass([0.5, 0.5], 5)


def test_brier_multiclass_rejects_empty() -> None:
    with pytest.raises(ValueError, match=r"must be non-empty"):
        brier_score_multiclass([], 0)


def test_brier_multiclass_rejects_negative_pk() -> None:
    with pytest.raises(ValueError, match=r"in \[0, 1\]"):
        brier_score_multiclass([-0.1, 1.1], 0)


# ────────────────────────── Ahmadian PBS ──────────────────────────


def test_pbs_correct_argmax_no_penalty() -> None:
    """When argmax(p) == realized, PBS == Brier (no penalty term)."""
    p = [0.7, 0.2, 0.1]
    bs = brier_score_multiclass(p, 0)
    pbs = ahmadian_pbs(p, 0)
    assert math.isclose(pbs, bs, abs_tol=1e-12)


def test_pbs_misclassification_adds_penalty() -> None:
    """Argmax disagreement adds exactly `misclassification_penalty`."""
    p = [0.1, 0.6, 0.3]  # argmax = 1
    pbs = ahmadian_pbs(p, realized_index=0, misclassification_penalty=2.0)
    bs = brier_score_multiclass(p, 0)
    assert math.isclose(pbs, bs + 2.0, abs_tol=1e-12)


def test_pbs_superior_ordering_property() -> None:
    """Ahmadian 2025 main theorem : ANY correct prediction scores
    strictly LOWER than ANY misclassification, at λ=2 for K=2 (Brier
    swing max = 1.0 < 2.0).

    Construct : a low-confidence correct prediction (bad Brier but
    correct argmax) MUST still beat a confident wrong one."""
    # Low-confidence correct : p=0.51 toward class 1, realized=1.
    # Brier = (0.51-1)² + (0.49-0)² ≈ 0.4802.
    p_correct = [0.49, 0.51]
    pbs_correct = ahmadian_pbs(p_correct, realized_index=1)
    # Confident wrong : p=0.99 toward class 0, realized=1.
    # Brier = (0.99-0)² + (0.01-1)² ≈ 1.9602, then +2 penalty.
    p_wrong = [0.99, 0.01]
    pbs_wrong = ahmadian_pbs(p_wrong, realized_index=1)
    assert pbs_correct < pbs_wrong


def test_pbs_strict_properness_at_oracle() -> None:
    """Perfect prediction (p = e_realized) scores 0 — strict-properness
    is preserved by the PBS construction."""
    p = [0.0, 0.0, 1.0, 0.0]
    assert ahmadian_pbs(p, realized_index=2) == 0.0


def test_pbs_rejects_negative_penalty() -> None:
    with pytest.raises(ValueError, match=r"misclassification_penalty"):
        ahmadian_pbs([0.5, 0.5], 0, misclassification_penalty=-1.0)


def test_pbs_lambda_zero_collapses_to_brier() -> None:
    """λ = 0 is degenerate : PBS == Brier, no superior ordering."""
    p = [0.3, 0.7]
    pbs = ahmadian_pbs(p, realized_index=0, misclassification_penalty=0.0)
    assert math.isclose(pbs, brier_score_multiclass(p, 0))


# ────────────────────────── ClimatologyPenalty ──────────────────────────


def test_climatology_penalty_zero_at_baseline() -> None:
    """If p == p_climatology, the penalty is 0 — no anti-overconfidence
    pull when the prediction is already at base rates."""
    p_clim = [0.4, 0.4, 0.2]
    assert climatology_penalty(p_clim, p_clim, lambda_pen=1.0) == 0.0


def test_climatology_penalty_grows_quadratic_in_distance() -> None:
    """For 2-class diagonal move : p = [0.7, 0.3], climatology
    [0.5, 0.5]. Distance² = (0.2)² + (-0.2)² = 0.08. λ = 0.5 →
    penalty = 0.04."""
    p = [0.7, 0.3]
    p_clim = [0.5, 0.5]
    assert math.isclose(
        climatology_penalty(p, p_clim, lambda_pen=0.5),
        0.04,
        abs_tol=1e-9,
    )


def test_climatology_penalty_rejects_negative_lambda() -> None:
    with pytest.raises(ValueError, match=r"lambda_pen"):
        climatology_penalty([0.5, 0.5], [0.5, 0.5], lambda_pen=-0.1)


def test_climatology_penalty_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match=r"!= len"):
        climatology_penalty([0.5, 0.5], [0.33, 0.33, 0.34])
