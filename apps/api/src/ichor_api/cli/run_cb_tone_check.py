"""CLI runner for the FOMC_TONE_SHIFT + ECB_TONE_SHIFT alerts.

Daily (or twice-daily — ideally aligned with FOMC press conference
schedules in NY hours) reads recent CbSpeech rows for FED + ECB,
scores each with FOMC-Roberta, persists net_hawkish into
fred_observations, computes the rolling z-score, and fires the
catalog alert when |z| ≥ 1.5.

Usage :
    python -m ichor_api.cli.run_cb_tone_check          # dry-run
    python -m ichor_api.cli.run_cb_tone_check --persist
    python -m ichor_api.cli.run_cb_tone_check --persist --cb FED
    python -m ichor_api.cli.run_cb_tone_check --persist --lookback-hours 48
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.cb_tone_check import CB_TO_METRIC, evaluate_cb_tone

log = structlog.get_logger(__name__)


async def run(*, persist: bool, cbs: list[str], lookback_hours: int) -> int:
    sm = get_sessionmaker()
    n_alerts = 0
    async with sm() as session:
        for cb in cbs:
            result = await evaluate_cb_tone(
                session,
                cb=cb,
                lookback_hours=lookback_hours,
                persist=persist,
            )
            print(f"cb_tone · {result.note}")
            if result.z_score is not None and abs(result.z_score) >= 1.5:
                n_alerts += 1
        if persist:
            await session.commit()
    print(f"cb_tone · scanned {len(cbs)} CB(s), {n_alerts} extreme-shift alert(s)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_cb_tone_check")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument(
        "--cb",
        choices=sorted(CB_TO_METRIC.keys()),
        help="Restrict to a single CB (default: all wired in CB_TO_METRIC)",
    )
    parser.add_argument("--lookback-hours", type=int, default=24)
    args = parser.parse_args(argv[1:])
    cbs = [args.cb] if args.cb else sorted(CB_TO_METRIC.keys())
    try:
        return asyncio.run(
            run(persist=args.persist, cbs=cbs, lookback_hours=args.lookback_hours)
        )
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
