"""Phase 7 — Streaming-cadence verdict refresh cron CLI (ADR-109).

Detects a NEW strong event since each asset's last session card
(fresh economic ``actual`` / central-bank speech / strong-tone news,
reusing ``_assemble_live_triggers``) and regenerates ONLY that asset's
card (full 4-pass + Pass-6 Opus via ``run_session_card._run``) + pushes
a notification — so the NY-session verdict stays live to market-moving
events BETWEEN the 4×/day batch emissions.

ADDITIVE + reversible : gated by the ``streaming_refresh_enabled``
feature flag (fail-closed). NEVER touches the 4×/day batch.

Cadence : every ~12 minutes Paris — see
``scripts/hetzner/register-cron-streaming-refresh.sh``. Voie D : the
regen routes through the Win11 runner; detection + push are pure DB /
web-push. Zero Anthropic spend. Most ticks find no new event and do
nothing (zero marginal Opus).

Usage :

    python -m ichor_api.cli.run_streaming_refresh
    python -m ichor_api.cli.run_streaming_refresh --dry-run
    python -m ichor_api.cli.run_streaming_refresh --asset EUR_USD   # witness

Exit codes (mirror ``run_scenario_invalidation_check``) :

    0 : success (zero or more cards regenerated)
    1 : feature flag OFF — clean skip, NOT a failure
    2 : ≥1 stale-verdict regen FAILED — OnFailure notify path (S02 audit)
    3 : DB connection / runtime failure — cron retries next tick

ADR refs : ADR-109 (streaming cadence), ADR-106 §D2/§D4, ADR-085 Pass-6,
ADR-017 boundary, ADR-009 Voie D, ADR-030 ResolveCron.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
from datetime import UTC, datetime

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.feature_flags import is_enabled
from ..services.streaming_refresh import (
    _DEFAULT_COOLDOWN_MINUTES,
    _DEFAULT_MAX_REGENS_PER_FIRE,
    run_streaming_refresh,
)

log = structlog.get_logger(__name__)

_FEATURE_FLAG_NAME = "streaming_refresh_enabled"


async def _run(
    *,
    dry_run: bool,
    cooldown_minutes: int,
    max_per_fire: int,
    only_asset: str | None,
    enable_rag: bool,
    enable_tools: bool,
) -> int:
    """Run the streaming refresh once. Returns shell exit code."""
    sm = get_sessionmaker()

    # Feature-flag gate — fail-closed (absent flag → is_enabled False).
    try:
        async with sm() as flag_session:
            enabled = await is_enabled(flag_session, _FEATURE_FLAG_NAME)
    except Exception as exc:
        print(
            f"DB connection failure during feature flag check : {exc!s}. Cron will retry next tick."
        )
        return 3

    if not enabled:
        print(
            f"feature flag {_FEATURE_FLAG_NAME!r} is OFF — skipping streaming "
            "refresh. Activate via :\n"
            "  UPDATE feature_flags SET enabled = true "
            f"WHERE key = '{_FEATURE_FLAG_NAME}' ;"
        )
        return 1

    assets = (only_asset.upper(),) if only_asset else None
    print(
        f"== streaming refresh · cooldown={cooldown_minutes}min · "
        f"max_per_fire={max_per_fire} · dry_run={dry_run}"
        f"{' · asset=' + only_asset.upper() if only_asset else ''} =="
    )

    try:
        result = await run_streaming_refresh(
            session_factory=sm,
            now_utc=datetime.now(UTC),
            cooldown_minutes=cooldown_minutes,
            max_regens_per_fire=max_per_fire,
            assets=assets,
            dry_run=dry_run,
            enable_rag=enable_rag,
            enable_tools=enable_tools,
        )
    except Exception as exc:
        log.error(
            "streaming_refresh.failed",
            error=str(exc)[:500],
            traceback=traceback.format_exc()[:2000],
        )
        print(f"streaming refresh failed : {exc!s}")
        return 3

    log.info(
        "streaming_refresh.complete",
        dry_run=dry_run,
        regenerated=result.regenerated,
        pushed=result.pushed,
        dropped=result.dropped,
        failed=result.failed,
    )
    print(
        f"OK · regenerated={result.regenerated} pushed={result.pushed} "
        f"dropped={result.dropped} failed={result.failed} (dry_run={dry_run})"
    )
    for o in result.outcomes:
        detail = f" — {o.detail}" if o.detail else ""
        push_tag = " [push]" if o.pushed else ""
        print(f"  · {o.asset:<11} {o.action:<12} {o.reason:<14}{push_tag}{detail}")
    # S02 socle audit (2026-06-18) — honest failure signalling. A stale verdict
    # whose regen FAILED (result.failed > 0) used to exit 0 = silent : the card
    # stayed stale and nobody was paged. Exit 2 (distinct from 3 = DB-transient,
    # tolerated by the unit's SuccessExitStatus) so the systemd OnFailure path
    # fires. Dry-run never regenerates, so failed is always 0 there.
    if result.failed > 0:
        print(
            f"streaming refresh: {result.failed} regen(s) FAILED — exit 2 "
            "(stale verdict not refreshed; OnFailure notify path)"
        )
        return 2
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(
            dry_run=args.dry_run,
            cooldown_minutes=args.cooldown_minutes,
            max_per_fire=args.max_per_fire,
            only_asset=args.asset,
            enable_rag=not args.no_rag,
            enable_tools=args.enable_tools,
        )
    finally:
        await get_engine().dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Streaming-cadence verdict refresh — detect a NEW strong event "
            "since each asset's last card and regenerate ONLY that asset's "
            "card + push. Feature-flag-gated (streaming_refresh_enabled), "
            "additive, never touches the 4×/day batch."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Detect + report only — do NOT regenerate any card or push. "
            "Read-only smoke test of the detector."
        ),
    )
    parser.add_argument(
        "--cooldown-minutes",
        type=int,
        default=_DEFAULT_COOLDOWN_MINUTES,
        help=(
            f"Per-asset cooldown (default {_DEFAULT_COOLDOWN_MINUTES}). Skip "
            "an asset whose last card is younger than this, even if a new "
            "event fired (bounds the regen rate; self-respects a fresh batch)."
        ),
    )
    parser.add_argument(
        "--max-per-fire",
        type=int,
        default=_DEFAULT_MAX_REGENS_PER_FIRE,
        help=(
            f"Max assets regenerated in one tick (default "
            f"{_DEFAULT_MAX_REGENS_PER_FIRE}). Overflow is logged as a drop "
            "(never silent) and picked up next tick."
        ),
    )
    parser.add_argument(
        "--asset",
        default=None,
        help=(
            "Restrict to a single asset (e.g. EUR_USD). Used for the "
            "post-deploy witness; the cron runs the full universe."
        ),
    )
    parser.add_argument(
        "--no-rag",
        action="store_true",
        help="Disable past-only RAG analogues in the regen (default: enabled, matching the batch).",
    )
    parser.add_argument(
        "--enable-tools",
        action="store_true",
        help="Wire Cap5 MCP tools in the regen (default OFF, matching the prudent batch rollout).",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
