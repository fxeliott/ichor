"""CLI runner for QUAD_WITCHING + OPEX_GAMMA_PEAK proximity alerts (Phase D.5.e).

Daily Mon-Fri 22:00 Paris (post NY close — same slot as
real-yield-gold-check, fires at most a few times per year for QW
and 12 times per year for monthly OPEX) :
  1. Compute today's UTC date
  2. Find next quad-witching date (3rd Friday of Mar/Jun/Sep/Dec)
  3. Find next monthly OPEX (3rd Friday of any month)
  4. Fire QUAD_WITCHING (T-5 through T-0) + OPEX_GAMMA_PEAK
     (T-2 through T-0) when in window

Usage :
    python -m ichor_api.cli.run_quad_witching_check
    python -m ichor_api.cli.run_quad_witching_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.quad_witching_check import evaluate_quad_witching_proximity

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_quad_witching_proximity(session, persist=persist)
        if persist:
            await session.commit()

    print(
        f"witching · today={result.today} "
        f"next_quad={result.next_quad_date} (T-{result.days_to_quad}) "
        f"next_opex={result.next_opex_date} (T-{result.days_to_opex})"
    )
    if result.is_quad_witching_window:
        marker = "✓ FIRED" if result.quad_witching_alert_fired else "(dry-run)"
        print(f"witching · QUAD_WITCHING in window {marker}")
    if result.is_opex_window:
        marker = "✓ FIRED" if result.opex_alert_fired else "(dry-run)"
        print(f"witching · OPEX_GAMMA_PEAK in window {marker}")
    return 0


async def _main(persist: bool) -> int:
    """Async entrypoint with engine disposal in the same loop (cf ADR-024)."""
    try:
        return await run(persist=persist)
    finally:
        if persist:
            await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_quad_witching_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
