"""Batch session-card runner — generates one card per asset for one
session window, sequentially.

Used by the systemd briefings timers (06:00 / 12:00 / 17:00 / 22:00
Paris) to produce the full 8-asset grid in one cron tick. Sequential
on purpose : Claude Max 20x has a 5h rolling cap and parallel calls
would burst quota. Running the 8 cards back-to-back over ~8 minutes
keeps quota usage steady.

Usage :
  python -m ichor_api.cli.run_session_cards_batch pre_londres
  python -m ichor_api.cli.run_session_cards_batch pre_ny
  python -m ichor_api.cli.run_session_cards_batch pre_londres --assets EUR_USD,XAU_USD
  python -m ichor_api.cli.run_session_cards_batch pre_londres --dry-run

The session_type maps to a cron name :
  pre_londres    → ~07:30 Paris (briefing tick at 06:00 UTC)
  pre_ny         → ~13:30 Paris (12:00 UTC)
  ny_mid         → 17:00 Paris (mid-NY context refresh)
  ny_close       → 22:00 Paris (NY close debrief)
  event_driven   → on-demand from anomaly trigger

Per ADR-017 capability #4 the brain runs 4 passes per asset per
session — this CLI is the entrypoint for the autonomous "16 cards
per day" production schedule.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import structlog

from .run_session_card import _run as run_one_card
from ..db import get_engine

log = structlog.get_logger(__name__)


_DEFAULT_ASSETS: tuple[str, ...] = (
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
)

_VALID_SESSIONS = {"pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"}


async def _run_batch(
    *,
    session_type: str,
    assets: tuple[str, ...],
    live: bool,
    inter_card_sleep_s: float,
) -> int:
    if session_type not in _VALID_SESSIONS:
        print(
            f"unknown session_type {session_type!r} "
            f"(expected one of {sorted(_VALID_SESSIONS)})",
            file=sys.stderr,
        )
        return 2

    print(
        f"== batch {session_type} · "
        f"{len(assets)} cards · "
        f"{'LIVE' if live else 'DRY-RUN'} =="
    )
    successes = 0
    failures = 0
    started = time.time()
    for i, asset in enumerate(assets, start=1):
        print(f"\n--- [{i}/{len(assets)}] {asset} ---")
        try:
            rc = await run_one_card(asset, session_type, live=live)
            if rc == 0:
                successes += 1
            else:
                failures += 1
                print(f"!! card {asset} returned non-zero rc={rc}", file=sys.stderr)
        except Exception as e:
            failures += 1
            log.error("batch.card_failed", asset=asset, error=str(e))
            print(f"!! card {asset} raised: {e}", file=sys.stderr)
        # Polite spacing so we don't flood the claude-runner — Voie D
        # ToS mitigation. Skip after the last card.
        if i < len(assets):
            await asyncio.sleep(inter_card_sleep_s)

    elapsed = time.time() - started
    print(
        f"\n== batch done · {successes} ok / {failures} failed · "
        f"elapsed {elapsed:.1f}s =="
    )
    return 0 if failures == 0 else 1


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_session_cards_batch",
        description="Generate session cards for all assets in one session window.",
    )
    parser.add_argument("session_type", help=f"one of {sorted(_VALID_SESSIONS)}")
    parser.add_argument(
        "--assets",
        type=lambda s: tuple(a.strip().upper() for a in s.split(",") if a.strip()),
        default=None,
        help="comma-separated list of asset codes (default: all 8 Phase-1)",
    )
    parser.add_argument(
        "--inter-card-sleep",
        type=float,
        default=2.0,
        help="seconds between cards (default 2)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="real claude-runner via tunnel")
    mode.add_argument("--dry-run", action="store_true", help="canned responses (default)")
    args = parser.parse_args(argv)

    assets = args.assets or _DEFAULT_ASSETS
    live = args.live  # default False (dry-run)
    try:
        return await _run_batch(
            session_type=args.session_type,
            assets=assets,
            live=live,
            inter_card_sleep_s=args.inter_card_sleep,
        )
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
