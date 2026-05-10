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
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

# Bounds per SPEC §3.7.
WEIGHT_MIN = 0.05
WEIGHT_MAX = 0.5

DEFAULT_LR = 0.05
DEFAULT_MOMENTUM = 0.9

# Canonical factor list emitted by services/confluence_engine.assess_confluence.
# V2 reads `session_card_audit.drivers` and pivots a row into a (F,) signal
# vector indexed by these names ; missing factors fall back to 0.5 (neutral).
DEFAULT_FACTOR_NAMES: tuple[str, ...] = (
    "rate_diff",
    "cot",
    "microstructure_ofi",
    "daily_levels",
    "polymarket_overlay",
    "funding_stress",
    "surprise_index",
    "vix_term",
    "risk_appetite",
    "btc_risk_proxy",
)


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
            full: np.ndarray = np.full_like(w, 1.0 / len(w))
            return full
        w = w / s
        # If clipping happened the sum may be off; iterate.
        if abs(w.sum() - 1.0) < 1e-6 and (w >= w_min - 1e-9).all() and (w <= w_max + 1e-9).all():
            clipped: np.ndarray = np.clip(w, w_min, w_max)
            return clipped
    final: np.ndarray = np.clip(w / w.sum(), w_min, w_max)
    return final


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


# ──────────────────────── V2 helpers (D.1 sprint) ─────────────────────
# These pivot the new `session_card_audit.drivers` JSONB column (added by
# migration 0026, shape list[{factor, contribution, evidence}]) into a
# (N, F) signal matrix + (N,) outcome vector that the V1 `run_optimization`
# helpers can fit. Outcomes are reverse-engineered from the Brier identity
# brier = (p_up - y)^2 with y ∈ {0, 1} — exact for any non-neutral card.


def derive_realized_outcome(
    bias_direction: str,
    conviction_pct: float,
    brier_contribution: float,
    *,
    tolerance: float = 1e-3,
) -> int | None:
    """Reverse-engineer the binary outcome y ∈ {0, 1} from the persisted
    Brier contribution.

    The reconciler writes brier_contribution = (p_up − y)² where y ∈ {0, 1}.
    Given (bias, conviction) we recover p_up via `services.brier.conviction_to_p_up`
    and pick whichever y minimizes |brier − (p_up − y)²|.

    Returns None when both candidates are within `tolerance` of brier — that
    only happens at p_up = 0.5 (neutral bias), where the call carried no
    directional information and the optimizer must skip the row.
    """
    from .brier import conviction_to_p_up

    if bias_direction not in {"long", "short", "neutral"}:
        return None
    p_up = conviction_to_p_up(bias_direction, conviction_pct)  # type: ignore[arg-type]
    diff_y0 = abs(brier_contribution - p_up * p_up)
    diff_y1 = abs(brier_contribution - (p_up - 1.0) ** 2)
    if abs(diff_y0 - diff_y1) < tolerance:
        return None
    return 0 if diff_y0 < diff_y1 else 1


def drivers_to_signal_row(
    drivers: list[Any] | None,
    factor_names: tuple[str, ...] = DEFAULT_FACTOR_NAMES,
) -> np.ndarray | None:
    """Map a `drivers` JSONB row → (F,) array of signals in [0, 1].

    confluence_engine emits Driver.contribution ∈ [-1, +1] (signed,
    + = long, − = short). The V1 optimizer expects signals in [0, 1]
    with 0.5 = neutral, so we apply `signal = 0.5 + 0.5 * contribution`
    and clamp out-of-range values defensively.

    Missing factors default to 0.5 (neutral). Returns None if `drivers`
    is None or empty (no signal at all). Argument type stays `list[Any]`
    because the column is JSONB — rows surfaced by SQLAlchemy may contain
    legacy shapes or string-encoded contributions ; we validate each entry.
    """
    if not drivers:
        return None
    by_factor: dict[str, float] = {}
    for entry in drivers:
        if not isinstance(entry, dict):
            continue
        f = entry.get("factor")
        c = entry.get("contribution")
        if not isinstance(f, str) or c is None:
            continue
        try:
            c_val = float(c)
        except (TypeError, ValueError):
            continue
        c_clamped = max(-1.0, min(1.0, c_val))
        by_factor[f] = 0.5 + 0.5 * c_clamped
    if not by_factor:
        return None
    arr: np.ndarray = np.array(
        [by_factor.get(name, 0.5) for name in factor_names],
        dtype=np.float64,
    )
    return arr


@dataclass(frozen=True)
class DriversMatrix:
    """Output of `aggregate_drivers_matrix` — keeps the factor list paired
    with the matrix so callers don't drift between V1 helpers."""

    factor_names: list[str]
    factor_signals: np.ndarray
    """Shape (N, F), each row = one card, each col = one factor signal."""
    outcomes: np.ndarray
    """Shape (N,), binary realized direction (1 = close > open)."""
    n_skipped_no_drivers: int
    n_skipped_ambiguous_outcome: int


async def aggregate_drivers_matrix(
    session: AsyncSession,
    *,
    asset: str | None,
    regime: str | None,
    lookback_days: int = 30,
    factor_names: tuple[str, ...] = DEFAULT_FACTOR_NAMES,
    min_obs: int = 30,
) -> DriversMatrix | None:
    """Build a (factor_signals, outcomes) batch from `session_card_audit`.

    Filters :
      - drivers IS NOT NULL
      - brier_contribution IS NOT NULL
      - generated_at >= now − lookback_days
      - asset = :asset (when provided)
      - regime_quadrant = :regime (when provided ; "all" maps to NULL/any)

    Skips rows where drivers cannot be parsed or outcome is ambiguous
    (neutral bias). Returns None when fewer than `min_obs` rows survive
    filtering — projected SGD on tiny batches is meaningless.
    """
    from sqlalchemy import select

    from ..models import SessionCardAudit

    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    stmt = select(
        SessionCardAudit.bias_direction,
        SessionCardAudit.conviction_pct,
        SessionCardAudit.brier_contribution,
        SessionCardAudit.drivers,
    ).where(
        SessionCardAudit.generated_at >= cutoff,
        SessionCardAudit.brier_contribution.is_not(None),
        SessionCardAudit.drivers.is_not(None),
    )
    if asset:
        stmt = stmt.where(SessionCardAudit.asset == asset)
    if regime and regime != "all":
        stmt = stmt.where(SessionCardAudit.regime_quadrant == regime)

    rows = (await session.execute(stmt)).all()

    signals_rows: list[np.ndarray] = []
    outcomes_list: list[float] = []
    n_no_drivers = 0
    n_ambiguous = 0

    for bias, conviction, brier, drivers in rows:
        sig = drivers_to_signal_row(drivers, factor_names)
        if sig is None:
            n_no_drivers += 1
            continue
        outcome = derive_realized_outcome(str(bias), float(conviction), float(brier))
        if outcome is None:
            n_ambiguous += 1
            continue
        signals_rows.append(sig)
        outcomes_list.append(float(outcome))

    if len(outcomes_list) < min_obs:
        return None

    factor_signals = np.vstack(signals_rows)
    outcomes_arr = np.array(outcomes_list, dtype=np.float64)
    return DriversMatrix(
        factor_names=list(factor_names),
        factor_signals=factor_signals,
        outcomes=outcomes_arr,
        n_skipped_no_drivers=n_no_drivers,
        n_skipped_ambiguous_outcome=n_ambiguous,
    )


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
        loaded: dict[str, float] = __import__("json").loads(raw)
        return loaded
    return dict(raw)
