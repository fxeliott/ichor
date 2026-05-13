"""Unit tests for services/gepa_optimizer.py (W117b.c skeleton, round-36).

Tests cover the 3 ADR-091 invariants enforced by the skeleton :
  1. §Invariant 1 — Budget enforcement (hard cap 100, monotonic
     consume, BudgetExhausted contract).
  2. §Invariant 2 amended r32 — HARD-ZERO fitness gate
     (count_violations > 0 → -inf, else brier_skill).
  3. DSPy GEPA metric callback shape (ScoreWithFeedback TypedDict).

NO actual LLM call. NO `dspy.GEPA(...)` invocation. Skeleton-only
structural tests.
"""

from __future__ import annotations

import pytest
from ichor_api.services.gepa_optimizer import (
    _GEPA_BUDGET_HARD_CAP,
    BudgetExhausted,
    GepaRunBudget,
    GepaRunContext,
    compute_fitness_with_hard_zero,
    ichor_gepa_metric,
)

# ──────────────────────── §Invariant 1 budget ────────────────────────


def test_budget_hard_cap_constant_is_100() -> None:
    """ADR-091 §Invariant 1 : the hard cap is 100. Catches a future
    refactor that bumps it without an ADR."""
    assert _GEPA_BUDGET_HARD_CAP == 100


def test_budget_constructor_rejects_exceeding_hard_cap() -> None:
    """A run cannot ASK for more than the hard cap."""
    with pytest.raises(ValueError, match="exceeds the ADR-091"):
        GepaRunBudget(max_lm_calls=101)


def test_budget_constructor_rejects_zero_or_negative() -> None:
    with pytest.raises(ValueError, match="must be >= 1"):
        GepaRunBudget(max_lm_calls=0)
    with pytest.raises(ValueError, match="must be >= 1"):
        GepaRunBudget(max_lm_calls=-5)


def test_budget_constructor_rejects_negative_calls_used() -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        GepaRunBudget(max_lm_calls=100, calls_used=-1)


def test_budget_consume_increments_calls_used() -> None:
    budget = GepaRunBudget(max_lm_calls=10)
    assert budget.calls_used == 0
    budget.consume(1)
    assert budget.calls_used == 1
    budget.consume(3)
    assert budget.calls_used == 4


def test_budget_consume_raises_on_exhaustion() -> None:
    """ADR-091 §Invariant 1 contract : raise BudgetExhausted past cap.
    The optimizer's run loop catches this + exits gracefully."""
    budget = GepaRunBudget(max_lm_calls=5)
    budget.consume(4)
    with pytest.raises(BudgetExhausted, match="GEPA budget exhausted"):
        budget.consume(2)  # 4 + 2 = 6 > 5 → raise


def test_budget_consume_at_exact_cap_succeeds() -> None:
    """Consume that brings calls_used == max_lm_calls is OK (not >)."""
    budget = GepaRunBudget(max_lm_calls=10)
    budget.consume(10)
    assert budget.calls_used == 10
    # Next consume must raise
    with pytest.raises(BudgetExhausted):
        budget.consume(1)


def test_budget_consume_rejects_non_positive_n() -> None:
    budget = GepaRunBudget(max_lm_calls=10)
    with pytest.raises(ValueError, match="n >= 1"):
        budget.consume(0)
    with pytest.raises(ValueError, match="n >= 1"):
        budget.consume(-1)


def test_budget_remaining_property() -> None:
    budget = GepaRunBudget(max_lm_calls=100)
    assert budget.remaining == 100
    budget.consume(30)
    assert budget.remaining == 70


# ──────────────────────── §Invariant 2 hard-zero fitness ─────────────


def test_fitness_clean_output_returns_brier_skill() -> None:
    """No ADR-017 violation → fitness equals brier_skill as-is."""
    fitness = compute_fitness_with_hard_zero(
        brier_skill=0.42,
        candidate_output="Pocket EUR_USD/usd_complacency anti-skill : steelman should consider Fed put expectations.",
    )
    assert fitness == 0.42


def test_fitness_buy_token_returns_neg_inf() -> None:
    """ADR-017 bare imperative → hard-zero."""
    fitness = compute_fitness_with_hard_zero(
        brier_skill=0.9,  # high skill should NOT save a tainted candidate
        candidate_output="Consider BUY pressure on EUR.",
    )
    assert fitness == float("-inf")


def test_fitness_full_width_unicode_returns_neg_inf() -> None:
    """r32 Unicode hardening : full-width 'ＢＵＹ' caught."""
    fitness = compute_fitness_with_hard_zero(
        brier_skill=0.8,
        candidate_output="Steelman: ＢＵＹ EUR aggressively.",
    )
    assert fitness == float("-inf")


def test_fitness_multilingual_imperative_returns_neg_inf() -> None:
    """r32 multilingual hardening : French 'acheter' caught."""
    fitness = compute_fitness_with_hard_zero(
        brier_skill=0.6,
        candidate_output="Il faut acheter EUR maintenant.",
    )
    assert fitness == float("-inf")


def test_fitness_negative_brier_skill_passes_through_when_clean() -> None:
    """A clean output with negative brier_skill (worse than baseline)
    returns the negative skill — only ADR-017 violations force -inf."""
    fitness = compute_fitness_with_hard_zero(
        brier_skill=-0.05,  # anti-skill but clean text
        candidate_output="Macro-only narrative without trade tokens.",
    )
    assert fitness == -0.05


# ──────────────────────── DSPy metric callback shape ────────────────


def test_metric_callback_returns_score_with_feedback() -> None:
    """Verify the DSPy 3.2.1 GEPA metric contract :
    `metric(gold, pred, trace, pred_name, pred_trace) -> ScoreWithFeedback`."""
    result = ichor_gepa_metric(
        gold={"realized_bucket": "base"},
        pred={"bucket_probabilities": {"base": 0.4}},
        trace=None,
        pred_name="pass_regime",
        pred_trace=None,
    )
    assert isinstance(result, dict)
    assert "score" in result
    assert "feedback" in result
    assert isinstance(result["score"], float)
    assert isinstance(result["feedback"], str)


def test_metric_callback_handles_none_prediction() -> None:
    """Skeleton resilience : `pred=None` returns no-prediction feedback."""
    result = ichor_gepa_metric(gold={}, pred=None)
    assert result["score"] == 0.0
    assert "no prediction" in result["feedback"]


def test_metric_callback_skeleton_feedback_mentions_w117b_d() -> None:
    """Skeleton documentation contract : the feedback must announce
    the next sub-wave that wires actual scoring."""
    result = ichor_gepa_metric(
        gold={"realized_bucket": "mild_bull"},
        pred={"bucket_probabilities": {"mild_bull": 0.5}},
    )
    assert "W117b.d" in result["feedback"]
    assert "ahmadian_pbs" in result["feedback"]


# ──────────────────────── GepaRunContext skeleton ────────────────────


def test_run_context_default_pass_kind_is_regime() -> None:
    ctx = GepaRunContext(
        gepa_run_id="test-uuid",
        budget=GepaRunBudget(max_lm_calls=100),
    )
    assert ctx.pass_kind == "regime"


def test_run_context_tracks_promotion_counts() -> None:
    """Skeleton invariants : counters start at 0."""
    ctx = GepaRunContext(
        gepa_run_id="test-uuid",
        budget=GepaRunBudget(max_lm_calls=50),
    )
    assert ctx.candidates_emitted == 0
    assert ctx.candidates_rejected_adr017 == 0
    assert ctx.candidates_promoted == 0
    assert ctx.notes == []


# ──────────────────────── ADR-017 hard-zero invariant ────────────────


def test_hard_zero_dominates_any_finite_brier_skill() -> None:
    """Property : for any finite brier_skill, a violating output
    always returns -inf. Catches a refactor that adds a soft-lambda
    cushion (which was the original ADR-091 reading, REJECTED r32
    amendment)."""
    for skill in (-10.0, -0.5, 0.0, 0.1, 0.5, 0.9, 100.0):
        assert compute_fitness_with_hard_zero(skill, "BUY EUR now") == float("-inf"), (
            f"Soft-lambda regression detected at brier_skill={skill} — "
            "the optimizer would be able to promote tainted candidates."
        )


def test_hard_zero_pareto_safety() -> None:
    """If the GEPA optimizer's Pareto frontier sorts by fitness, -inf
    candidates always sit at the bottom → never promoted. Verify
    `compute_fitness_with_hard_zero` returns a strict `-inf` (not a
    finite floor like -1e10) so the Pareto sort behavior is correct."""
    violating = compute_fitness_with_hard_zero(0.9, "TARGET 1.0850 confluent")
    clean = compute_fitness_with_hard_zero(0.001, "Clean narrative")
    assert violating == float("-inf")
    assert violating < clean  # always true via -inf
    # Verify it's actually float infinity (not a sentinel int)
    import math

    assert math.isinf(violating)
    assert violating < 0  # negative infinity specifically
