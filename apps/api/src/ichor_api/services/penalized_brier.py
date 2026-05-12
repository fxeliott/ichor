"""Phase D W116 — Penalized Brier Score variants (ADR-087).

Two distinct PBS-family functions, used by different code paths :

1. `ahmadian_pbs(p, realized)` — strict-proper scoring with the
   "superior ordering" guarantee : any correct prediction MUST score
   strictly better than any misclassification.
       PBS = Σ_k (p_k − 𝟙[k=c])² + λ · 𝟙[argmax(p) ≠ c]
   λ chosen to dominate the worst-case Brier swing, so the ordering
   property holds. Reference :
       Ahmadian, Ghatee, Wahlström. "Superior Scoring Rules for
       Probabilistic Evaluation of Single-Label Multi-Class
       Classification Tasks." Knowledge-Based Systems, 2025
       (arXiv:2407.17697).
   Usage : W116 post-mortem evaluator. Lower-is-better.

2. `climatology_penalty(p, p_climatology, lambda_pen)` — L2 distance
   to base rates, used as an anti-overconfidence regularizer when
   evaluating GENERATED prompt outputs (W117 GEPA fitness function).
   Different semantic from PBS : this is a soft pull-toward-prior, not
   a scoring rule.

Both are pure functions, no DB, no I/O — fully unit-testable.
"""

from __future__ import annotations


def brier_score_binary(p: float, realized: int) -> float:
    """Standard binary Brier score : (p - y)². Range [0, 1].

    Convenience wrapper for the W115 binary case ; callers can also
    construct the 2-vector and use `brier_score_multiclass` for
    consistency.
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p={p!r} not in [0, 1]")
    if realized not in (0, 1):
        raise ValueError(f"realized must be 0 or 1, got {realized!r}")
    return (p - realized) ** 2


def brier_score_multiclass(p: list[float], realized_index: int) -> float:
    """Multidimensional Brier (a.k.a. quadratic loss).

    `p` is the predicted probability vector over K classes (sums to 1).
    `realized_index` is the index of the realized class.

    BS = Σ_k (p_k − 𝟙[k = realized_index])². Range [0, 2] for proper
    probability vectors.
    """
    if not p:
        raise ValueError("p must be non-empty")
    if not 0 <= realized_index < len(p):
        raise ValueError(f"realized_index={realized_index!r} not in [0, {len(p)})")
    if abs(sum(p) - 1.0) > 1e-6:
        raise ValueError(f"p must sum to 1, got {sum(p):.6f}")
    if any(not 0.0 <= pk <= 1.0 for pk in p):
        raise ValueError("every p_k must be in [0, 1]")
    s = 0.0
    for k, pk in enumerate(p):
        y_k = 1.0 if k == realized_index else 0.0
        s += (pk - y_k) ** 2
    return s


def ahmadian_pbs(
    p: list[float],
    realized_index: int,
    *,
    misclassification_penalty: float = 2.0,
) -> float:
    """Penalized Brier Score with the Ahmadian-2025 superior-ordering
    property.

    Formula : `PBS = BrierScore(p, c) + λ · 𝟙[argmax(p) ≠ c]`.

    The penalty λ (default 2.0) is chosen to dominate the maximum
    possible Brier swing from a confidently wrong prediction
    (max Brier on K=2 = 1.0 ; max on K=7 = 2.0 for the W115/W116
    7-bucket case). Setting λ ≥ 2.0 guarantees that any misclassified
    prediction scores strictly worse than any correct prediction —
    Ahmadian's "superior" property.

    Strict-properness is preserved because the indicator term only
    fires on argmax disagreement, and argmax of a properly-scored
    forecast already aligns with the truth on a strict-proper scoring
    rule. The PBS thus inherits Brier's strict-properness while gaining
    the discrete ordering bonus.

    Returns a non-negative float, lower-is-better.
    """
    if misclassification_penalty < 0.0:
        raise ValueError(
            f"misclassification_penalty must be ≥ 0, got {misclassification_penalty!r}"
        )
    bs = brier_score_multiclass(p, realized_index)
    argmax_idx = max(range(len(p)), key=lambda i: p[i])
    miss = 0.0 if argmax_idx == realized_index else misclassification_penalty
    return bs + miss


def climatology_penalty(
    p: list[float],
    p_climatology: list[float],
    lambda_pen: float = 0.1,
) -> float:
    """Anti-overconfidence regularizer : L2² distance to base rates.

    Used by W117 GEPA fitness on prompt CANDIDATES — penalizes outputs
    that deviate too far from climatology unless they bring genuine
    signal (composed additively with Brier in the fitness aggregate).

    NOT a scoring rule on its own : this is a SOFT pull-toward-prior
    used as a regularizer. The Brier component remains the truth
    signal.

    Returns `lambda_pen · ||p - p_climatology||²₂`.
    """
    if len(p) != len(p_climatology):
        raise ValueError(f"len(p)={len(p)} != len(p_climatology)={len(p_climatology)}")
    if lambda_pen < 0.0:
        raise ValueError(f"lambda_pen must be ≥ 0, got {lambda_pen!r}")
    s = sum((a - b) ** 2 for a, b in zip(p, p_climatology, strict=True))
    return lambda_pen * s
