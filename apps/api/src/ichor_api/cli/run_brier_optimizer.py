"""CLI runner for the nightly Brier→weights optimizer.

Closes the Living Entity loop step 3 : reads recent session card
outcomes (brier_contribution), aggregates per (asset, regime), seeds
baseline weights into `confluence_weights_history` if none exist, and
writes a diagnostic row to `brier_optimizer_runs`.

V1 scope (this file):
  - Seed equal-weight rows into confluence_weights_history when none
    exist for a given (asset, regime). This unblocks the runtime
    `assess_confluence(...)` path that now reads from this table.
  - Aggregate Brier statistics (count, mean, p95) for monitoring.
  - Always-False adoption ; promotion to active is gated on a 21-day
    holdout (V2 — needs per-factor signal storage).

V2 scope (deferred — TODO when session_card_audit gets a `drivers` JSONB):
  - Run brier_optimizer.run_optimization with real factor_signals.
  - Compare brier_after vs brier_before on holdout, flip adopted=True
    when delta < -0.02 (MDE).

Usage:
    python -m ichor_api.cli.run_brier_optimizer          # dry-run
    python -m ichor_api.cli.run_brier_optimizer --persist

Cron-driven from `scripts/hetzner/register-cron-brier-optimizer.sh`
(nightly at 03:30 Paris, after the reconciler at 02:00).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy import text as sa_text

from ..db import get_engine, get_sessionmaker
from ..models import SessionCardAudit
from ..services.brier_optimizer import latest_active_weights

log = structlog.get_logger(__name__)

# Equal-weight seed across the 10 confluence factors emitted by
# services/confluence_engine.py:assess_confluence. Names must match
# the Driver.factor symbolic name used at runtime.
_FACTOR_NAMES: tuple[str, ...] = (
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


def _equal_weights() -> dict[str, float]:
    n = len(_FACTOR_NAMES)
    w = 1.0 / n
    return dict.fromkeys(_FACTOR_NAMES, w)


async def _aggregate_brier(
    session: Any, *, lookback_days: int
) -> list[tuple[str, str, int, float]]:
    """Return [(asset, regime, n_obs, mean_brier)] over the window."""
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    stmt = (
        select(
            SessionCardAudit.asset,
            SessionCardAudit.regime_quadrant,
            SessionCardAudit.brier_contribution,
        )
        .where(
            SessionCardAudit.generated_at >= cutoff,
            SessionCardAudit.brier_contribution.is_not(None),
        )
    )
    rows = (await session.execute(stmt)).all()

    grouped: dict[tuple[str, str], list[float]] = {}
    for asset, regime, brier in rows:
        regime_str = (regime or "all").lower()
        grouped.setdefault((asset, regime_str), []).append(float(brier))

    out: list[tuple[str, str, int, float]] = []
    for (asset, regime), briers in grouped.items():
        if not briers:
            continue
        out.append((asset, regime, len(briers), sum(briers) / len(briers)))
    return out


async def _seed_baseline_weights_if_missing(
    session: Any,
    *,
    asset: str,
    regime: str,
    persist: bool,
) -> bool:
    """Insert an equal-weight row in confluence_weights_history when no
    active row exists for (asset, regime). Returns True if seeded."""
    existing = await latest_active_weights(session, asset=asset, regime=regime)
    if existing is not None:
        return False

    if not persist:
        log.info("brier_optimizer.would_seed", asset=asset, regime=regime)
        return False

    weights = _equal_weights()
    now = datetime.now(UTC)
    # Schema (migration 0014) : id, created_at, asset, regime, weights,
    # brier_30d, ece_30d, optimizer_run_id, is_active, notes.
    # No `source` column — we embed the seed signal in `notes`.
    await session.execute(
        sa_text(
            """
            INSERT INTO confluence_weights_history
                (id, created_at, asset, regime, weights, is_active, notes)
            VALUES
                (:id, :created_at, :asset, :regime, CAST(:weights AS jsonb),
                 TRUE, :notes)
            """
        ),
        {
            "id": str(uuid4()),
            "created_at": now,
            "asset": asset,
            # Schema is String(16) — truncate defensively. Common Ichor
            # regime tags (haven_bid, risk_on, etc.) all fit.
            "regime": regime[:16],
            "weights": json.dumps(weights),
            "notes": (
                f"[brier_optimizer_seed] Equal-weight baseline "
                f"({asset}/{regime}) — no prior active row."
            ),
        },
    )
    return True


async def _persist_diagnostic_run(
    session: Any,
    *,
    asset: str,
    regime: str,
    n_obs: int,
    mean_brier: float,
) -> None:
    """Insert a diagnostic row in brier_optimizer_runs (adopted=False).

    The actual SGD-optimized weights are not yet computed (V2 — needs
    per-factor signal storage). This row exists so the dashboard can
    show "the optimizer ran on N=X obs with mean_brier=Y on date Z"
    even before we have real per-factor optimization.
    """
    from decimal import Decimal

    now = datetime.now(UTC)
    weights = _equal_weights()
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
            "id": str(uuid4()),
            "ran_at": now,
            "algo": "diagnostic_v1",
            "lr": Decimal("0"),
            "n_obs": n_obs,
            "before": Decimal(f"{mean_brier:.4f}"),
            "after": Decimal(f"{mean_brier:.4f}"),
            "delta": Decimal("0"),
            "weights": json.dumps(weights),
            "hs": now,
            "he": now + timedelta(days=21),
            "notes": (
                f"V1 diagnostic only: aggregate Brier on {n_obs} obs for "
                f"{asset}/{regime}. Per-factor SGD optimization deferred to V2."
            ),
        },
    )


async def run(*, persist: bool, lookback_days: int = 30) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        groups = await _aggregate_brier(session, lookback_days=lookback_days)

    print(
        f"Brier optimizer · {len(groups)} (asset,regime) groups over "
        f"{lookback_days}d window"
    )

    # Always seed at least the global baseline so confluence_engine can
    # find weights even when no session cards exist yet.
    if not groups:
        groups = [("GLOBAL", "all", 0, 0.0)]

    n_seeded = 0
    for asset, regime, n_obs, mean_brier in groups:
        print(f"  [{asset:10s} / {regime:12s}] n={n_obs:4d} mean_brier={mean_brier:.4f}")
        if persist:
            async with sm() as session:
                seeded = await _seed_baseline_weights_if_missing(
                    session, asset=asset, regime=regime, persist=True
                )
                if n_obs > 0:
                    await _persist_diagnostic_run(
                        session,
                        asset=asset,
                        regime=regime,
                        n_obs=n_obs,
                        mean_brier=mean_brier,
                    )
                await session.commit()
            if seeded:
                n_seeded += 1
                print("    ↳ seeded equal-weight baseline (was missing)")

    if persist:
        print(f"Brier optimizer · seeded {n_seeded} baseline weight rows")

    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_brier_optimizer")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=30)
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist, lookback_days=args.lookback_days))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
