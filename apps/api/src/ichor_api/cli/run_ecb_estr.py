"""ADR-090 P0 step-4 cron — ECB €STR daily ingestion CLI.

Daily 16:45 Paris cron (15 min after Bund 10Y at 16:30 ; matches the
ADR-090 step-4 backlog refinement r32b proposed schedule).

Fetches the daily €STR (Euro Short-Term Rate) volume-weighted trimmed
mean rate from ECB Data Portal SDMX (collector
`services.collectors.ecb_estr`), inserts new rows into
`estr_observations` via INSERT ... ON CONFLICT DO NOTHING. Batched
5000 chunks per asyncpg 32767 param limit (5 cols × 5000 = 25000).

ECB publishes €STR each TARGET business day at ~08:05 CEST. Scheduling
at 16:45 gives a generous safety margin and arrives after Bund 10Y
ingestion at 16:30 — the data-pool render for EUR_USD then has both
EUR signals fresh on the same day.

Gated by feature flag `ecb_estr_collector_enabled` (default False —
fail-closed). Round-34 ship : feature flag is set to `true @ 100`
at deploy time.

Pattern mirrors r33 `cli/run_bundesbank_bund.py`.

Usage :
  python -m ichor_api.cli.run_ecb_estr [--dry-run]
                                       [--batch-size N]
                                       [--incremental]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..collectors.ecb_estr import fetch_estr_rates
from ..db import get_engine, get_sessionmaker
from ..models import EstrObservation
from ..services.feature_flags import is_enabled

log = structlog.get_logger(__name__)

_FEATURE_FLAG_NAME = "ecb_estr_collector_enabled"
_DEFAULT_BATCH_SIZE = 5000
# Incremental fetch window — pull the last 30 days if --incremental
# is set, otherwise full history. 30 days covers cron downtime up to
# ~6 weeks of misses (€STR ≈ 5 obs / week).
_INCREMENTAL_WINDOW_DAYS = 30


async def _latest_observation_date(session: Any) -> date | None:
    """Return the most-recent observation_date in estr_observations,
    or None if the table is empty (cold-start)."""
    stmt = (
        select(EstrObservation.observation_date)
        .order_by(EstrObservation.observation_date.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _ingest_batched(
    session: Any,
    *,
    rows: list[dict[str, Any]],
    batch_size: int,
) -> tuple[int, int]:
    """Insert rows in chunks. Returns (n_attempted, n_chunks).

    Same pattern as `run_bundesbank_bund._ingest_batched`. ON CONFLICT
    (observation_date) DO NOTHING is the idempotency contract.
    """
    n_attempted = len(rows)
    n_chunks = 0
    for i in range(0, n_attempted, batch_size):
        batch = rows[i : i + batch_size]
        stmt = insert(EstrObservation).values(batch)
        stmt = stmt.on_conflict_do_nothing(index_elements=["observation_date"])
        await session.execute(stmt)
        n_chunks += 1
    return n_attempted, n_chunks


async def _run(*, dry_run: bool, batch_size: int, incremental: bool) -> int:
    sm = get_sessionmaker()

    # Feature flag check — fail-closed if disabled OR not set.
    async with sm() as flag_session:
        enabled = await is_enabled(flag_session, _FEATURE_FLAG_NAME)
    if not enabled:
        print(
            f"feature flag {_FEATURE_FLAG_NAME!r} is OFF — skipping "
            "€STR ingestion (set to true via UPDATE feature_flags "
            "... once you're ready to start daily collection)."
        )
        return 0

    # Decide fetch window. --incremental queries the DB for the most
    # recent observation_date and asks ECB for everything since then ;
    # otherwise full history (~1700 rows since 2019-10-01 inception).
    start_period: date | None = None
    if incremental:
        async with sm() as q_session:
            latest = await _latest_observation_date(q_session)
        if latest is not None:
            # Overlap by 30 days to catch any back-revisions the ECB
            # might publish (rare for €STR but defense-in-depth).
            start_period = latest - timedelta(days=_INCREMENTAL_WINDOW_DAYS)
            print(f"incremental mode : fetching from {start_period} (DB latest = {latest})")
        else:
            print("incremental mode requested but DB empty — falling back to full history")

    print("== ecb_estr · fetch starting ==")
    try:
        obs = await fetch_estr_rates(start_period=start_period)
    except Exception as exc:  # noqa: BLE001 — collector is best-effort
        log.warning("ecb_estr.fetch_failed_top", error=str(exc))
        print(f"fetch failed : {exc}", file=sys.stderr)
        return 1

    if not obs:
        print("no observations returned from ECB Data Portal (collector returned [])")
        return 0

    print(f"fetched {len(obs)} observation(s) from ECB Data Portal")
    # ECB Data Portal serves ASCENDING dates (oldest first), so :
    #   obs[0]  = oldest in time
    #   obs[-1] = newest in time
    # (Same ordering as Bundesbank — careful labeling in print line.)
    print(
        f"  oldest = {obs[0].observation_date} : {float(obs[0].rate_pct):.4f}%  "
        f"newest = {obs[-1].observation_date} : {float(obs[-1].rate_pct):.4f}%"
    )

    if dry_run:
        print("DRY-RUN : skipping DB INSERT")
        return 0

    rows = [
        {
            "observation_date": o.observation_date,
            "rate_pct": float(o.rate_pct),
            "source_url": o.source_url,
            "fetched_at": o.fetched_at,
        }
        for o in obs
    ]

    async with sm() as session:
        n_attempted, n_chunks = await _ingest_batched(session, rows=rows, batch_size=batch_size)
        await session.commit()

    log.info(
        "ecb_estr.ingestion_complete",
        n_attempted=n_attempted,
        n_chunks=n_chunks,
        newest_date=str(obs[-1].observation_date),
        newest_pct=float(obs[-1].rate_pct),
    )
    print(
        f"OK : {n_attempted} row(s) attempted across {n_chunks} batch(es) "
        f"(ON CONFLICT DO NOTHING on observation_date — duplicates silently skipped)"
    )
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            incremental=args.incremental,
        )
    finally:
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_ecb_estr",
        description=(
            "ADR-090 P0 step-4 — daily €STR rate ingestion. Fetches "
            "the daily volume-weighted trimmed mean rate from ECB "
            "Data Portal SDMX and upserts into estr_observations. "
            f"Gated by feature flag {_FEATURE_FLAG_NAME!r}."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but skip DB INSERT (safe verification).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_DEFAULT_BATCH_SIZE,
        help=(
            f"Rows per INSERT batch (default {_DEFAULT_BATCH_SIZE} ; max "
            "~6553 due to asyncpg 32767 query-arg limit / 5 cols)."
        ),
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help=(
            "Fetch only rows since the most recent observation_date in "
            "the DB minus 30-day overlap (saves bandwidth). Default = "
            "full history."
        ),
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
