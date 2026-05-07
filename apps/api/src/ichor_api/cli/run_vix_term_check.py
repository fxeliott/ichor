"""CLI runner for VIX_TERM_INVERSION alert (Phase E innovation).

Daily 22h Paris (post NY close, after FRED extended collector lands
the day's VIXCLS + VXVCLS readings):
  1. Pull latest VIXCLS (1M IV) + VXVCLS (3M IV) from fred_observations
  2. Compute ratio = VIXCLS / VXVCLS
  3. Fire `VIX_TERM_INVERSION` if ratio > 1.0 (backwardation)
  4. Tag regime ('contango' | 'neutral' | 'backwardation' | 'backwardation_shock')

Usage :
    python -m ichor_api.cli.run_vix_term_check          # dry-run
    python -m ichor_api.cli.run_vix_term_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.vix_term_check import evaluate_vix_term_inversion

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_vix_term_inversion(session, persist=persist)
        if persist:
            await session.commit()

    print(result.note)
    if result.alert_fired:
        print(
            f"vix_term · ALERT (regime={result.regime}, ratio={result.ratio:.4f})"
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
    parser = argparse.ArgumentParser(prog="run_vix_term_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
