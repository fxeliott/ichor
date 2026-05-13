"""ADR-090 P0 step-1 cron — Bundesbank Bund 10Y daily ingestion CLI.

Daily 16:30 Paris cron. Fetches the full Bund 10Y daily series from
Bundesbank SDMX (collector `services.collectors.bundesbank_bund`),
inserts new rows into `bund_10y_observations` via INSERT ... ON
CONFLICT DO NOTHING. Batched in chunks of 5000 to respect the asyncpg
parameter limit (32767 / 5 cols = 6553 max, 5000 is safe).

Bundesbank refreshes the daily fixing once per business day around
16:00 CEST (after the German bond market close). Scheduling at 16:30
gives a 30-min safety margin and avoids overlap with W116b PBS
(Sunday 18:00) + W116c addendum generator (Sunday 19:00).

Gated by feature flag `bundesbank_bund_collector_enabled` (default
False — must be set explicitly via UPDATE feature_flags ... once
Eliot is ready to start daily ingestion). Round-33 ship : feature
flag is set to `true @ 100` at deploy time so the first cron fire
post-deploy ingests cleanly.

Round-32c fixes baked in :
  - URL has NO `?format=csvdata` (Bundesbank rejects with HTTP 406).
  - CSV parser uses `delimiter=';'` (SDMX-CSV 1.0.0 spec).

Usage :
  python -m ichor_api.cli.run_bundesbank_bund [--dry-run]
                                              [--batch-size N]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import insert

from ..collectors.bundesbank_bund import fetch_bund_yields
from ..db import get_engine, get_sessionmaker
from ..models import BundYieldObservation
from ..services.feature_flags import is_enabled

log = structlog.get_logger(__name__)

_FEATURE_FLAG_NAME = "bundesbank_bund_collector_enabled"
_DEFAULT_BATCH_SIZE = 5000


async def _ingest_batched(
    session: Any,
    *,
    rows: list[dict[str, Any]],
    batch_size: int,
) -> tuple[int, int]:
    """Insert rows in chunks. Returns (n_attempted, n_inserted_estimate).

    Postgres asyncpg has a 32767 query-arg limit. With 5 columns per
    insert, max batch = 6553 ; we use 5000 as a safe default.

    `ON CONFLICT (observation_date) DO NOTHING` skips duplicates on
    re-run (idempotent).
    """
    n_attempted = len(rows)
    n_chunks = 0
    for i in range(0, n_attempted, batch_size):
        batch = rows[i : i + batch_size]
        stmt = insert(BundYieldObservation).values(batch)
        stmt = stmt.on_conflict_do_nothing(index_elements=["observation_date"])
        await session.execute(stmt)
        n_chunks += 1
    return n_attempted, n_chunks


async def _run(*, dry_run: bool, batch_size: int) -> int:
    sm = get_sessionmaker()

    # Feature flag check — fail-closed if disabled OR not set.
    async with sm() as flag_session:
        enabled = await is_enabled(flag_session, _FEATURE_FLAG_NAME)
    if not enabled:
        print(
            f"feature flag {_FEATURE_FLAG_NAME!r} is OFF — skipping "
            "Bund 10Y ingestion (set to true via UPDATE feature_flags "
            "... once you're ready to start daily collection)."
        )
        return 0

    # Fetch via the collector (round-32c fixes : URL OK + delimiter ;).
    print("== bundesbank_bund · fetch starting ==")
    try:
        obs = await fetch_bund_yields()
    except Exception as exc:  # noqa: BLE001 — collector is best-effort
        log.warning("bundesbank_bund.fetch_failed_top", error=str(exc))
        print(f"fetch failed : {exc}", file=sys.stderr)
        return 1

    if not obs:
        print("no observations returned from Bundesbank (collector returned [])")
        return 0

    print(f"fetched {len(obs)} observation(s) from Bundesbank")
    # Bundesbank SDMX returns ASCENDING dates (oldest first), so :
    #   obs[0]  = oldest in time
    #   obs[-1] = newest in time
    # Round-34 cosmetic fix : the r33 print line had labels inverted
    # (called obs[0] "latest"). Mirror the r34 €STR CLI labeling.
    print(
        f"  oldest = {obs[0].observation_date} : {float(obs[0].yield_pct):.4f}%  "
        f"newest = {obs[-1].observation_date} : {float(obs[-1].yield_pct):.4f}%"
    )

    if dry_run:
        print("DRY-RUN : skipping DB INSERT")
        return 0

    # Materialize into dict rows for batched insert. observation_date is
    # the natural key ; ON CONFLICT (observation_date) DO NOTHING makes
    # the operation idempotent across cron re-runs.
    rows = [
        {
            "observation_date": o.observation_date,
            "yield_pct": float(o.yield_pct),
            "source_url": o.source_url,
            "fetched_at": o.fetched_at,
        }
        for o in obs
    ]

    async with sm() as session:
        n_attempted, n_chunks = await _ingest_batched(session, rows=rows, batch_size=batch_size)
        await session.commit()

    log.info(
        "bundesbank_bund.ingestion_complete",
        n_attempted=n_attempted,
        n_chunks=n_chunks,
        newest_date=str(obs[-1].observation_date),
        newest_pct=float(obs[-1].yield_pct),
    )
    print(
        f"OK : {n_attempted} row(s) attempted across {n_chunks} batch(es) "
        f"(ON CONFLICT DO NOTHING on observation_date — duplicates silently skipped)"
    )
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(dry_run=args.dry_run, batch_size=args.batch_size)
    finally:
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_bundesbank_bund",
        description=(
            "ADR-090 P0 step-1 — daily Bund 10Y yield ingestion. Fetches "
            "the full series from Bundesbank SDMX and upserts into "
            "bund_10y_observations. Gated by feature flag "
            f"{_FEATURE_FLAG_NAME!r}."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but skip DB INSERT (for safe verification).",
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
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
