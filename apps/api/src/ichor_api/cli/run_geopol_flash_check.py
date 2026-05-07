"""CLI runner for GEOPOL_FLASH alert (Phase D.5.b).

Daily 23:30 Paris (after the AI-GPR collector lands the day's value
at 23h Paris) :
  1. Pull recent ai_gpr observations from `gpr_observations`
  2. Compute z-score of latest reading vs trailing 30d distribution
  3. Fire `GEOPOL_FLASH` if |z| >= 2.0

Usage :
    python -m ichor_api.cli.run_geopol_flash_check          # dry-run
    python -m ichor_api.cli.run_geopol_flash_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.geopol_flash_check import evaluate_geopol_flash

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_geopol_flash(session, persist=persist)
        if persist:
            await session.commit()

    print(f"geopol_flash · {result.note} (n_history={result.n_history})")
    if result.alert_fired:
        print(
            f"geopol_flash · ALERT (z={result.z_score:+.2f}) "
            f"havens_signaled={','.join(result.havens_signaled)}"
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
    parser = argparse.ArgumentParser(prog="run_geopol_flash_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
