"""CLI runner for TREASURY_VOL_SPIKE alert (Phase E innovation, MOVE proxy).

Daily 23:00 Paris :
  1. Pull ~2y of DGS10 from FRED
  2. Compute 30d rolling realized vol (× √252 annualized)
  3. Z-score current vs trailing 252d distribution
  4. Fire `TREASURY_VOL_SPIKE` if |z| >= 2.0
  5. Tag regime ('stress' z>0 / 'complacency' z<0)

Usage :
    python -m ichor_api.cli.run_treasury_vol_check          # dry-run
    python -m ichor_api.cli.run_treasury_vol_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.treasury_vol_check import evaluate_treasury_vol

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_treasury_vol(session, persist=persist)
        if persist:
            await session.commit()

    print(f"treasury_vol · {result.note}")
    if result.alert_fired:
        print(
            f"treasury_vol · ALERT (z={result.z_score:+.2f} regime={result.regime}) "
            f"related={','.join(result.related_assets)}"
        )
    return 0


async def _main(persist: bool) -> int:
    """Async entrypoint with engine disposal in the same loop (cf ADR-024)."""
    try:
        return await run(persist=persist)
    finally:
        if persist:
            await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_treasury_vol_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
