"""Dry-run collectors on demand — useful for manual smoke tests.

Run:
  python -m ichor_api.cli.run_collectors rss
  python -m ichor_api.cli.run_collectors polymarket
  python -m ichor_api.cli.run_collectors all

Prints a compact summary (counts + sample items) without persisting to the
database. Once collectors land in the cron schedule, this CLI stays useful
as a "is this feed still live?" probe (e.g. inside RUNBOOK-005).
"""

from __future__ import annotations

import asyncio
import sys

from ..collectors.polymarket import poll_all as poll_polymarket
from ..collectors.rss import poll_all as poll_rss


async def _run_rss() -> int:
    items = await poll_rss()
    print(f"RSS  · {len(items)} items pulled")
    for it in items[:5]:
        ts = it.published_at.isoformat(timespec="minutes")
        print(f"  [{it.source:20s}] {ts}  {it.title[:90]}")
    if len(items) > 5:
        print(f"  ... and {len(items) - 5} more")
    return 0 if items else 1


async def _run_polymarket() -> int:
    snaps = await poll_polymarket()
    print(f"Polymarket · {len(snaps)} markets pulled")
    for s in snaps:
        yes = f"{s.yes_price:.2f}" if s.yes_price is not None else "n/a"
        vol = f"${s.volume_usd:,.0f}" if s.volume_usd is not None else "n/a"
        print(f"  [{s.slug[:40]:40s}] yes={yes}  vol={vol}  {s.question[:60]}")
    return 0 if snaps else 1


async def _main(target: str) -> int:
    if target == "rss":
        return await _run_rss()
    if target == "polymarket":
        return await _run_polymarket()
    if target == "all":
        rc1 = await _run_rss()
        print()
        rc2 = await _run_polymarket()
        return rc1 | rc2
    print(f"unknown target: {target!r} (expected: rss | polymarket | all)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) >= 2 else "all"
    sys.exit(asyncio.run(_main(target)))
