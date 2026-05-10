"""CLI runner for TARIFF_SHOCK alert (Phase D.5.b.2).

4× business days (11:30 / 15:30 / 18:30 / 22:30 Paris) :
  1. Pull last 30+7d gdelt_events filtered for tariff narrative keywords
  2. Group by UTC day → daily count + today's avg(tone)
  3. Z-score today's count vs trailing 30d
  4. Fire `TARIFF_SHOCK` if count_z >= 2.0 AND avg_tone <= -1.5

Usage :
    python -m ichor_api.cli.run_tariff_shock_check          # dry-run
    python -m ichor_api.cli.run_tariff_shock_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.tariff_shock_check import evaluate_tariff_shock

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_tariff_shock(session, persist=persist)
        if persist:
            await session.commit()

    print(f"tariff_shock · {result.note} (n_history={result.n_history})")
    if result.title_sample:
        print(f"tariff_shock · sample titles: {' | '.join(result.title_sample[:3])}")
    if result.alert_fired:
        print(
            f"tariff_shock · ALERT (count_z={result.count_z:+.2f} avg_tone={result.avg_tone_today})"
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
    parser = argparse.ArgumentParser(prog="run_tariff_shock_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
