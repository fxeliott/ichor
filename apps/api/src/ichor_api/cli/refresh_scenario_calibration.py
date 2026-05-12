"""Refresh `scenario_calibration_bins` for all (asset, session_type) pairs.

Runs every Sunday 00:30 UTC (systemd timer `ichor-scenario-calibration.timer`)
per ADR-085 §"Calibration weekly refresh". For each of the 6 carded assets
× 5 session types = 30 calibration rows, calls
`services.scenario_calibration.compute_calibration_bins` which reads
`polygon_intraday` realized session-window returns (rolling 252 trading
days, EWMA λ=0.94 RiskMetrics) and writes a new row.

Append-only — the PK includes `computed_at` so concurrent writes are safe
and history is preserved. Pass-6 prompt reads `ORDER BY computed_at DESC
LIMIT 1` to pick the latest calibration.

Usage :
  python -m ichor_api.cli.refresh_scenario_calibration [--dry-run]

`--dry-run` reports what would be written without committing.

Implements W105b (the only remaining sub-wave of ADR-085 W105 batch).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

import structlog

from ..cli.run_session_cards_batch import _DEFAULT_ASSETS
from ..db import get_engine, get_sessionmaker
from ..services.scenario_calibration import (
    CONFIDENCE_FLOOR,
    compute_calibration_bins,
    persist_calibration,
)

log = structlog.get_logger(__name__)

# All 5 canonical session_types from ichor_brain.types.SessionType.
_SESSION_TYPES: tuple[str, ...] = (
    "pre_londres",
    "pre_ny",
    "ny_mid",
    "ny_close",
    "event_driven",
)


async def _run(*, dry_run: bool) -> int:
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    n_committed = 0
    n_skipped = 0
    n_low_sample = 0

    async with sm() as session:
        for asset in _DEFAULT_ASSETS:
            for session_type in _SESSION_TYPES:
                try:
                    result = await compute_calibration_bins(
                        session,
                        asset,
                        session_type,  # type: ignore[arg-type]
                        now=now,
                    )
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "calibration.compute_failed",
                        asset=asset,
                        session_type=session_type,
                        error=str(e),
                    )
                    print(f"-- {asset:12s} {session_type:14s} ERROR: {e}", file=sys.stderr)
                    n_skipped += 1
                    continue

                flagged = result.sample_n < CONFIDENCE_FLOOR
                if flagged:
                    n_low_sample += 1

                if dry_run:
                    print(
                        f"-- {asset:12s} {session_type:14s} "
                        f"sigma_pips={result.sigma_pips:.2f} "
                        f"n={result.sample_n}{' (low-sample)' if flagged else ''} (dry-run)"
                    )
                else:
                    row = await persist_calibration(session, result, computed_at=now)
                    print(
                        f"OK {asset:12s} {session_type:14s} "
                        f"sigma_pips={result.sigma_pips:.2f} "
                        f"n={result.sample_n}{' (low-sample fallback)' if flagged else ''}"
                    )
                    log.info(
                        "calibration.persisted",
                        asset=row.asset,
                        session_type=row.session_type,
                        computed_at=row.computed_at.isoformat(),
                        sigma_pips=result.sigma_pips,
                        sample_n=row.sample_n,
                        low_sample_fallback=flagged,
                    )
                    n_committed += 1

        if not dry_run and n_committed > 0:
            await session.commit()

    print(
        f"\n{n_committed} rows committed, {n_low_sample} low-sample fallback, "
        f"{n_skipped} errors {'(DRY-RUN)' if dry_run else ''}"
    )
    return 0 if n_skipped == 0 else 1


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="refresh_scenario_calibration",
        description=(
            "Refresh scenario_calibration_bins for all 6-asset × 5-session pairs "
            "(W105b ADR-085 weekly Sunday 00:30 UTC)."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="report without committing")
    args = parser.parse_args(argv)
    try:
        return await _run(dry_run=args.dry_run)
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
