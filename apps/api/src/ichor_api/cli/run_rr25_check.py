"""CLI runner for the RISK_REVERSAL_25D alert.

Twice-daily (14h + 21h30 Paris) :
  1. Pull the front-month options chain via yfinance for SPY, QQQ, GLD
  2. Compute RR25 (call IV - put IV at strikes ≈ spot ± 5 %)
  3. Persist into fred_observations as `RR25_<ASSET>`
  4. Compute the rolling z-score (60 trading-day window)
  5. Fire `RISK_REVERSAL_25D` (catalog metric `rr25_z`, threshold ≥ 2.0)
     when the skew is in extreme territory

Usage :
    python -m ichor_api.cli.run_rr25_check          # dry-run
    python -m ichor_api.cli.run_rr25_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..collectors.yfinance_options import fetch_options_snapshot
from ..db import get_engine, get_sessionmaker
from ..services.risk_reversal_check import TICKER_TO_ASSET, evaluate_rr25

log = structlog.get_logger(__name__)


def _front_month_rr25(ticker: str) -> float | None:
    """Pick the closest expiry that has a non-null RR25. Yahoo
    sometimes returns malformed IV for the very front 0DTE chain ;
    walking forward until a usable rr25 is found is more robust."""
    snaps = fetch_options_snapshot(ticker)
    for s in snaps:
        if s.risk_reversal_25d is not None and not _is_nan(s.risk_reversal_25d):
            return s.risk_reversal_25d
    return None


def _is_nan(x: float) -> bool:
    return x != x  # NaN check without importing math


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    n_persisted = 0
    n_alerts = 0
    async with sm() as session:
        for ticker, asset in TICKER_TO_ASSET.items():
            rr25 = _front_month_rr25(ticker)
            if rr25 is None:
                print(f"rr25 · {ticker:4s} → no usable chain (skip)")
                continue
            result = await evaluate_rr25(session, asset=asset, rr25_pct=rr25, persist=persist)
            print(f"rr25 · {ticker:4s} → {asset:11s} {result.note}")
            n_persisted += 1
            if result.z_score is not None and abs(result.z_score) >= 2.0:
                n_alerts += 1
        if persist:
            await session.commit()
    print(
        f"rr25 · persisted {n_persisted}/{len(TICKER_TO_ASSET)} tickers, "
        f"{n_alerts} extreme-skew alert(s)"
    )
    return 0


async def _main(persist: bool) -> int:
    """Entrypoint async qui dispose l'engine dans le même event loop que run().

    Garde-fou pour le `RuntimeError: Event loop is closed` : asyncpg attache la
    connexion au loop courant ; si on appelle `asyncio.run(get_engine().dispose())`
    après `asyncio.run(run(...))`, c'est un nouveau loop et asyncpg crashe.
    """
    try:
        return await run(persist=persist)
    finally:
        if persist:
            await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_rr25_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
