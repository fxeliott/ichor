"""CLI runner for YIELD_CURVE_UN_INVERSION_EVENT alert (Phase E innovation).

Daily 22:55 Paris (last in nightly chain after YIELD_CURVE_INVERSION_DEEP) :
  1. Pull last LOOKBACK_DAYS+5 T10Y2Y observations
  2. Detect cross-up event (yesterday ≤ 0, today > 0)
  3. Detect deep inversion in 60d window (≤ -30 bps)
  4. Fire `YIELD_CURVE_UN_INVERSION_EVENT` if both conditions met

Usage :
    python -m ichor_api.cli.run_yield_curve_un_inversion_check          # dry-run
    python -m ichor_api.cli.run_yield_curve_un_inversion_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.yield_curve_un_inversion_check import (
    evaluate_yield_curve_un_inversion,
)

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_yield_curve_un_inversion(session, persist=persist)
        if persist:
            await session.commit()

    print(result.note)
    if result.alert_fired:
        print(
            f"yield_curve_un_inv · ALERT (un-inversion event confirmed: "
            f"{result.n_conditions_met}/2 conditions, days_since_deepest="
            f"{result.days_since_deepest})"
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
    parser = argparse.ArgumentParser(prog="run_yield_curve_un_inversion_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
