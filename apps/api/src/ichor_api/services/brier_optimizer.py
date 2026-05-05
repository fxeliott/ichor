"""Brier→weights optimizer — projected SGD on confluence weights.

Per AUTOEVO §2 + ADR-021:
  - Algo: online SGD projected onto simplex {w >= 0.05, sum(w) = 1, w <= 0.5}
  - Loss: Brier = (predicted - outcome)^2 averaged over recent obs
  - Update: w_{t+1} = project(w_t - lr * grad(Brier))
  - Guards: lr=0.05 with momentum 0.9, sanity check |sum-1|<0.01

Holdout protocol:
  - Run optimizer over (current_weights, recent_obs).
  - Persist proposed weights to `brier_optimizer_runs` with adopted=False.
  - 21-day holdout starts; if Brier_after on holdout < Brier_before by ≥
    MDE 0.02, flip to adopted=True + write a new active row to
    `confluence_weights_history`.

This V1 does NOT fit the holdout flow itself (that's the
`scripts/hetzner/run_brier_optimizer.py` cron) — it provides the math
primitives and DB writers.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

# Bounds per SPEC §3.7.
WEIGHT_MIN = 0.05
WEIGHT_MAX = 0.5

DEFAULT_LR = 0.05
DEFAULT_MOMENTUM = 0.9


@dataclass(frozen=True)
class OptimizationResult:
    """One pass of the optimizer."""

    weights_proposed: dict[str, float]
    n_obs: int
    brier_before: float
    brier_after: float
    delta: float
    """Negative = improvement (Brier lower is better)."""

    converged: bool


def project_simplex_bounded(
    w: np.ndarray, *, w_min: float = WEIGHT_MIN, w_max: float = WEIGHT_MAX
) -> np.ndarray:
    """Project onto {w_min <= w <= w_max, sum(w) = 1} via clip + iterative renorm.

    Cf Duchi et al. 2008. We don't run the exact O(n log n) projection
    because n (~5-12 weights) is tiny — clip+renorm converges in 2-3
    iterations.

    Raises ValueError on infeasible bounds: `n * w_min > 1` (no vector
    can both satisfy each w >= w_min AND sum to 1) or `n * w_max < 1`.
    """
    w = np.asarray(w, dtype=np.float64).copy()
    n = len(w)
    if n == 0:
        return w
    if n * w_min > 1.0 + 1e-9:
        raise ValueError(f"infeasible bounds: n={n} * w_min={w_min} > 1 — sum cannot reach 1")
    if n * w_max < 1.0 - 1e-9:
        raise ValueError(f"infeasible bounds: n={n} * w_max={w_max} < 1 — sum cannot reach 1")
    for _ in range(10):
        w = np.clip(w, w_min, w_max)
        s = w.sum()
        if s <= 0:
            return np.full_like(w, 1.0 / len(w))
        w = w / s
        # If clipping happened the sum may be off; iterate.
        if abs(w.sum() - 1.0) < 1e-6 and (w >= w_min - 1e-9).all() and (w <= w_max + 1e-9).all():
            return np.clip(w, w_min, w_max)
    return np.clip(w / w.sum(), w_min, w_max)


def brier_loss(weights: np.ndarray, factor_signals: np.ndarray, outcomes: np.ndarray) -> float:
    """Weighted-aggregate Brier on a batch.

    factor_signals: shape (N, F) — each row = one observation, each col = one
                     factor's directional signal in [0, 1] (where 0.5 = neutral).
    outcomes:       shape (N,)   — realized binary outcome in {0, 1}.
    """
    if factor_signals.size == 0:
        return float("nan")
    preds = factor_signals @ weights  # shape (N,)
    return float(((preds - outcomes) ** 2).mean())


def step_sgd(
    weights: np.ndarray,
    factor_signals: np.ndarray,
    outcomes: np.ndarray,
    *,
    lr: float = DEFAULT_LR,
    momentum: float = DEFAULT_MOMENTUM,
    velocity: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """One projected-SGD step. Returns (new_weights, new_velocity)."""
    preds = factor_signals @ weights
    errors = preds - outcomes  # shape (N,)
    grad = (2.0 / len(outcomes)) * (factor_signals.T @ errors)  # shape (F,)
    if velocity is None:
        velocity = np.zeros_like(weights)
    new_velocity = momentum * velocity + lr * grad
    new_weights = project_simplex_bounded(weights - new_velocity)
    return new_weights, new_velocity


def run_optimization(
    initial_weights: Mapping[str, float],
    factor_signals: np.ndarray,
    outcomes: np.ndarray,
    *,
    n_steps: int = 200,
    lr: float = DEFAULT_LR,
    momentum: float = DEFAULT_MOMENTUM,
    convergence_eps: float = 1e-5,
) -> OptimizationResult:
    """Full optimization pass on a fixed batch."""
    factor_names = list(initial_weights.keys())
    w = np.asarray([initial_weights[k] for k in factor_names], dtype=np.float64)
    w = project_simplex_bounded(w)

    brier_before = brier_loss(w, factor_signals, outcomes)
    velocity: np.ndarray | None = None
    converged = False
    prev_loss = brier_before
    for _ in range(n_steps):
        w_next, velocity = step_sgd(
            w, factor_signals, outcomes, lr=lr, momentum=momentum, velocity=velocity
        )
        w = w_next
        loss = brier_loss(w, factor_signals, outcomes)
        if abs(loss - prev_loss) < convergence_eps:
            converged = True
            break
        prev_loss = loss

    brier_after = brier_loss(w, factor_signals, outcomes)
    # Sanity check
    if abs(w.sum() - 1.0) > 0.01:
        raise RuntimeError(f"weights sanity check failed: sum={w.sum()}")

    return OptimizationResult(
        weights_proposed=dict(zip(factor_names, w.tolist(), strict=False)),
        n_obs=len(outcomes),
        brier_before=float(brier_before),
        brier_after=float(brier_after),
        delta=float(brier_after - brier_before),
        converged=converged,
    )


async def persist_optimizer_run(
    session: AsyncSession,
    *,
    asset: str | None,
    regime: str,
    result: OptimizationResult,
    holdout_days: int = 21,
    algo: str = "online_sgd",
    lr: float = DEFAULT_LR,
) -> UUID:
    """Insert a row in `brier_optimizer_runs`. Returns the run UUID.

    Brier values are NaN-guarded: a run on an empty batch (n_obs == 0)
    gets `before/after/delta = NULL` rather than raising
    `decimal.InvalidOperation` on `Decimal(NaN)`.
    """
    import json

    from sqlalchemy import text as sa_text

    def _decimal_or_none(v: float) -> Decimal | None:
        if v is None or not math.isfinite(v):
            return None
        return Decimal(f"{v:.4f}")

    run_id = uuid4()
    now = datetime.now(UTC)
    await session.execute(
        sa_text(
            """
            INSERT INTO brier_optimizer_runs
                (id, ran_at, algo, lr, n_obs, brier_before, brier_after,
                 delta, weights_proposed, adopted,
                 holdout_period_start, holdout_period_end, notes)
            VALUES
                (:id, :ran_at, :algo, :lr, :n_obs, :before, :after,
                 :delta, CAST(:weights AS jsonb), false,
                 :hs, :he, :notes)
            """
        ),
        {
            "id": str(run_id),
            "ran_at": now,
            "algo": algo,
            "lr": Decimal(str(lr)),
            "n_obs": result.n_obs,
            "before": _decimal_or_none(result.brier_before),
            "after": _decimal_or_none(result.brier_after),
            "delta": _decimal_or_none(result.delta),
            "weights": json.dumps(result.weights_proposed),
            "hs": now,
            "he": now + timedelta(days=holdout_days),
            "notes": (f"asset={asset or 'global'} regime={regime} converged={result.converged}"),
        },
    )
    return run_id


async def latest_active_weights(
    session: AsyncSession, *, asset: str | None, regime: str
) -> dict[str, float] | None:
    """Read the active weights row from confluence_weights_history."""
    from ..models import ConfluenceHistory  # noqa: F401  (ensure model loaded)

    sql = (
        "SELECT weights FROM confluence_weights_history "
        "WHERE regime = :regime AND is_active = TRUE "
        + ("AND asset = :asset " if asset else "AND asset IS NULL ")
        + "ORDER BY created_at DESC LIMIT 1"
    )
    params: dict[str, str] = {"regime": regime}
    if asset:
        params["asset"] = asset
    from sqlalchemy import text as sa_text

    row = (await session.execute(sa_text(sql), params)).mappings().first()
    if row is None:
        return None
    raw = row["weights"]
    if isinstance(raw, str):
        return __import__("json").loads(raw)
    return dict(raw)
