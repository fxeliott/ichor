"""r144 cron CLI — FRED ALFRED actuals reconciler.

Backfills `economic_events.actual` for US events via FRED ALFRED
first-vintage values. Idempotent : already-populated events are
excluded from the SELECT filter (preserves first-vintage even if FRED
issues T+24h revisions).

Cadence (4x/day, offset 15 min from FF collector fires 03/09/15/21h
to ensure FF has upserted the event row before reconciler queries) :

    OnCalendar=*-*-* 01,07,13,19:15:00 Europe/Paris

Gated by feature flag `actuals_reconciler_enabled` (default False ;
set to true via `UPDATE feature_flags ... ` once Eliot is ready to
start the cron).

Voie D : no `import anthropic`, no paid API ; only httpx.AsyncClient
to api.stlouisfed.org (shared key with existing FRED collectors).

Usage :
  python -m ichor_api.cli.run_economic_event_actuals_reconcile
                                                  [--dry-run]
                                                  [--lookback-days N]
                                                  [--settle-minutes N]
                                                  [--currency USD]

ADR refs : ADR-099 Impl(r144).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..config import get_settings
from ..db import get_engine, get_sessionmaker
from ..services.economic_event_actuals_reconciler import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SETTLE_MINUTES,
    reconcile_actuals,
)
from ..services.feature_flags import is_enabled

log = structlog.get_logger(__name__)

_FEATURE_FLAG_NAME = "actuals_reconciler_enabled"


async def _run(
    *,
    dry_run: bool,
    lookback_days: int,
    settle_minutes: int,
    currency: str,
) -> int:
    """Run the reconciler once. Returns shell exit code.

    Exit codes :
      0 : success (zero or more events updated)
      1 : feature flag is OFF — skipped cleanly
      2 : ICHOR_API_FRED_API_KEY missing — cannot fetch
    """
    sm = get_sessionmaker()
    settings = get_settings()

    # Feature flag check — fail-closed if disabled OR not set.
    async with sm() as flag_session:
        enabled = await is_enabled(flag_session, _FEATURE_FLAG_NAME)
    if not enabled:
        print(
            f"feature flag {_FEATURE_FLAG_NAME!r} is OFF — skipping "
            "FRED ALFRED actuals reconciliation (set to true via "
            "UPDATE feature_flags ... once you're ready to start "
            "daily reconciliation)."
        )
        return 1

    api_key = settings.fred_api_key
    if not api_key:
        # ICHOR_API_FRED_API_KEY empty — same guard as existing FRED CLI
        # callers (e.g. apps/api/src/ichor_api/cli/run_collectors.py).
        # Print and exit cleanly so the cron job doesn't loop-fail.
        print(
            "ICHOR_API_FRED_API_KEY is empty — cannot reach FRED ALFRED. "
            "Set the env var via /etc/ichor/api.env and re-deploy."
        )
        return 2

    print(
        f"== actuals reconciler · {currency} · "
        f"lookback={lookback_days}d settle={settle_minutes}m "
        f"dry_run={dry_run} ==",
    )

    async with sm() as session:
        result = await reconcile_actuals(
            session,
            api_key=api_key,
            lookback_days=lookback_days,
            settle_minutes=settle_minutes,
            currency=currency,
            dry_run=dry_run,
        )

    log.info(
        "alfred.reconcile.complete",
        examined=result.examined,
        updated=result.updated,
        skipped_unmapped=result.skipped_unmapped,
        skipped_fetch_failed=result.skipped_fetch_failed,
        skipped_no_value=result.skipped_no_value,
        dry_run=dry_run,
        currency=currency,
        lookback_days=lookback_days,
    )

    print(
        f"OK · examined={result.examined} "
        f"updated={result.updated} "
        f"unmapped={result.skipped_unmapped} "
        f"fetch_failed={result.skipped_fetch_failed} "
        f"no_value={result.skipped_no_value}",
    )
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(
            dry_run=args.dry_run,
            lookback_days=args.lookback_days,
            settle_minutes=args.settle_minutes,
            currency=args.currency.upper(),
        )
    finally:
        await get_engine().dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "FRED ALFRED reconciler — populate economic_events.actual "
            "for past US events via first-vintage values. Cron-friendly, "
            "idempotent, feature-flag-gated."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Smoke test : query + log but do NOT write to the DB.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=(
            "Days of past events to consider (default "
            f"{DEFAULT_LOOKBACK_DAYS}). Events older than this are "
            "ignored to save API quota."
        ),
    )
    parser.add_argument(
        "--settle-minutes",
        type=int,
        default=DEFAULT_SETTLE_MINUTES,
        help=(
            "Wait this many minutes past scheduled_at before attempting "
            f"reconciliation (default {DEFAULT_SETTLE_MINUTES}). Gives "
            "BLS/BEA → FRED ingestion lag a margin."
        ),
    )
    parser.add_argument(
        "--currency",
        default="USD",
        help=(
            "Currency filter (default USD). ALFRED is US-only ; other "
            "currencies are r145+ provider research."
        ),
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
