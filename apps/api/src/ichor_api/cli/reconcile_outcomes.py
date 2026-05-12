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
from datetime import UTC, datetime, timedelta

import structlog
from ichor_brain.scenarios import bucket_for_zscore
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_engine, get_sessionmaker
from ..models import PolygonIntradayBar, ScenarioCalibrationBins, SessionCardAudit
from ..services.brier import reconcile_card
from ..services.scenario_calibration import _PIP_UNIT_FACTOR

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
    cutoff = datetime.now(UTC) - _GRACE_PERIOD
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


async def _bars_for_card(session: AsyncSession, card: SessionCardAudit) -> list[PolygonIntradayBar]:
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

    # W105g — compute realized_scenario_bucket via z-score lookup on
    # the most recent ScenarioCalibrationBins row for (asset,
    # session_type). Pure addition : pre-existing brier_contribution
    # logic untouched ; scenarios reconciliation isolated and None-safe.
    realized_bucket = await _resolve_realized_bucket(
        session,
        asset=card.asset,
        session_type=card.session_type,
        open_px=open_px,
        close_px=close_px,
    )

    if dry_run:
        return False, (
            f"dry-run · p_up={outcome.p_up:.3f} y={outcome.realized_outcome} "
            f"brier={outcome.brier_contribution:.4f} "
            f"bucket={realized_bucket or 'n/a'}"
        )

    card.realized_close_session = outcome.realized_close_session
    card.realized_high_session = outcome.realized_high_session
    card.realized_low_session = outcome.realized_low_session
    card.realized_at = datetime.now(UTC)
    card.brier_contribution = outcome.brier_contribution
    if realized_bucket is not None:
        card.realized_scenario_bucket = realized_bucket
    return True, (
        f"brier={outcome.brier_contribution:.4f} y={outcome.realized_outcome} "
        f"bucket={realized_bucket or 'n/a'}"
    )


async def _resolve_realized_bucket(
    session: AsyncSession,
    *,
    asset: str,
    session_type: str,
    open_px: float,
    close_px: float,
) -> str | None:
    """Map the session's realized close-to-open log-return to one of the
    7 canonical buckets (`ichor_brain.scenarios.bucket_for_zscore`).

    Resolution :
      1. Fetch the most recent ScenarioCalibrationBins row for
         (asset, session_type) via the latest-DESC index (W105a).
      2. Convert realized log-return → pip/point unit via
         `_PIP_UNIT_FACTOR[asset]`.
      3. Recover sigma_pips from the stored thresholds
         (`pip_thresholds[i] = z_thresholds[i] * sigma`).
      4. Pass the realized z-score to `bucket_for_zscore`.

    Returns None when no calibration row exists yet (cold-start). The
    W105b weekly Sunday cron populates calibration rows for the 6
    assets × 5 session types ; before the first run, this stays None
    and the W108 reconciler will catch up retroactively.
    """
    import math

    if open_px <= 0.0 or close_px <= 0.0:
        return None

    stmt = (
        select(ScenarioCalibrationBins)
        .where(ScenarioCalibrationBins.asset == asset)
        .where(ScenarioCalibrationBins.session_type == session_type)
        .order_by(desc(ScenarioCalibrationBins.computed_at))
        .limit(1)
    )
    cal = (await session.execute(stmt)).scalar_one_or_none()
    if cal is None:
        return None

    # Recover sigma_pips from the stored thresholds. We persisted
    # `pip_thresholds[i] = z_thresholds[i] * sigma_pips` so dividing
    # back gives sigma. Use the `+0.25` bin (z_thresholds index 3) :
    # it's always non-zero by canonical convention.
    try:
        z_thr = list(cal.bins_z_thresholds)
        pip_thr = list(cal.bins_pip_thresholds)
        if len(z_thr) < 4 or len(pip_thr) < 4 or z_thr[3] == 0.0:
            return None
        sigma_pips = pip_thr[3] / z_thr[3]
        if sigma_pips <= 0.0:
            return None
    except (KeyError, IndexError, TypeError, ZeroDivisionError):
        return None

    unit_factor = _PIP_UNIT_FACTOR.get(asset, 1.0)
    realized_log_return = math.log(close_px / open_px)
    realized_pips = realized_log_return * unit_factor
    z = realized_pips / sigma_pips
    return bucket_for_zscore(z)


async def _run(*, limit: int, asset_filter: str | None, dry_run: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        cards = await _find_pending_cards(session, limit=limit, asset_filter=asset_filter)
        if not cards:
            print("no pending cards to reconcile")
            return 0
        n_committed = 0
        for card in cards:
            committed, reason = await _reconcile_one(session, card, dry_run=dry_run)
            log.info(
                "reconcile.card",
                id=str(card.id),
                asset=card.asset,
                session_type=card.session_type,
                committed=committed,
                reason=reason,
            )
            print(
                f"{'OK ' if committed else '-- '}{card.asset:10s} {card.session_type:14s} {reason}"
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
