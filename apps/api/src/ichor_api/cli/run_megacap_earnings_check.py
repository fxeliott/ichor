"""CLI runner for MEGACAP_EARNINGS_T-1 alert (Phase D.5.f).

Daily 14h Paris (post US pre-market window) :
  1. Iterate Mag-7 tickers (TSLA, GOOGL, MSFT, META, AAPL, AMZN, NVDA)
  2. Fetch next earnings date from yfinance
  3. Fire `MEGACAP_EARNINGS_T-1` for each ticker within T-1 (= today or tomorrow)

Usage :
    python -m ichor_api.cli.run_megacap_earnings_check          # dry-run
    python -m ichor_api.cli.run_megacap_earnings_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.megacap_earnings_check import evaluate_megacap_earnings

log = structlog.get_logger(__name__)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_megacap_earnings(session, persist=persist)
        if persist:
            await session.commit()

    print(
        f"megacap_earnings · today={result.today.isoformat()} "
        f"evaluated={result.tickers_evaluated} with_date={result.tickers_with_date} "
        f"alerting={result.tickers_alerting}"
    )
    if result.per_ticker:
        breakdown = " ".join(
            f"{t.ticker}={'T-' + str(t.days_to_event) if t.days_to_event is not None else 'n/a'}"
            for t in result.per_ticker
        )
        print(f"megacap_earnings · breakdown: {breakdown}")
    if result.alerts_fired:
        print(f"megacap_earnings · ALERTS: {', '.join(result.alerts_fired)}")
    return 0


async def _main(persist: bool) -> int:
    """Async entrypoint with engine disposal in the same loop (cf ADR-024)."""
    try:
        return await run(persist=persist)
    finally:
        if persist:
            await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_megacap_earnings_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
