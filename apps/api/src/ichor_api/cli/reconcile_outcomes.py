"""Reconcile session-card outcomes against realized prices.

Runs nightly (systemd timer) ~23:00 Paris. For each session card whose
`timing_window_end < now()` and `realized_at IS NULL`, this CLI :

  1. Pulls the Polygon 1-min bars in the window [generated_at,
     timing_window_end OR generated_at + 8h].
  2. Computes realized open/high/low/close, direction, and Brier
     contribution via `services.brier.reconcile_card`.
  3. Writes back to `session_card_audit.realized_*` +
     `brier_contribution` + `realized_at = now()`.

Usage :
  python -m ichor_api.cli.reconcile_outcomes [--limit N] [--asset CODE]
                                              [--dry-run]

`--dry-run` reports what would be written without committing.

Implements VISION_2026.md delta H (Brier reconciler) and ADR-017
capability #8 (Persistent track-record + public calibration).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_engine, get_sessionmaker
from ..models import PolygonIntradayBar, SessionCardAudit
from ..services.brier import reconcile_card

log = structlog.get_logger(__name__)

# Buffer after timing_window_end before we consider the session closed
# enough to reconcile. Bars from a closed window are immutable.
_GRACE_PERIOD = timedelta(minutes=15)

# When timing_window_end is null, fall back to this default window.
_DEFAULT_WINDOW = timedelta(hours=8)


async def _find_pending_cards(
    session: AsyncSession, *, limit: int, asset_filter: str | None
) -> list[SessionCardAudit]:
    """Cards waiting for reconciliation : realized_at IS NULL and
    timing window has elapsed (with grace period)."""
    cutoff = datetime.now(timezone.utc) - _GRACE_PERIOD
    stmt = (
        select(SessionCardAudit)
        .where(SessionCardAudit.realized_at.is_(None))
        .order_by(desc(SessionCardAudit.generated_at))
        .limit(limit)
    )
    if asset_filter:
        stmt = stmt.where(SessionCardAudit.asset == asset_filter.upper())
    rows = (await session.execute(stmt)).scalars().all()
    out: list[SessionCardAudit] = []
    for r in rows:
        end = r.timing_window_end or (r.generated_at + _DEFAULT_WINDOW)
        if end <= cutoff:
            out.append(r)
    return out


async def _bars_for_card(
    session: AsyncSession, card: SessionCardAudit
) -> list[PolygonIntradayBar]:
    """Polygon 1-min bars covering the session window for this asset."""
    start = card.generated_at
    end = card.timing_window_end or (card.generated_at + _DEFAULT_WINDOW)
    stmt = (
        select(PolygonIntradayBar)
        .where(
            PolygonIntradayBar.asset == card.asset,
            PolygonIntradayBar.bar_ts >= start,
            PolygonIntradayBar.bar_ts <= end,
        )
        .order_by(PolygonIntradayBar.bar_ts.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _reconcile_one(
    session: AsyncSession, card: SessionCardAudit, *, dry_run: bool
) -> tuple[bool, str]:
    """Reconcile a single card. Returns (committed, reason)."""
    bars = await _bars_for_card(session, card)
    if not bars:
        return False, "no bars in window"
    open_px = bars[0].open
    close_px = bars[-1].close
    high_px = max(b.high for b in bars)
    low_px = min(b.low for b in bars)

    bias = card.bias_direction  # type: ignore[assignment]
    if bias not in ("long", "short", "neutral"):
        return False, f"unknown bias_direction {bias!r}"

    outcome = reconcile_card(
        bias_direction=bias,  # type: ignore[arg-type]
        conviction_pct=card.conviction_pct,
        open_px=open_px,
        close_px=close_px,
        high_px=high_px,
        low_px=low_px,
    )

    if dry_run:
        return False, (
            f"dry-run · p_up={outcome.p_up:.3f} y={outcome.realized_outcome} "
            f"brier={outcome.brier_contribution:.4f}"
        )

    card.realized_close_session = outcome.realized_close_session
    card.realized_high_session = outcome.realized_high_session
    card.realized_low_session = outcome.realized_low_session
    card.realized_at = datetime.now(timezone.utc)
    card.brier_contribution = outcome.brier_contribution
    return True, f"brier={outcome.brier_contribution:.4f} y={outcome.realized_outcome}"


async def _run(*, limit: int, asset_filter: str | None, dry_run: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        cards = await _find_pending_cards(
            session, limit=limit, asset_filter=asset_filter
        )
        if not cards:
            print("no pending cards to reconcile")
            return 0
        n_committed = 0
        for card in cards:
            committed, reason = await _reconcile_one(
                session, card, dry_run=dry_run
            )
            log.info(
                "reconcile.card",
                id=str(card.id),
                asset=card.asset,
                session_type=card.session_type,
                committed=committed,
                reason=reason,
            )
            print(
                f"{'OK ' if committed else '-- '}{card.asset:10s} "
                f"{card.session_type:14s} {reason}"
            )
            if committed:
                n_committed += 1
        if not dry_run and n_committed > 0:
            await session.commit()
        print(
            f"\n{n_committed}/{len(cards)} cards reconciled "
            f"({'DRY-RUN' if dry_run else 'committed'})"
        )
    return 0


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="reconcile_outcomes",
        description="Fill realized_* + brier_contribution columns on closed session cards.",
    )
    parser.add_argument("--limit", type=int, default=100, help="max cards per run")
    parser.add_argument("--asset", type=str, default=None, help="restrict to one asset")
    parser.add_argument("--dry-run", action="store_true", help="don't commit")
    args = parser.parse_args(argv)
    try:
        return await _run(
            limit=args.limit,
            asset_filter=args.asset,
            dry_run=args.dry_run,
        )
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
