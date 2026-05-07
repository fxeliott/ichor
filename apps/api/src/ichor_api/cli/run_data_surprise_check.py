"""CLI runner for DATA_SURPRISE_Z alert (Phase D.5.a).

Daily 14h35 Paris (after the 14h30 US data release window — NFP at
14h30, CPI at 14h30, retail sales at 14h30, etc.) :

  1. Re-run the Eco Surprise Index proxy (services/surprise_index.py)
  2. For each constituent series with |z| >= 2.0, fire DATA_SURPRISE_Z
  3. Print a one-line punch-list (composite + per-series breakdown)

Usage :
    python -m ichor_api.cli.run_data_surprise_check          # dry-run
    python -m ichor_api.cli.run_data_surprise_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.data_surprise_check import evaluate_data_surprise_z

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_data_surprise_z(session, persist=persist)
        if persist:
            await session.commit()

    composite_str = (
        f"{result.composite_z:+.2f}" if result.composite_z is not None else "n/a"
    )
    print(
        f"data_surprise · {result.region} composite={composite_str} ({result.composite_band}) "
        f"· {result.n_series_evaluated} series · {result.n_series_alerting} alert(s) fired"
    )
    if result.alerts_fired:
        print(f"data_surprise · alerts: {', '.join(result.alerts_fired)}")
    return 0


async def _main(persist: bool) -> int:
    """Entrypoint async qui dispose l'engine dans le même event loop que run().

    Garde-fou pour le `RuntimeError: Event loop is closed` : asyncpg attache la
    connexion au loop courant (cf ADR-024 + RUNBOOK-014).
    """
    try:
        return await run(persist=persist)
    finally:
        if persist:
            await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_data_surprise_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
