"""CLI runner for the LIQUIDITY_TIGHTENING alert.

Reads RRPONTSYD + DTS_TGA_CLOSE from `fred_observations`, computes
the 5-day liquidity proxy delta in $bn, and fires
`metric_name='liq_proxy_d'` against the catalog. The alert
triggers when the delta is ≤ -200 ($bn drained from money markets
in 5 trading days — historically precedes funding-rate spikes).

This wires the catalog row that has been DORMANT since the alert
was added : the metric was declared in `alerts/catalog.py` but no
producer ever called `check_metric("liq_proxy_d", ...)`. With this
runner registered as a daily cron (after the dts_treasury collector
finishes at 04:00 Paris), the alert finally has a heartbeat.

Usage :
    python -m ichor_api.cli.run_liquidity_check          # dry-run
    python -m ichor_api.cli.run_liquidity_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.alerts_runner import check_metric
from ..services.liquidity_proxy import assess_liquidity_proxy

log = structlog.get_logger(__name__)


async def run(*, persist: bool, lookback_days: int = 5) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        reading = await assess_liquidity_proxy(session, lookback_days=lookback_days)
        if reading.delta_bn is None:
            print(f"liquidity_check · skipped — {reading.note}")
            return 0

        print(
            f"liquidity_check · proxy={reading.proxy_bn:.0f}bn "
            f"(RRP {reading.rrp_bn:.0f}bn + TGA {reading.tga_bn:.0f}bn) "
            f"Δ{lookback_days}d {reading.delta_bn:+.0f}bn"
        )

        if persist:
            hits = await check_metric(
                session,
                metric_name="liq_proxy_d",
                current_value=reading.delta_bn,
                extra_payload={
                    "rrp_bn": reading.rrp_bn,
                    "tga_bn": reading.tga_bn,
                    "proxy_bn": reading.proxy_bn,
                    "proxy_bn_lag": reading.proxy_bn_lag,
                    "lookback_days": lookback_days,
                },
            )
            await session.commit()
            print(
                f"liquidity_check · {len(hits)} alert(s) triggered "
                f"({', '.join(h.alert_def.code for h in hits) or 'none'})"
            )
    return 0


async def _main(persist: bool, lookback_days: int) -> int:
    """Entrypoint async qui dispose l'engine dans le même event loop que run().

    Garde-fou contre `RuntimeError: Event loop is closed` (asyncpg conn liée au loop).
    """
    try:
        return await run(persist=persist, lookback_days=lookback_days)
    finally:
        if persist:
            await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_liquidity_check")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=5)
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist, lookback_days=args.lookback_days))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
