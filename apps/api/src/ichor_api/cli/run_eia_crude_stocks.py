"""ADR-107 cron — EIA weekly petroleum crude-stocks ingestion CLI.

Weekly Thursday cron (after the EIA Weekly Petroleum Status Report,
released Wed 10:30 ET). Fetches weekly crude-stock series from EIA
OpenData v2 (collector ``collectors.eia_petroleum``), inserts new rows
into ``eia_crude_stocks`` via INSERT ... ON CONFLICT DO NOTHING on
``(series_id, observation_date)``.

Feeds the theme_classifier ``supply_demand`` driver (Eliot Fathom
transcript étape 1, the 8th driver). Until rows exist,
``_is_supply_demand_elevated`` returns False → baseline 0.2 (graceful
honest absence, zero behaviour regression — same dormant-until-data
pattern as the other collectors).

Gated by feature flag ``eia_crude_stocks_collector_enabled`` (default
False — fail-closed). REQUIRES ``EIA_API_KEY`` in the process env
(systemd ``EnvironmentFile=/etc/ichor/api.env``) — EIA has no
anonymous tier. Without the key the collector returns [] gracefully.

Pattern mirrors r34 ``cli/run_ecb_estr.py``.

Usage :
  python -m ichor_api.cli.run_eia_crude_stocks [--dry-run]
                                               [--batch-size N]
                                               [--last-n-obs N]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import insert

from ..collectors.eia_petroleum import fetch_weekly_petroleum_stocks
from ..config import get_settings
from ..db import get_engine, get_sessionmaker
from ..models import EiaCrudeStockObservation
from ..services.feature_flags import is_enabled

log = structlog.get_logger(__name__)

_FEATURE_FLAG_NAME = "eia_crude_stocks_collector_enabled"
_DEFAULT_BATCH_SIZE = 5000
_DEFAULT_LAST_N_OBS = 60
"""60 weekly obs ≈ 14 months — comfortably backfills the rolling
365-day window the supply_demand driver reads (~52 weekly obs), with
margin so the percentile rank has ≥30 weekly Δ from the first cron."""
_EIA_FALLBACK_SOURCE_URL = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"


def _parse_period_to_date(period: str) -> date | None:
    """Weekly EIA periods are ISO 'YYYY-MM-DD' (week-ending). Return a
    ``date`` or None for anything that isn't a full ISO date (defensive
    — a monthly 'YYYY-MM' period would be skipped rather than raise)."""
    try:
        return date.fromisoformat(period)
    except ValueError:
        return None


async def _ingest_batched(
    session: Any,
    *,
    rows: list[dict[str, Any]],
    batch_size: int,
) -> tuple[int, int]:
    """Insert rows in chunks. Returns (n_attempted, n_chunks). ON
    CONFLICT (series_id, observation_date) DO NOTHING = idempotency."""
    n_attempted = len(rows)
    n_chunks = 0
    for i in range(0, n_attempted, batch_size):
        batch = rows[i : i + batch_size]
        stmt = insert(EiaCrudeStockObservation).values(batch)
        stmt = stmt.on_conflict_do_nothing(index_elements=["series_id", "observation_date"])
        await session.execute(stmt)
        n_chunks += 1
    return n_attempted, n_chunks


async def _run(*, dry_run: bool, batch_size: int, last_n_obs: int) -> int:
    sm = get_sessionmaker()

    # Feature flag — fail-closed if disabled OR not set.
    async with sm() as flag_session:
        enabled = await is_enabled(flag_session, _FEATURE_FLAG_NAME)
    if not enabled:
        print(
            f"feature flag {_FEATURE_FLAG_NAME!r} is OFF — skipping EIA "
            "crude-stocks ingestion (set true via UPDATE feature_flags "
            "once EIA_API_KEY is provisioned and you're ready)."
        )
        return 0

    settings = get_settings()
    if not settings.eia_api_key:
        print(
            "EIA_API_KEY is empty — EIA has no anonymous tier, the "
            "collector returns []. Set EIA_API_KEY in /etc/ichor/api.env.",
            file=sys.stderr,
        )
        return 0

    print("== eia_crude_stocks · fetch starting ==")
    try:
        obs = await fetch_weekly_petroleum_stocks(
            api_key=settings.eia_api_key,
            last_n_obs=last_n_obs,
        )
    except Exception as exc:  # noqa: BLE001 — collector is best-effort
        log.warning("eia_crude_stocks.fetch_failed_top", error=str(exc))
        print(f"fetch failed : {exc}", file=sys.stderr)
        return 1

    if not obs:
        print("no observations returned from EIA OpenData (collector returned [])")
        return 0

    rows: list[dict[str, Any]] = []
    skipped = 0
    for o in obs:
        obs_date = _parse_period_to_date(o.period)
        if obs_date is None or not o.series_id:
            skipped += 1
            continue
        rows.append(
            {
                "series_id": o.series_id,
                "observation_date": obs_date,
                "value": o.value,
                "unit": o.unit,
                "source_url": o.source_url or _EIA_FALLBACK_SOURCE_URL,
                "fetched_at": o.fetched_at,
            }
        )

    print(
        f"fetched {len(obs)} observation(s) from EIA OpenData ({skipped} skipped : non-date period)"
    )
    if rows:
        newest = max(rows, key=lambda r: r["observation_date"])
        print(f"  newest = {newest['series_id']} {newest['observation_date']} : {newest['value']}")

    if dry_run:
        print("DRY-RUN : skipping DB INSERT")
        return 0

    if not rows:
        print("no parseable rows to insert")
        return 0

    async with sm() as session:
        n_attempted, n_chunks = await _ingest_batched(session, rows=rows, batch_size=batch_size)
        await session.commit()

    log.info(
        "eia_crude_stocks.ingestion_complete",
        n_attempted=n_attempted,
        n_chunks=n_chunks,
    )
    print(
        f"OK : {n_attempted} row(s) attempted across {n_chunks} batch(es) "
        "(ON CONFLICT DO NOTHING on (series_id, observation_date))"
    )
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            last_n_obs=args.last_n_obs,
        )
    finally:
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_eia_crude_stocks",
        description=(
            "ADR-107 — weekly EIA petroleum crude-stocks ingestion. "
            "Fetches weekly stock series from EIA OpenData v2 and upserts "
            f"into eia_crude_stocks. Gated by {_FEATURE_FLAG_NAME!r} + "
            "requires EIA_API_KEY."
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
        help=f"Rows per INSERT batch (default {_DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--last-n-obs",
        type=int,
        default=_DEFAULT_LAST_N_OBS,
        help=(
            f"Weekly observations per series to fetch (default "
            f"{_DEFAULT_LAST_N_OBS} ≈ 14 months ; backfills the 365-day "
            "supply_demand window with margin)."
        ),
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
