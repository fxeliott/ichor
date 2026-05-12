"""Batch session-card runner — generates one card per asset for one
session window, sequentially.

Used by the systemd briefings timers (06:00 / 12:00 / 17:00 / 22:00
Paris) to produce the **6-asset universe** in one cron tick (ADR-083 D1 :
EURUSD / GBPUSD / USDCAD / XAUUSD / NAS100 / SPX500). USDJPY + AUDUSD
are tracked-no-card per ADR-083 D1 — queryable via `--assets USD_JPY`
but never in the default batch. Sequential on purpose : Claude Max 20x
has a 5h rolling cap and parallel calls would burst quota. Running 6
cards back-to-back over ~6-7 minutes keeps quota usage steady.

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

from ..db import get_engine
from .run_session_card import _run as run_one_card

log = structlog.get_logger(__name__)


# ADR-083 D1 — the 6 assets Eliot actually trades. USDJPY + AUDUSD are
# tracked-no-card (ticker maps in data_pool still wired so they can be
# queried explicitly via --assets, but the autonomous batch defaults to
# the 6 below). Pre-W104 this tuple held 8 assets.
_DEFAULT_ASSETS: tuple[str, ...] = (
    "EUR_USD",
    "GBP_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
)

from ichor_brain.types import VALID_SESSION_TYPES as _VALID_SESSIONS  # ADR-031: single source


async def _run_batch(
    *,
    session_type: str,
    assets: tuple[str, ...],
    live: bool,
    inter_card_sleep_s: float,
    push_on_complete: bool = True,
) -> int:
    if session_type not in _VALID_SESSIONS:
        print(
            f"unknown session_type {session_type!r} (expected one of {sorted(_VALID_SESSIONS)})",
            file=sys.stderr,
        )
        return 2

    print(f"== batch {session_type} · {len(assets)} cards · {'LIVE' if live else 'DRY-RUN'} ==")
    successes = 0
    failures = 0
    failed_assets: list[str] = []
    started = time.time()
    for i, asset in enumerate(assets, start=1):
        print(f"\n--- [{i}/{len(assets)}] {asset} ---")
        try:
            rc = await run_one_card(asset, session_type, live=live)
            if rc == 0:
                successes += 1
            else:
                failures += 1
                failed_assets.append(asset)
                print(f"!! card {asset} returned non-zero rc={rc}", file=sys.stderr)
        except Exception as e:
            failures += 1
            failed_assets.append(asset)
            log.error("batch.card_failed", asset=asset, error=str(e))
            print(f"!! card {asset} raised: {e}", file=sys.stderr)
        # Polite spacing so we don't flood the claude-runner — Voie D
        # ToS mitigation. Skip after the last card.
        if i < len(assets):
            await asyncio.sleep(inter_card_sleep_s)

    elapsed = time.time() - started
    print(f"\n== batch done · {successes} ok / {failures} failed · elapsed {elapsed:.1f}s ==")

    # G2 fix — push notification at end of LIVE batch. Closes the audit
    # gap "Eliot ne reçoit rien quand pre_londres est prêt à 06:30 Paris".
    # Best-effort : a push failure must NOT fail the batch. Subscriber
    # list lives in Redis `ichor:push:subs` (services/push.py).
    if live and push_on_complete and successes > 0:
        try:
            from ..services.push import send_to_all

            title = f"Ichor — {session_type} prête ({successes}/{len(assets)})"
            body_parts = [
                f"{successes} cards générées en {elapsed:.0f}s",
            ]
            if failed_assets:
                body_parts.append(f"Échecs : {', '.join(failed_assets)}")
            body = " · ".join(body_parts)
            n_sent = await send_to_all(title, body, url=f"/sessions?session={session_type}")
            log.info("batch.push_sent", n_recipients=n_sent, session_type=session_type)
            print(f"   push: {n_sent} subscribers notified")
        except Exception as e:  # noqa: BLE001
            log.warning("batch.push_failed", error=str(e))
            print(f"   push: failed ({e}) — non-fatal", file=sys.stderr)

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
        help="comma-separated list of asset codes (default: the 6-asset universe per ADR-083 D1)",
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
