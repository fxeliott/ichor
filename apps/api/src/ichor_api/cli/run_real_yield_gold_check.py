"""CLI runner for REAL_YIELD_GOLD_DIVERGENCE alert (Phase D.5.c).

Daily Mon-Fri 22:00 Paris (after NY close) :
  1. Pull 5y XAU + DFII10 from FRED (already in DB via fred_extended)
  2. Compute log-returns / first-diffs aligned on dates
  3. 60d rolling correlation
  4. Z-score against trailing 250d distribution of rolling-corr
  5. Fire `REAL_YIELD_GOLD_DIVERGENCE` if |z| >= 2.0

Usage :
    python -m ichor_api.cli.run_real_yield_gold_check          # dry-run
    python -m ichor_api.cli.run_real_yield_gold_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.real_yield_gold_check import evaluate_real_yield_gold_divergence

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_real_yield_gold_divergence(session, persist=persist)
        if persist:
            await session.commit()

    print(
        f"real_yield_gold · {result.note} "
        f"(xau_n={result.n_xau_obs}, dfii10_n={result.n_dfii10_obs}, "
        f"aligned={result.n_aligned_pairs}, zhist={result.n_zscore_history})"
    )
    if result.z_score is not None and abs(result.z_score) >= 2.0:
        print(f"real_yield_gold · ALERT (z={result.z_score:+.2f})")
    return 0


async def _main(persist: bool) -> int:
    """Async entrypoint with engine disposal in the same loop (cf ADR-024)."""
    try:
        return await run(persist=persist)
    finally:
        if persist:
            await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_real_yield_gold_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
