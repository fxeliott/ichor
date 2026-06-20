"""Feature-flag admin CLI — the safe, auditable way to toggle a flag in prod.

Until now flags were flipped with a raw ``UPDATE feature_flags SET enabled = true
WHERE key = '...'`` (documented across the cron CLIs). That bypasses the app's
``set_flag`` write path, so it (a) leaves no ``updated_by`` actor trail, (b) does
NOT publish the cross-worker Redis cache invalidation (so a running API can serve
the stale flag for up to 60 s), and (c) is typo-prone (a misspelled key silently
no-ops). This CLI closes that gap — it is the canonical activation tool, especially
for the S04 ``*_dimension_vote_enabled`` flags (all default-OFF / dormant).

It calls ``services.feature_flags.set_flag`` (DB upsert + local-cache invalidate +
best-effort Redis publish), prints the BEFORE→AFTER state so the operator sees
exactly what changed, and supports a ``--dry-run`` that reads + prints without
writing. ``--list`` shows every flag; ``--dimensions`` shows just the S04 dimension
votes + the doubt term so the gradual rollout is easy to drive.

Voie D : pure DB I/O, zero LLM / spend.

Usage :

    # see the current state of every S04 dimension vote
    python -m ichor_api.cli.run_set_feature_flag --dimensions

    # activate one (safe order: the DOUBT votes first — they can only LOWER
    # conviction, never amplify over-confidence) :
    python -m ichor_api.cli.run_set_feature_flag vol_regime_dimension_vote_enabled --on
    python -m ichor_api.cli.run_set_feature_flag geopolitics_dimension_vote_enabled --on --dry-run

    # roll back :
    python -m ichor_api.cli.run_set_feature_flag <key> --off

Exit codes :  0 success · 2 bad usage · 3 DB connection failure
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from ..db import get_sessionmaker
from ..services.feature_flags import is_enabled, list_all, set_flag

log = structlog.get_logger(__name__)


def _dimension_flags() -> dict[str, str]:
    """The S04 Chantier-C vote flags + the doubt term, in the RECOMMENDED activation
    order (doubts first — they only lower conviction, so they cannot amplify the
    over-confidence the calibration must otherwise shrink). Imported from each
    producer (single source of truth) so this list can never typo-drift."""
    from ..services.correlations_vote import CORRELATIONS_DIMENSION_VOTE_FLAG
    from ..services.cot_vote import COT_DIMENSION_VOTE_FLAG
    from ..services.geopolitics_vote import GEOPOLITICS_DIMENSION_VOTE_FLAG
    from ..services.manipulation_liquidity_vote import MANIPULATION_LIQUIDITY_DIMENSION_VOTE_FLAG
    from ..services.positioning_divergence_vote import POSITIONING_DIVERGENCE_DIMENSION_VOTE_FLAG
    from ..services.positioning_tff_vote import POSITIONING_TFF_DIMENSION_VOTE_FLAG
    from ..services.real_yield_vote import REAL_YIELD_DIMENSION_VOTE_FLAG
    from ..services.sentiment_vote import SENTIMENT_DIMENSION_VOTE_FLAG
    from ..services.vol_regime_vote import VOL_REGIME_DIMENSION_VOTE_FLAG
    from ..services.volume_vote import VOLUME_DIMENSION_VOTE_FLAG

    return {
        # — DOUBT votes (lower conviction only → safest to activate first) —
        VOL_REGIME_DIMENSION_VOTE_FLAG: "doubt · VIX term-structure (global)",
        MANIPULATION_LIQUIDITY_DIMENSION_VOTE_FLAG: "doubt · RRP+TGA funding drain (global)",
        CORRELATIONS_DIMENSION_VOTE_FLAG: "doubt · systemic cross-asset correlation (global)",
        POSITIONING_DIVERGENCE_DIMENSION_VOTE_FLAG: "doubt · TFF LevFunds-vs-AssetMgr (per-asset)",
        # — non-directional corroboration —
        GEOPOLITICS_DIMENSION_VOTE_FLAG: "credit · AI-GPR spike (global)",
        VOLUME_DIMENSION_VOTE_FLAG: "credit · RVOL participation (indices/gold)",
        # — directional (raise/lower per agreement → activate last, witness each) —
        COT_DIMENSION_VOTE_FLAG: "directional · COT managed-money",
        POSITIONING_TFF_DIMENSION_VOTE_FLAG: "directional · TFF leveraged-funds (SPX500)",
        SENTIMENT_DIMENSION_VOTE_FLAG: "directional · MyFXBook retail contrarian (FX+gold)",
        REAL_YIELD_DIMENSION_VOTE_FLAG: "directional · real-yield→gold carry (XAU)",
    }


async def _run(args: argparse.Namespace) -> int:
    sm = get_sessionmaker()

    # --- Read-only listing modes ------------------------------------------------------
    if args.list or args.dimensions:
        try:
            async with sm() as session:
                if args.dimensions:
                    dims = _dimension_flags()
                    print("== S04 dimension-vote flags (recommended activation order) ==")
                    for key, label in dims.items():
                        on = await is_enabled(session, key)
                        print(f"  [{'ON ' if on else 'off'}] {key:46s} {label}")
                else:
                    flags = await list_all(session)
                    print(f"== all feature flags ({len(flags)}) ==")
                    for f in flags:
                        state = "ON " if f.enabled else "off"
                        print(f"  [{state}] {f.key:46s} rollout={f.rollout_pct}%")
        except Exception as exc:  # noqa: BLE001 — surface DB outage as a clean exit code
            print(f"DB connection failure : {exc!s}")
            return 3
        return 0

    # --- Toggle mode ------------------------------------------------------------------
    if not args.key:
        print("error: a flag KEY is required to toggle (or use --list / --dimensions).")
        return 2
    if args.on == args.off:  # both or neither
        print("error: choose exactly one of --on / --off.")
        return 2

    enabled = bool(args.on)
    try:
        async with sm() as session:
            before = await is_enabled(session, args.key)
            if args.dry_run:
                print(
                    f"DRY-RUN : {args.key} is currently {'ON' if before else 'off'} → would set "
                    f"{'ON' if enabled else 'off'} (rollout {args.rollout}%). No write."
                )
                return 0
            await set_flag(
                session,
                args.key,
                enabled=enabled,
                rollout_pct=args.rollout,
                actor=args.actor,
            )
            await session.commit()
            after = await is_enabled(session, args.key)
        print(
            f"OK : {args.key}  {'ON' if before else 'off'} → {'ON' if after else 'off'} "
            f"(rollout {args.rollout}%, actor={args.actor})."
        )
        if args.key in _dimension_flags() and enabled:
            print(
                "  → next session-card batch will freeze this dimension's vote onto the card "
                "and the verdict will fuse it. Witness one fresh card before activating the next."
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"DB connection failure : {exc!s}")
        return 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_set_feature_flag",
        description="Safe, auditable feature-flag toggle (set_flag: actor trail + Redis invalidate).",
    )
    parser.add_argument("key", nargs="?", help="feature flag key to toggle")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--on", action="store_true", help="enable the flag")
    g.add_argument("--off", action="store_true", help="disable the flag")
    parser.add_argument(
        "--rollout", type=int, default=100, help="rollout percent 0-100 (default 100)"
    )
    parser.add_argument("--actor", default="cli", help="updated_by audit actor (default 'cli')")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the intended change, do not write"
    )
    parser.add_argument("--list", action="store_true", help="list ALL feature flags + state")
    parser.add_argument(
        "--dimensions", action="store_true", help="list the S04 dimension-vote flags + state"
    )
    args = parser.parse_args(argv)
    if args.rollout < 0 or args.rollout > 100:
        parser.error("--rollout must be in [0, 100]")
    # Toggle-mode usage validation (pure, before any DB touch) unless a listing mode.
    if not (args.list or args.dimensions):
        if not args.key:
            parser.error("a flag KEY is required to toggle (or use --list / --dimensions)")
        if args.on == args.off:
            parser.error("choose exactly one of --on / --off")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
