"""CLI runner for TERM_PREMIUM_REPRICING alert (Phase E.2).

Daily 22h Paris (post NY close, after FRED extended collector lands
the day's THREEFYTP10 reading):
  1. Pull recent THREEFYTP10 readings from `fred_observations`
  2. Compute z-score of latest reading vs trailing 90d distribution
  3. Fire `TERM_PREMIUM_REPRICING` if |z| >= 2.0
  4. Tag regime ('expansion' or 'contraction') + assets_likely_to_move

Usage :
    python -m ichor_api.cli.run_term_premium_check          # dry-run
    python -m ichor_api.cli.run_term_premium_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.term_premium_check import evaluate_term_premium_repricing

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_term_premium_repricing(session, persist=persist)
        if persist:
            await session.commit()

    print(f"term_premium · {result.note} (n_history={result.n_history})")
    if result.alert_fired:
        print(
            f"term_premium · ALERT (z={result.z_score:+.2f} regime={result.regime}) "
            f"assets={','.join(result.assets_likely_to_move)}"
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
    parser = argparse.ArgumentParser(prog="run_term_premium_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
