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

Exit-code contract (ADR-110 / 2026-06-10 P0 class kill) :
  0 — every card generated (or nothing to do, market-closed gate).
  1 — PARTIAL failure (≥1 ok, ≥1 failed). Whitelisted by the systemd
      unit (`SuccessExitStatus=0 1`) as a warning, not a failure.
  2 — TOTAL failure (0 ok) or bad invocation. NOT whitelisted →
      systemd Result=failed → OnFailure=ichor-notify@ fires. A dead
      runner / quota exhaustion can no longer pass silent.
  3 — TRANSIENT : an uncaught exception escaped OUTSIDE the per-card loop
      (argument/setup error, an unexpected failure in `_run_batch`, or the
      engine-dispose `finally`). Pre-2026-06-19 this exited 1 and was MASKED
      by `SuccessExitStatus=0 1` → silent batch death (exactly the class
      `_exit.cron_main` was built to close for the `_check` CLIs). The batch
      now delegates to `cron_main`, which PROPAGATES the 0/1/2 return
      unchanged and converts only an uncaught exception into a distinct
      honest 3 so OnFailure fires (S02 socle residual audit 2026-06-19).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.feature_flags import is_enabled
from ..services.market_session import compute_session_status, market_closed_for_asset
from ._exit import cron_main
from .run_session_card import _run as run_one_card

log = structlog.get_logger(__name__)

# ADR-105 — market-closed gate (ADR-099 §Tier-3). Ships OFF : with no
# `feature_flags` row, is_enabled() → False ⇒ the gate is fully inert
# (zero behaviour change) until Eliot inserts the flag row.
_MARKET_CLOSED_GATE_FLAG = "session_cards_market_closed_gate_enabled"


# The 5 assets Eliot actually trades (owner decision 2026-06-20 — drops
# USD_CAD from the former ADR-083 D1 6-asset list). USD_CAD now joins
# USDJPY + AUDUSD as tracked-no-card (ticker maps in data_pool still wired
# so they can be queried explicitly via --assets, but the autonomous batch
# defaults to the 5 below). Pre-W104 this tuple held 8 assets.
_DEFAULT_ASSETS: tuple[str, ...] = (
    "EUR_USD",
    "GBP_USD",
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
    enable_rag: bool = False,
    enable_tools: bool = False,
) -> int:
    if session_type not in _VALID_SESSIONS:
        print(
            f"unknown session_type {session_type!r} (expected one of {sorted(_VALID_SESSIONS)})",
            file=sys.stderr,
        )
        return 2

    # ADR-105 market-closed gate (ADR-099 §Tier-3). FAIL-OPEN : the gate
    # may suppress a card ONLY on a positive, error-free "market closed"
    # determination ; any exception ⇒ proceed (a missed real pre-session
    # is unrecoverable — the timer does not re-fire — and is categorically
    # worse than a redundant closed-day card). Inert unless the flag row
    # exists (ships OFF).
    try:
        sm = get_sessionmaker()
        async with sm() as _flag_session:
            gate_on = await is_enabled(_flag_session, _MARKET_CLOSED_GATE_FLAG)
        if gate_on:
            status = compute_session_status()
            market_closed = status.market_closed_fx or status.market_closed_us_equity
            kept = tuple(a for a in assets if not market_closed_for_asset(a, status))
            skipped = [a for a in assets if a not in kept]
            if not kept and not market_closed:
                # SAFETY (ADR-105 §3 — fail-open made STRUCTURAL, not
                # emergent ; ichor-trader R28 YELLOW-1) : an empty keep-set
                # while the market is NOT positively closed means the gate
                # SSOT is internally inconsistent (a future
                # _US_EQUITY_ASSETS / market_closed_for_asset regression).
                # NEVER suppress a real session on ambiguity — log loud and
                # generate the FULL original set.
                log.warning(
                    "batch.market_closed_gate_anomaly_failed_open",
                    session_type=session_type,
                    state=status.state,
                    assets=list(assets),
                )
                print(
                    "   market-closed gate: empty keep-set on a NON-closed "
                    f"market ({status.state}) — anomaly, generating all "
                    "(fail-open)",
                    file=sys.stderr,
                )
            else:
                if skipped:
                    hol = f" · {status.holiday_name}" if status.holiday_name else ""
                    log.info(
                        "batch.market_closed_gate",
                        session_type=session_type,
                        state=status.state,
                        holiday=status.holiday_name,
                        skipped=skipped,
                        kept=list(kept),
                    )
                    print(
                        f"== market-closed gate ({status.state}{hol}) : "
                        f"skipping {len(skipped)} closed-market asset(s) {skipped} =="
                    )
                assets = kept
                if not assets:
                    print(f"== all assets closed ({status.state}) — no cards this tick ==")
                    return 0
    except Exception as e:  # noqa: BLE001 — FAIL-OPEN : never turn an error into a skip
        log.warning("batch.market_closed_gate_failed_open", error=str(e))
        print(
            f"   market-closed gate errored ({e}) — proceeding (fail-open)",
            file=sys.stderr,
        )

    flags = []
    if enable_rag:
        flags.append("RAG")
    if enable_tools:
        flags.append("TOOLS")
    flags_label = (" · " + "+".join(flags)) if flags else ""
    print(
        f"== batch {session_type} · {len(assets)} cards · "
        f"{'LIVE' if live else 'DRY-RUN'}{flags_label} =="
    )
    successes = 0
    failures = 0
    failed_assets: list[str] = []
    started = time.time()
    for i, asset in enumerate(assets, start=1):
        print(f"\n--- [{i}/{len(assets)}] {asset} ---")
        try:
            rc = await run_one_card(
                asset,
                session_type,
                live=live,
                enable_rag=enable_rag,
                enable_tools=enable_tools,
            )
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
    if failures and not successes:
        # TOTAL failure (0 cards) — the 2026-06-10 P0 class: a dead
        # runner / exhausted quota fails EVERY card, yet rc=1 was
        # whitelisted by `SuccessExitStatus=0 1` on the systemd unit, so
        # the unit showed Result=success and OnFailure never notified.
        # rc=2 is NOT whitelisted → systemd marks the unit failed and
        # fires ichor-notify@. Partial failure keeps rc=1 (warning):
        # some cards shipped, the window is not silently lost.
        print(
            "!! TOTAL batch failure — 0 cards generated; exiting rc=2 "
            "(systemd failure + OnFailure notify)",
            file=sys.stderr,
        )

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

    if failures == 0:
        return 0
    return 2 if successes == 0 else 1


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
        default=30.0,
        help=(
            "seconds between cards (default 30). Pre-round-10 default was "
            "2s but batch 6-cards × 5 passes burst 30 calls in ~18min and "
            "saturated Claude Max 20x rate limit. 30s pacing keeps the "
            "burst rate ≤ 60/h ceiling per ADR-009 Voie D ToS hygiene."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="real claude-runner via tunnel")
    mode.add_argument("--dry-run", action="store_true", help="canned responses (default)")
    # W110 + Cap5 mainline flips — forwarded to run_session_card per asset.
    # Default OFF preserves the historical batch shape (pre-round-13). The
    # production systemd unit `ichor-session-cards@.service` is expected to
    # pass both flags so every card embeds RAG analogues + Cap5 tool calls.
    parser.add_argument(
        "--enable-rag",
        action="store_true",
        help="W110d ADR-086 — inject past-only RAG analogues in Pass-1 prompt.",
    )
    parser.add_argument(
        "--enable-tools",
        action="store_true",
        help="W87 ADR-077 — wire mcp__ichor__{query_db,calc} for Pass-1/2/scenarios.",
    )
    args = parser.parse_args(argv)

    assets = args.assets or _DEFAULT_ASSETS
    live = args.live  # default False (dry-run)
    try:
        return await _run_batch(
            session_type=args.session_type,
            assets=assets,
            live=live,
            inter_card_sleep_s=args.inter_card_sleep,
            enable_rag=args.enable_rag,
            enable_tools=args.enable_tools,
        )
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    # cron_main runs `_main` (which disposes the engine in its own finally,
    # same event loop — ADR-024), PROPAGATES the 0/1/2 contract unchanged, and
    # converts an otherwise exit-1 uncaught traceback into a distinct honest
    # exit 3 (TRANSIENT) so the unit's OnFailure fires instead of masking it.
    sys.exit(cron_main(lambda: _main(sys.argv[1:])))
