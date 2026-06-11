"""r165 Strand F — Scenario Invalidation cron CLI.

Reads recent ``session_card_audit`` rows + evaluates each populated
``invalidations[]`` list via the r164 monitor service + emits canonical
Ichor Alert rows via the r165 alerts pipeline (de-dup + persist).

Cadence : 6×/jour Paris (00, 04, 08, 12, 16, 20) — see
``scripts/hetzner/register-cron-scenario-invalidation-check.sh`` for the
systemd timer. Cadence rationale per ADR-106 §D3 :

  - 00h : end-of-day cleanup, captures any invalidation that fired
    during the NY session post-20h cutoff but before the user's
    next-day briefing emission.
  - 04h : pre-Tokyo opening, captures overnight FX/commodity moves.
  - 08h : pre-London opening, captures pre-EU-session repricing.
  - 12h : peri-briefing, captures the pre-NY session window.
  - 16h : mid-NY session, captures invalidations DURING the trader's
    14h-20h Paris execution window.
  - 20h : end-of-NY-session, captures final-hour moves before the
    verdict expires_at_utc (20h15 Paris).

Gated by feature flag ``scenario_invalidation_monitor_enabled``
(default False ; activate via ``UPDATE feature_flags ...`` once Pass-6
populated path is empirically validated ≥3 production sessions per
ADR-106 §"Carry-forward r166").

Voie D : zero LLM call, pure SQL + Python comparisons via the r164
monitor service. The cron stays within the Voie D ceiling at runtime.

Usage :

    python -m ichor_api.cli.run_scenario_invalidation_check
                                                    [--dry-run]
                                                    [--lookback-hours N]

Exit codes :

    0 : success (zero or more alerts emitted + persisted)
    1 : feature flag is OFF — clean skip, NOT a failure
    3 : DB connection failure — cron infra issue (retry next tick)

ADR refs : ADR-106 §175 Stride 1 + §D3 refresh cycle ; ADR-085 Pass-6 ;
ADR-099 §Impl(r165) ; ADR-030 ResolveCron canonical pattern.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import traceback

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.alerts_runner import check_scenario_invalidations
from ..services.feature_flags import is_enabled

log = structlog.get_logger(__name__)

_FEATURE_FLAG_NAME = "scenario_invalidation_monitor_enabled"

DEFAULT_LOOKBACK_HOURS = 24


async def _run(
    *,
    dry_run: bool,
    lookback_hours: int,
) -> int:
    """Run the scenario invalidation check once. Returns shell exit code.

    Exit codes (mirror of ``run_economic_event_actuals_reconcile.py``
    convention) :
      0 : success — N alerts emitted + persisted (N may be 0)
      1 : feature flag OFF — clean skip
      3 : DB connection failure
    """
    sm = get_sessionmaker()

    # Feature flag check — fail-closed if disabled. S03 exception : a
    # ``--dry-run`` evaluates EVEN with the flag OFF — that is the whole
    # point of the ≥3-session empirical validation the flag's arming is
    # gated on (ADR-106 §Carry-forward r166): the monitor must run against
    # real prod cards, read-only + rolled back, to ACCUMULATE the evidence
    # while staying un-armed. Before this exception the flag gated the
    # dry-run too, so the validation could never start (S03 audit
    # 2026-06-11). Persisting runs stay strictly flag-gated.
    try:
        async with sm() as flag_session:
            enabled = await is_enabled(flag_session, _FEATURE_FLAG_NAME)
    except Exception as exc:
        print(
            f"DB connection failure during feature flag check : {exc!s}. Cron will retry next tick."
        )
        return 3

    if not enabled and not dry_run:
        print(
            f"feature flag {_FEATURE_FLAG_NAME!r} is OFF — skipping "
            "scenario invalidation monitor cron. Activate via :\n"
            "  UPDATE feature_flags SET enabled = true "
            f"WHERE key = '{_FEATURE_FLAG_NAME}' ;\n"
            "(once Pass-6 populated path is empirically validated "
            "≥3 production sessions per ADR-106 §Carry-forward r166 — "
            "accumulate that evidence with --dry-run runs, which evaluate "
            "flag-OFF and always roll back)."
        )
        return 1

    if not enabled and dry_run:
        print(
            f"VALIDATION MODE — {_FEATURE_FLAG_NAME!r} is OFF, dry-run "
            "forced evaluation (read-only, rolled back). Each such run is "
            "one piece of the ≥3-session arming evidence (journalctl is "
            "the validation log)."
        )

    print(f"== scenario invalidation check · lookback={lookback_hours}h · dry_run={dry_run} ==")

    async with sm() as session:
        try:
            persisted = await check_scenario_invalidations(
                session,
                lookback_hours=lookback_hours,
            )
        except Exception as exc:
            log.error(
                "scenario_invalidation_check.failed",
                error=str(exc)[:500],
                traceback=traceback.format_exc()[:2000],
            )
            print(f"scenario invalidation check failed : {exc!s}")
            return 3

        if dry_run:
            # Rollback so nothing lands when smoke-testing.
            await session.rollback()
            print(f"DRY-RUN · would have persisted {len(persisted)} alerts ; session rolled back.")
        else:
            await session.commit()

    log.info(
        "scenario_invalidation_check.complete",
        n_persisted=len(persisted),
        dry_run=dry_run,
        lookback_hours=lookback_hours,
        codes=[hit.alert_def.code for hit in persisted],
        assets=[hit.source_payload.get("asset") for hit in persisted],
    )

    print(
        f"OK · persisted={len(persisted)} alerts "
        f"(severity breakdown : "
        f"hard={sum(1 for h in persisted if h.alert_def.severity == 'critical')} "
        f"soft={sum(1 for h in persisted if h.alert_def.severity == 'warning')} "
        f"note={sum(1 for h in persisted if h.alert_def.severity == 'info')})"
    )
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(
            dry_run=args.dry_run,
            lookback_hours=args.lookback_hours,
        )
    finally:
        await get_engine().dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scenario invalidation cron — read recent session cards, "
            "evaluate populated invalidations via r164 monitor, emit "
            "canonical Ichor alerts via r165 alerts pipeline. "
            "Cron-friendly, feature-flag-gated, idempotent (dedup per "
            "alert_code+asset window)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Smoke test : query + log but ROLL BACK the session, do NOT "
            "persist any alerts. Useful for first-fire validation post-deploy."
        ),
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help=(
            f"Hours of recent session cards to consider (default "
            f"{DEFAULT_LOOKBACK_HOURS}). Older cards' invalidations are "
            "ignored (their verdicts have likely already expired)."
        ),
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
