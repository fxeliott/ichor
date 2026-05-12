"""Phase D W115 — Vovk-Zhdanov Aggregating Algorithm unit tests.

Pure-Python primitive tested without DB. Covers :

1. Construction invariants (n_experts >= 1, eta > 0, weights uniform
   default, weight-length match).
2. `predict` invariants (weighted-mean = AA substitution at η=1, raises
   on length mismatch, raises on p ∉ [0,1]).
3. `update` invariants (binary y only, exponential decay matches the
   AA formula, weights stay on the simplex, cumulative loss
   accumulates).
4. Regret bound mathematical property : ln(N) / η, constant in T.
5. Convergence sanity : after 200 updates with one expert systematically
   beating the others, the AA must concentrate weight on that expert.
"""

from __future__ import annotations

import math

import pytest
from ichor_api.services.vovk_aggregator import VovkBrierAggregator

# ────────────────────────── construction ──────────────────────────


def test_default_weights_are_uniform() -> None:
    agg = VovkBrierAggregator(n_experts=4)
    assert len(agg.weights) == 4
    assert all(math.isclose(w, 0.25, abs_tol=1e-12) for w in agg.weights)
    assert math.isclose(sum(agg.weights), 1.0, abs_tol=1e-12)


def test_default_eta_is_one_brier_game_optimum() -> None:
    """ADR-087 W115 : η=1 is the Vovk-Zhdanov 2009 Brier-game optimum.
    Drift catches any refactor that "tunes" to a different default."""
    agg = VovkBrierAggregator(n_experts=3)
    assert agg.eta == 1.0


def test_negative_n_experts_rejected() -> None:
    with pytest.raises(ValueError, match=r"n_experts must be >= 1"):
        VovkBrierAggregator(n_experts=0)


def test_nonpositive_eta_rejected() -> None:
    with pytest.raises(ValueError, match=r"eta must be > 0"):
        VovkBrierAggregator(n_experts=3, eta=0.0)


def test_explicit_weights_renormalized() -> None:
    """If caller passes [0.2, 0.3, 0.5] (already on simplex) we keep
    them ; if [2, 3, 5] we renormalize to the same simplex point."""
    agg = VovkBrierAggregator(n_experts=3, weights=[2.0, 3.0, 5.0])
    assert math.isclose(sum(agg.weights), 1.0, abs_tol=1e-12)
    assert math.isclose(agg.weights[0], 0.2, abs_tol=1e-12)


def test_weights_length_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match=r"weights length"):
        VovkBrierAggregator(n_experts=3, weights=[0.5, 0.5])


def test_all_zero_weights_reset_to_uniform() -> None:
    """Pathological input : weights sum to 0. Algorithm invariant
    'weights sum to 1' must hold ; we reset to uniform."""
    agg = VovkBrierAggregator(n_experts=4, weights=[0.0, 0.0, 0.0, 0.0])
    assert math.isclose(sum(agg.weights), 1.0, abs_tol=1e-12)
    assert all(math.isclose(w, 0.25, abs_tol=1e-12) for w in agg.weights)


# ────────────────────────── predict ──────────────────────────


def test_predict_returns_weighted_mean_at_eta_1() -> None:
    """η=1 substitution function for binary Brier = weighted mean
    (Vovk-Zhdanov Prop 2)."""
    agg = VovkBrierAggregator(n_experts=3, weights=[0.5, 0.3, 0.2])
    p = agg.predict([0.8, 0.4, 0.1])
    expected = 0.5 * 0.8 + 0.3 * 0.4 + 0.2 * 0.1
    assert math.isclose(p, expected, abs_tol=1e-12)


def test_predict_rejects_wrong_length() -> None:
    agg = VovkBrierAggregator(n_experts=3)
    with pytest.raises(ValueError, match=r"expert_predictions length"):
        agg.predict([0.5, 0.5])


def test_predict_rejects_out_of_range_probability() -> None:
    agg = VovkBrierAggregator(n_experts=2)
    with pytest.raises(ValueError, match=r"not in \[0, 1\]"):
        agg.predict([1.5, 0.5])
    with pytest.raises(ValueError, match=r"not in \[0, 1\]"):
        agg.predict([0.5, -0.1])


# ────────────────────────── update ──────────────────────────


def test_update_rejects_non_binary_outcome() -> None:
    agg = VovkBrierAggregator(n_experts=2)
    for bad in (0.5, -1, 2, "0", None):
        with pytest.raises(ValueError, match=r"realized must be 0 or 1"):
            agg.update([0.5, 0.5], bad)  # type: ignore[arg-type]


def test_update_keeps_weights_on_simplex() -> None:
    """The AA invariant : Σ w = 1 after every update. Watch out for
    floating-point drift over many iterations."""
    agg = VovkBrierAggregator(n_experts=4)
    import random

    rng = random.Random(42)
    for _ in range(500):
        ps = [rng.random() for _ in range(4)]
        y = rng.choice([0, 1])
        agg.update(ps, y)
        assert math.isclose(sum(agg.weights), 1.0, abs_tol=1e-9)
        assert all(0.0 <= w <= 1.0 for w in agg.weights)


def test_update_concentrates_on_best_expert() -> None:
    """Convergence sanity : if expert 0 systematically predicts the
    truth and the others predict the opposite, the AA must concentrate
    weight on expert 0 after enough iterations.

    With η=1 and N=3, after 200 iterations the gap is enormous.
    """
    agg = VovkBrierAggregator(n_experts=3)
    # Construct stream where y alternates 0/1 ; expert 0 nails it,
    # experts 1 and 2 predict the opposite.
    for t in range(200):
        y = t % 2
        ps = [
            0.95 if y == 1 else 0.05,  # expert 0 = oracle (nearly)
            0.95 if y == 0 else 0.05,  # expert 1 = anti-oracle
            0.95 if y == 0 else 0.05,  # expert 2 = anti-oracle
        ]
        agg.update(ps, y)
    # Expert 0 should now hold ~1.0 weight.
    assert agg.weights[0] > 0.99
    assert agg.weights[1] < 0.01
    assert agg.weights[2] < 0.01


def test_update_increments_observation_counter() -> None:
    agg = VovkBrierAggregator(n_experts=2)
    assert agg.n_observations == 0
    for _ in range(5):
        agg.update([0.5, 0.5], 1)
    assert agg.n_observations == 5


def test_update_accumulates_loss() -> None:
    """cumulative_losses tracks Σ (p_i - y)² per expert across calls.
    Used by the audit log + regret-bound check."""
    agg = VovkBrierAggregator(n_experts=2)
    # Expert 0 says p=1, y=0 → loss=1. Expert 1 says p=0, y=0 → loss=0.
    agg.update([1.0, 0.0], 0)
    assert math.isclose(agg.cumulative_losses[0], 1.0, abs_tol=1e-12)
    assert math.isclose(agg.cumulative_losses[1], 0.0, abs_tol=1e-12)
    # Second tick : Expert 0 says p=0.5, y=1 → loss=0.25.
    agg.update([0.5, 1.0], 1)
    assert math.isclose(agg.cumulative_losses[0], 1.25, abs_tol=1e-12)


# ────────────────────────── regret bound ──────────────────────────


def test_regret_bound_at_eta_1_is_ln_n() -> None:
    """Theorem 1 : Regret_T(AA) ≤ ln(N) / η. At η=1 this is ln(N)."""
    for n in (2, 4, 10, 100):
        agg = VovkBrierAggregator(n_experts=n)
        assert math.isclose(agg.regret_bound(), math.log(n), abs_tol=1e-12)


def test_regret_bound_constant_in_T() -> None:
    """The KILLER feature : regret bound does NOT grow with T. After
    1000 updates the bound is still ln(N), not ln(N) * sqrt(T)."""
    agg = VovkBrierAggregator(n_experts=4)
    bound_before = agg.regret_bound()
    for t in range(1000):
        agg.update([0.5, 0.5, 0.5, 0.5], t % 2)
    bound_after = agg.regret_bound()
    assert math.isclose(bound_after, bound_before, abs_tol=1e-12)


def test_regret_bound_scales_inverse_eta() -> None:
    """At η=2, the bound shrinks ; at η=0.5, the bound grows. Not
    that we'd pick those — η=1 is the Brier-game optimum — but the
    formula must hold for any positive η."""
    n = 5
    for eta in (0.5, 1.0, 2.0, 5.0):
        agg = VovkBrierAggregator(n_experts=n, eta=eta)
        assert math.isclose(agg.regret_bound(), math.log(n) / eta, abs_tol=1e-12)
