"""CLI runner for DOLLAR_SMILE_BREAK alert (Phase E.3).

Daily 22h Paris (post NY close, after FRED extended collector lands
the day's readings):
  1. Pull 90+14d for THREEFYTP10 + DTWEXBGS + VIXCLS + BAMLH0A0HYM2
  2. Z-score each
  3. Evaluate 4 conditions:
     - term_premium_z > +2.0 (expansion)
     - dxy_z < -1.0 (USD weakening)
     - vix_z < +1.0 (not panic)
     - hy_oas_z < +1.0 (no credit stress)
  4. Fire DOLLAR_SMILE_BREAK if all 4 conditions hold
  5. Tag smile_regime = 'us_driven_instability' when fired

Usage :
    python -m ichor_api.cli.run_dollar_smile_check          # dry-run
    python -m ichor_api.cli.run_dollar_smile_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.dollar_smile_check import evaluate_dollar_smile_break

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_dollar_smile_break(session, persist=persist)
        if persist:
            await session.commit()

    print(result.note)
    if result.alert_fired:
        print(
            f"dollar_smile · ALERT (regime={result.smile_regime}, "
            f"{result.n_conditions_passing}/4 conditions)"
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
    parser = argparse.ArgumentParser(prog="run_dollar_smile_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
