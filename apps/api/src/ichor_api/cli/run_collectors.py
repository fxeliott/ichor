"""Run collectors on demand — for manual smoke tests AND scheduled cron jobs.

Run:
  python -m ichor_api.cli.run_collectors rss              # dry-run, print only
  python -m ichor_api.cli.run_collectors polymarket
  python -m ichor_api.cli.run_collectors all
  python -m ichor_api.cli.run_collectors rss --persist    # write to Postgres
  python -m ichor_api.cli.run_collectors all --persist

The dry-run mode is the safe default; --persist must be opt-in. Cron units
should always pass --persist.
"""

from __future__ import annotations

import asyncio
import sys

from ..collectors.polymarket import poll_all as poll_polymarket
from ..collectors.rss import poll_all as poll_rss
from ..db import get_engine, get_sessionmaker


async def _run_rss(*, persist: bool) -> int:
    items = await poll_rss()
    print(f"RSS  · {len(items)} items pulled")
    for it in items[:5]:
        ts = it.published_at.isoformat(timespec="minutes")
        print(f"  [{it.source:20s}] {ts}  {it.title[:90]}")
    if len(items) > 5:
        print(f"  ... and {len(items) - 5} more")
    if persist:
        from ..collectors.persistence import persist_news_items

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_news_items(session, items)
        print(f"RSS  · persisted {inserted} new rows ({len(items) - inserted} dedup)")
    return 0 if items else 1


async def _run_polymarket(*, persist: bool) -> int:
    snaps = await poll_polymarket()
    print(f"Polymarket · {len(snaps)} markets pulled")
    for s in snaps:
        yes = f"{s.yes_price:.2f}" if s.yes_price is not None else "n/a"
        vol = f"${s.volume_usd:,.0f}" if s.volume_usd is not None else "n/a"
        print(f"  [{s.slug[:40]:40s}] yes={yes}  vol={vol}  {s.question[:60]}")
    if persist:
        from ..collectors.persistence import persist_polymarket_snapshots

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_polymarket_snapshots(session, snaps)
        print(f"Polymarket · persisted {inserted} snapshots")
    return 0 if snaps else 1


async def _main(target: str, *, persist: bool) -> int:
    try:
        if target == "rss":
            return await _run_rss(persist=persist)
        if target == "polymarket":
            return await _run_polymarket(persist=persist)
        if target == "all":
            rc1 = await _run_rss(persist=persist)
            print()
            rc2 = await _run_polymarket(persist=persist)
            return rc1 | rc2
        print(
            f"unknown target: {target!r} (expected: rss | polymarket | all)",
            file=sys.stderr,
        )
        return 2
    finally:
        if persist:
            await get_engine().dispose()


if __name__ == "__main__":
    args = sys.argv[1:]
    persist = "--persist" in args
    args = [a for a in args if a != "--persist"]
    target = args[0] if args else "all"
    sys.exit(asyncio.run(_main(target, persist=persist)))
