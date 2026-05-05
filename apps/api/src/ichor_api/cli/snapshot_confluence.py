"""CLI : snapshot the current /v1/confluence reading for the 8 phase-1 assets.

Designed to be run by a systemd timer (nightly 23:30 UTC for example) so
the /confluence dashboard can show a sparkline of how each asset's score
evolved.

Usage :
  python -m ichor_api.cli.snapshot_confluence
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from ..db import get_sessionmaker
from ..models import ConfluenceHistory
from ..services.confluence_engine import assess_confluence

log = structlog.get_logger(__name__)


_PHASE1_ASSETS = (
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
)


async def _run() -> int:
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    n_persisted = 0
    async with sm() as session:
        for asset in _PHASE1_ASSETS:
            try:
                report = await assess_confluence(session, asset)
            except Exception as e:
                log.error("confluence.assess_failed", asset=asset, err=str(e))
                continue
            drivers_blob = [
                {
                    "factor": d.factor,
                    "contribution": d.contribution,
                    "evidence": d.evidence,
                    "source": d.source,
                }
                for d in report.drivers
            ]
            session.add(
                ConfluenceHistory(
                    captured_at=now,
                    created_at=now,
                    asset=asset,
                    score_long=report.score_long,
                    score_short=report.score_short,
                    score_neutral=report.score_neutral,
                    dominant_direction=report.dominant_direction,
                    confluence_count=report.confluence_count,
                    n_drivers=len(report.drivers),
                    drivers=drivers_blob,
                )
            )
            n_persisted += 1
        await session.commit()
    log.info("confluence.snapshot.done", n=n_persisted, captured_at=now.isoformat())
    print(f"OK · {n_persisted}/8 confluence snapshots persisted at {now:%Y-%m-%d %H:%M UTC}")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
