"""CLI runner for YIELD_CURVE_INVERSION_DEEP alert (Phase E innovation).

Daily 22:50 Paris (post NY close) :
  1. Pull latest T10Y2Y from `fred_observations`
  2. Classify regime (severe / deep / shallow / flat / normal inversion)
  3. Fire `YIELD_CURVE_INVERSION_DEEP` if spread <= -0.50 pp (-50 bps)

Usage :
    python -m ichor_api.cli.run_yield_curve_inversion_check          # dry-run
    python -m ichor_api.cli.run_yield_curve_inversion_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.yield_curve_inversion_check import evaluate_yield_curve_inversion

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_yield_curve_inversion(session, persist=persist)
        if persist:
            await session.commit()

    print(result.note)
    if result.alert_fired:
        print(f"yield_curve · ALERT (regime={result.regime}, spread={result.spread_bps:+.1f} bps)")
    return 0


async def _main(persist: bool) -> int:
    """Async entrypoint with engine disposal in the same loop (cf ADR-024)."""
    try:
        return await run(persist=persist)
    finally:
        if persist:
            await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_yield_curve_inversion_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
