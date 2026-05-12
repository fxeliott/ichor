"""Brier multi-class K=7 scoring + skill vs 3 baselines.

Pure-Python compute layer for W105g reconciler. Per ADR-085 §"Brier
scoring — multi-class adaptation" + W105 researcher 2026-05-12 review.

Formula (Murphy 1973, multi-class K=7) :

    BS = (1/N) · Σ_t  Σ_c  (p_{t,c} − y_{t,c})²

where :
- `p_{t,c}` is the probability the model emitted for bucket c at obs t.
- `y_{t,c}` is the one-hot realized outcome (1 if bucket c realized, 0 else).
- Σ_c sums over the 7 canonical buckets — score range per obs : [0, 2].
- Lower is better.

Three baselines tracked :
- **Uniform** : `p_c = 1/7 ∀ c`. Score per obs = 6/49 ≈ 0.1224. Constant.
- **Climatology** : `p_c = empirical_frequency_c` on the rolling 252d
  history per (asset, session_type). Adapts to per-asset distribution
  reality (most assets have ~70% base+mild bins, ~3% tails).
- **Persistence** : `p_c = 1 if c == bucket_{t-1} else 0`. Each obs
  scores either 0 (correct) or 2 (wrong by one slot or more) — naive
  but very hard to beat in mean-reverting intraday FX.

Skill Score :

    BSS = 1 − BS_model / BS_baseline

`BSS > 0` ⇔ the model is better than the baseline. Realistic target
for Ichor Pass-6 on FX/index intraday (researcher web review 2026) :
`BSS vs climatology ∈ [0.02, 0.05]` is honest value-add ; expecting
0.15+ is meteorology-level optimism — never reached on financial
markets.

Pure functions — no DB, no I/O. The W105g reconciler reads
`session_card_audit` rows + `polygon_intraday` close prices, computes
realized z-scores → `bucket_for_zscore` → one-hot, then calls these
functions to produce the scoreboard payload that powers the
`/calibration` page extension (W105h).
"""

from __future__ import annotations

from dataclasses import dataclass

from ichor_brain.scenarios import BUCKET_LABELS, BucketLabel

# Multi-class K=7 ; constant for the entire module.
K: int = 7

# Uniform baseline score per observation (analytic) :
# Σ_c (1/K − y_c)² where exactly one y_c = 1, others = 0.
# = (1/K)² · (K-1) + ((1/K) − 1)² · 1
# = (K-1)/K² + ((K-1)/K)²
# For K=7 : 6/49 + 36/49 = 42/49 ≈ 0.8571 (sum-across-classes
# convention) OR 6/49 ≈ 0.1224 (mean-per-class convention).
# We use **sum-across-classes** = the standard Murphy 1973 convention.
BS_UNIFORM_PER_OBS: float = (K - 1) / (K * K) + ((K - 1) / K) ** 2  # 42/49


@dataclass(frozen=True)
class BrierScore:
    """Mean Brier score across N observations + decomposition."""

    n_obs: int
    score: float
    """Sum-across-classes mean : (1/N) · Σ_t Σ_c (p_c − y_c)². Lower better."""

    score_uniform: float = BS_UNIFORM_PER_OBS
    """Constant baseline 42/49 ≈ 0.8571."""

    score_climatology: float | None = None
    """Per-asset/session climatology baseline. Populated when caller
    provides the climatology frequencies."""

    score_persistence: float | None = None
    """Persistence (one-hot last bucket) baseline."""

    @property
    def skill_vs_uniform(self) -> float:
        """BSS = 1 − BS / BS_uniform. Positive = better than uniform."""
        if self.score_uniform <= 0.0:
            return 0.0
        return 1.0 - self.score / self.score_uniform

    @property
    def skill_vs_climatology(self) -> float | None:
        """Most informative skill metric for Ichor — beating the
        per-asset empirical distribution is the real test of Pass-6
        value-add. None if no climatology computed."""
        if self.score_climatology is None or self.score_climatology <= 0.0:
            return None
        return 1.0 - self.score / self.score_climatology

    @property
    def skill_vs_persistence(self) -> float | None:
        if self.score_persistence is None or self.score_persistence <= 0.0:
            return None
        return 1.0 - self.score / self.score_persistence


def one_hot(bucket: BucketLabel) -> tuple[float, ...]:
    """Map a canonical bucket label to a one-hot 7-vector in
    BUCKET_LABELS order."""
    return tuple(1.0 if label == bucket else 0.0 for label in BUCKET_LABELS)


def brier_one(probs: list[float], realized: BucketLabel) -> float:
    """Single-observation multi-class Brier : Σ_c (p_c − y_c)²."""
    if len(probs) != K:
        raise ValueError(f"brier_one needs {K} probs, got {len(probs)}")
    y = one_hot(realized)
    return sum((p - yc) ** 2 for p, yc in zip(probs, y, strict=True))


def brier_mean(predictions: list[tuple[list[float], BucketLabel]]) -> float:
    """Mean Brier across N observations.

    `predictions` is a list of (probs_7, realized_bucket) pairs. The
    function tolerates probs that don't quite sum to 1 (defence in
    depth — `cap_and_normalize` runs upstream) but the caller is
    expected to enforce the contract.
    """
    if not predictions:
        return 0.0
    total = sum(brier_one(probs, realized) for probs, realized in predictions)
    return total / len(predictions)


def climatology_frequencies(realized_buckets: list[BucketLabel]) -> list[float]:
    """Empirical bucket frequencies in BUCKET_LABELS order. Returns the
    uniform 1/7 when input is empty (cold-start)."""
    if not realized_buckets:
        return [1.0 / K for _ in range(K)]
    counts = dict.fromkeys(BUCKET_LABELS, 0)
    for b in realized_buckets:
        counts[b] += 1
    n = len(realized_buckets)
    return [counts[label] / n for label in BUCKET_LABELS]


def brier_climatology(realized_buckets: list[BucketLabel]) -> float:
    """Per-asset/session climatology baseline. Each observation receives
    the same probability vector = empirical frequencies."""
    if not realized_buckets:
        return BS_UNIFORM_PER_OBS
    clim = climatology_frequencies(realized_buckets)
    total = sum(brier_one(clim, realized) for realized in realized_buckets)
    return total / len(realized_buckets)


def brier_persistence(realized_buckets: list[BucketLabel]) -> float:
    """Persistence baseline : at each obs t ≥ 1, predict obs_{t-1}. Obs
    t=0 has no prior so it's predicted with uniform — fair handling."""
    n = len(realized_buckets)
    if n < 2:
        return BS_UNIFORM_PER_OBS
    total = 0.0
    # t=0 : uniform prior.
    total += brier_one([1.0 / K] * K, realized_buckets[0])
    # t=1..n-1 : one-hot persistence.
    for t in range(1, n):
        prev = realized_buckets[t - 1]
        probs = list(one_hot(prev))
        total += brier_one(probs, realized_buckets[t])
    return total / n


def compute_brier_scoreboard(
    predictions: list[tuple[list[float], BucketLabel]],
) -> BrierScore:
    """All-in-one scoreboard : the 4 baselines + the model score for a
    list of (probs, realized) observations.

    Designed for the W105g reconciler endpoint that aggregates one
    BrierScore per (asset, session_type) on a rolling 90d window.
    """
    realized = [r for _, r in predictions]
    return BrierScore(
        n_obs=len(predictions),
        score=brier_mean(predictions),
        score_climatology=brier_climatology(realized),
        score_persistence=brier_persistence(realized),
    )
