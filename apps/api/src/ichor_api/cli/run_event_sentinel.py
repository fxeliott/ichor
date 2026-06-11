"""S03 Chantier D — pre-announcement sentinel cron CLI.

Scans ``economic_events`` for high-impact prints inside the next horizon
(default 60 min) on the traded universe's currencies and emits
``ECO_EVENT_IMMINENT`` (critical → web-push) via the canonical pipeline.
Event-cluster dedup lives in ``alerts/event_sentinel.py`` — re-runs are
idempotent.

Usage :

    python -m ichor_api.cli.run_event_sentinel [--dry-run]
                                               [--horizon-minutes N]

Exit codes :

    0 : success (zero or more alerts emitted — a quiet calendar is 0)
    3 : DB connection failure — cron infra issue (retry next tick)

Voie D : zero LLM call — pure SQL + datetime arithmetic.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.alerts_runner import check_upcoming_economic_events

log = structlog.get_logger(__name__)

DEFAULT_HORIZON_MINUTES = 60


async def _run(*, dry_run: bool, horizon_minutes: int) -> int:
    sm = get_sessionmaker()
    try:
        async with sm() as session:
            persisted = await check_upcoming_economic_events(
                session, horizon_minutes=horizon_minutes, notify=not dry_run
            )
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
    except Exception as exc:
        print(f"DB failure during event-sentinel scan : {exc!s}. Cron will retry next tick.")
        return 3

    print(
        f"event-sentinel · horizon={horizon_minutes}min · "
        f"{len(persisted)} imminent-event alerts "
        f"{'(dry-run, rolled back)' if dry_run else 'persisted'}"
    )
    for hit in persisted:
        print(
            f"  [{hit.source_payload.get('currency')}] "
            f"T-{hit.metric_value:.0f}min — {hit.source_payload.get('titles')}"
        )
    log.info(
        "event_sentinel.complete",
        n_alerts=len(persisted),
        horizon_minutes=horizon_minutes,
        dry_run=dry_run,
        keys=[h.source_payload.get("event_key") for h in persisted],
    )
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(dry_run=args.dry_run, horizon_minutes=args.horizon_minutes)
    finally:
        await get_engine().dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Pre-announcement sentinel — warn BEFORE high-impact calendar "
            "events on the traded universe's currencies (S03 'être prévenu "
            "de toutes les annonces'). Descriptive only, never directional."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate + print but roll back — nothing persisted.",
    )
    parser.add_argument(
        "--horizon-minutes",
        type=int,
        default=DEFAULT_HORIZON_MINUTES,
        help=f"Forward window to scan (default {DEFAULT_HORIZON_MINUTES}).",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
