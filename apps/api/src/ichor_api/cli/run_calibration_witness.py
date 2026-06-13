"""run_calibration_witness — Chantier B slice-4 (ADR-119).

READ-ONLY witness CLI. Pulls the reconciled session cards from
``session_card_audit``, rebuilds each ``(p_up, y)`` from the persisted
``(bias_direction, conviction_pct, brier_contribution)`` (reusing the canonical
``brier.conviction_to_p_up`` + ``brier_optimizer.derive_realized_outcome``), and
forward-tests the slice-2/3 calibration candidates out-of-sample via
``services.calibration_witness``. It prints a markdown report and **writes
nothing** — the answer to "does re-calibrating the conviction beat raw, OOS?".

This decides nothing live (ADR-118/119): wiring a winning calibrator into the
verdict is a later GATED step (deploy + sustained re-witness). Run it as more
cards reconcile; the report states N honestly and flags a thin split as
inconclusive rather than inventing an edge.

Usage:
  python -m ichor_api.cli.run_calibration_witness [--session-type pre_ny]
      [--train-frac 0.6] [--min-conclusive 30] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_engine, get_sessionmaker
from ..models import SessionCardAudit
from ..services.brier import conviction_to_p_up
from ..services.brier_optimizer import derive_realized_outcome
from ..services.calibration_witness import format_witness_markdown, run_calibration_witness

log = structlog.get_logger(__name__)


async def _load_samples(
    session: AsyncSession, *, session_type: str | None, limit: int | None
) -> list[tuple[str, float, int]]:
    """Time-ordered (oldest-first) ``(asset, p_up, y)`` from reconciled cards.
    READ-ONLY. Skips neutral / ambiguous cards (``y is None``)."""
    stmt = (
        select(
            SessionCardAudit.asset,
            SessionCardAudit.bias_direction,
            SessionCardAudit.conviction_pct,
            SessionCardAudit.brier_contribution,
        )
        .where(SessionCardAudit.brier_contribution.is_not(None))
        .order_by(SessionCardAudit.generated_at.asc())
    )
    if session_type:
        stmt = stmt.where(SessionCardAudit.session_type == session_type)
    if limit:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).all()

    samples: list[tuple[str, float, int]] = []
    for asset, bias, conviction, brier in rows:
        if brier is None:
            continue
        y = derive_realized_outcome(bias, conviction, brier)
        if y is None:  # neutral bias carried no directional forecast
            continue
        samples.append((asset, conviction_to_p_up(bias, conviction), y))
    return samples


async def _async_main(args: argparse.Namespace) -> int:
    sm = get_sessionmaker()
    try:
        async with sm() as session:
            samples = await _load_samples(session, session_type=args.session_type, limit=args.limit)
    finally:
        await get_engine().dispose()

    if not samples:
        log.warning("calibration_witness.no_samples", session_type=args.session_type)
        print("# Conviction-calibration OOS witness (ADR-119)\n\nNo reconciled cards found.")
        return 0

    report = run_calibration_witness(
        samples,
        train_frac=args.train_frac,
        min_conclusive_test=args.min_conclusive,
    )
    print(format_witness_markdown(report))
    log.info(
        "calibration_witness.done",
        n_samples=len(samples),
        any_conclusive_improvement=report.any_conclusive_improvement,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Conviction-calibration OOS witness (read-only).")
    parser.add_argument("--session-type", default=None, help="filter, e.g. pre_ny")
    parser.add_argument("--train-frac", type=float, default=0.6)
    parser.add_argument("--min-conclusive", type=int, default=30)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
