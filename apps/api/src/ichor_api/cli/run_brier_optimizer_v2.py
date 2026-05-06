"""V2 Brier optimizer — projected SGD on the per-factor drivers matrix.

Per the D.1 sprint of `ichor_pending_todos_2026-05-06.md` and ADR-022 :

V1 (`run_brier_optimizer.py`) only writes a diagnostic row aggregating
mean Brier contribution. V2 adds the real per-factor optimization step
that closes the Living Entity loop : it reads the new
`session_card_audit.drivers` JSONB column (migration 0026), pivots it
into an (N_cards, N_factors) matrix using the sign convention from
`services/confluence_engine.assess_confluence` (contribution ∈ [-1, +1]
→ signal ∈ [0, 1]), reverse-engineers binary outcomes from the Brier
identity (brier = (p_up - y)² with y ∈ {0, 1}), and runs the existing
projected-SGD primitives in `services/brier_optimizer.run_optimization`.

Adoption is still gated on a 21-day holdout — V2 writes
`brier_optimizer_runs(adopted=False)` rows with `algo='online_sgd'` (a
later promotion step flips `adopted=True` if `brier_after − brier_before`
beats the MDE on out-of-sample cards).

Activation
----------
Behind the env flag ``ICHOR_API_BRIER_V2_ENABLED``. Default: false. When
unset / false this CLI logs a single line and exits 0 — the V1 nightly
cron keeps running undisturbed. Eliot enables V2 once Hetzner has
enough drivers-tagged cards (~30 days of populated rows) by exporting
``ICHOR_API_BRIER_V2_ENABLED=true`` in ``/etc/ichor/api.env``.

Usage
-----
::

    # Local dry run (reads but does not commit)
    python -m ichor_api.cli.run_brier_optimizer_v2

    # Production cron (commits to brier_optimizer_runs)
    ICHOR_API_BRIER_V2_ENABLED=true python -m ichor_api.cli.run_brier_optimizer_v2 \
        --persist --lookback-days 30
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select

from ..db import get_engine, get_sessionmaker
from ..models import SessionCardAudit
from ..services.brier_optimizer import (
    DEFAULT_FACTOR_NAMES,
    aggregate_drivers_matrix,
    latest_active_weights,
    persist_optimizer_run,
    run_optimization,
)

log = structlog.get_logger(__name__)

# Minimum number of cards per (asset, regime) group below which projected
# SGD is statistically meaningless (high variance vs equal-weight baseline).
MIN_OBS_PER_GROUP = 30

# Adoption recommendation threshold — matches the V1 MDE Brier delta.
MDE_DELTA = 0.02


def _v2_enabled() -> bool:
    """Read the runtime feature flag. Default: false (no-op)."""
    raw = os.environ.get("ICHOR_API_BRIER_V2_ENABLED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _equal_weights() -> dict[str, float]:
    n = len(DEFAULT_FACTOR_NAMES)
    w = 1.0 / n
    return dict.fromkeys(DEFAULT_FACTOR_NAMES, w)


async def _list_groups(
    session: Any, *, lookback_days: int
) -> list[tuple[str, str]]:
    """Distinct (asset, regime) groups with at least one drivers-tagged card
    in the lookback window."""
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    stmt = (
        select(SessionCardAudit.asset, SessionCardAudit.regime_quadrant)
        .where(
            SessionCardAudit.generated_at >= cutoff,
            SessionCardAudit.drivers.is_not(None),
            SessionCardAudit.brier_contribution.is_not(None),
        )
        .distinct()
    )
    rows = (await session.execute(stmt)).all()
    return [(asset, (regime or "all")) for asset, regime in rows]


async def _restrict_initial_weights(
    session: Any, *, asset: str, regime: str
) -> dict[str, float]:
    """Read the active weights for (asset, regime) and project them onto the
    canonical factor list. Missing factors fall back to equal-weight share so
    initial sum stays close to 1 before the simplex projection."""
    current = await latest_active_weights(session, asset=asset, regime=regime)
    if not current:
        return _equal_weights()
    fallback = 1.0 / len(DEFAULT_FACTOR_NAMES)
    return {name: float(current.get(name, fallback)) for name in DEFAULT_FACTOR_NAMES}


async def run(*, persist: bool, lookback_days: int = 30) -> int:
    if not _v2_enabled():
        print(
            "ICHOR_API_BRIER_V2_ENABLED is unset or false — V2 optimizer "
            "skipped (V1 nightly cron stays active)."
        )
        return 0

    sm = get_sessionmaker()
    async with sm() as session:
        groups = await _list_groups(session, lookback_days=lookback_days)

    if not groups:
        print(
            f"Brier V2 · no drivers-tagged cards in the last {lookback_days}d "
            "— skipping run."
        )
        return 0

    print(
        f"Brier V2 · {len(groups)} (asset, regime) groups over "
        f"{lookback_days}d window"
    )

    n_runs = 0
    n_skipped_low_n = 0
    n_candidates = 0

    for asset, regime in groups:
        async with sm() as session:
            initial = await _restrict_initial_weights(session, asset=asset, regime=regime)
            mat = await aggregate_drivers_matrix(
                session,
                asset=asset,
                regime=regime if regime != "all" else None,
                lookback_days=lookback_days,
                min_obs=MIN_OBS_PER_GROUP,
            )
            if mat is None:
                n_skipped_low_n += 1
                print(
                    f"  [{asset:10s} / {regime:12s}] skipped — "
                    f"n < {MIN_OBS_PER_GROUP}"
                )
                continue

            result = run_optimization(initial, mat.factor_signals, mat.outcomes)
            n_runs += 1

            print(
                f"  [{asset:10s} / {regime:12s}] n={result.n_obs:4d} "
                f"brier {result.brier_before:.4f} -> {result.brier_after:.4f} "
                f"(delta {result.delta:+.4f}) converged={result.converged} "
                f"skipped={mat.n_skipped_no_drivers}/{mat.n_skipped_ambiguous_outcome}"
            )

            if result.delta < -MDE_DELTA:
                n_candidates += 1
                print(
                    f"    ↳ candidate for adoption — delta < -{MDE_DELTA} "
                    "(21d holdout will confirm)"
                )

            if persist:
                await persist_optimizer_run(
                    session,
                    asset=asset,
                    regime=regime,
                    result=result,
                    algo="online_sgd",
                )
                await session.commit()

    print(
        f"Brier V2 · {n_runs} optimizations / {n_skipped_low_n} skipped (low n) "
        f"/ {n_candidates} adoption candidates"
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_brier_optimizer_v2")
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
