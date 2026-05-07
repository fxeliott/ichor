"""CLI runner for MACRO_QUARTET_STRESS alert (Phase E.4).

Daily 22h Paris (post NY close, after FRED extended collector lands
the day's readings):
  1. Pull last 90+14d for each of DTWEXBGS / DGS10 / VIXCLS / BAMLH0A0HYM2
  2. Compute z-score per dim
  3. Count dimensions with |z| > 2.0
  4. Fire `MACRO_QUARTET_STRESS` if count >= 3 (3-of-4 alignment)
  5. Tag regime ('stress' if all positive, 'complacency' if all negative,
     'mixed' if no directional consensus)

Usage :
    python -m ichor_api.cli.run_macro_quartet_check          # dry-run
    python -m ichor_api.cli.run_macro_quartet_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.macro_quartet_check import evaluate_macro_quartet

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_macro_quartet(session, persist=persist)
        if persist:
            await session.commit()

    print(f"macro_quartet · {result.note}")
    if result.alert_fired:
        print(
            f"macro_quartet · ALERT (regime={result.regime}, "
            f"{result.n_stressed_extreme}/4 dims extreme)"
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
    parser = argparse.ArgumentParser(prog="run_macro_quartet_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
