"""Phase D W116c — addendum generator CLI (ADR-087, Voie D).

Weekly Sunday 19:00 Paris cron (after W116b PBS at 18:00). For each
recent auto_improvement_log row with `loop_kind='post_mortem'` AND
`output_summary.has_skill_vs_baseline = false`, calls the LLM (via
Couche-2 claude-runner path → Max plan, ZERO API spend) to generate
one short textual addendum and inserts it into `pass3_addenda` via
`record_new_addendum`.

Gated by feature flag `w116c_llm_addendum_enabled` (default False —
must be set explicitly via UPDATE feature_flags ... once W116b has
produced source data and you're ready to start LLM generation).

Usage :
  python -m ichor_api.cli.run_addendum_generator [--since-days N]
                                                  [--max-pockets N]
                                                  [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, select

from ..db import get_engine, get_sessionmaker
from ..models import AutoImprovementLog
from ..services.addendum_generator import generate_addendum_text
from ..services.auto_improvement_log import record as record_audit
from ..services.feature_flags import is_enabled
from ..services.pass3_addendum_injector import record_new_addendum

log = structlog.get_logger(__name__)


_DEFAULT_SINCE_DAYS = 7
_DEFAULT_MAX_POCKETS = 10
_DEFAULT_TTL_DAYS = 90.0
_FEATURE_FLAG_NAME = "w116c_llm_addendum_enabled"


async def _select_anti_skill_pockets(
    session: Any, *, since_days: int, limit: int
) -> list[AutoImprovementLog]:
    """Pull recent post_mortem audit rows where the pocket is shown
    NOT to have skill vs baseline (anti-skill = LLM forecaster worse
    than equal-weight)."""
    cutoff = datetime.now(UTC) - timedelta(days=since_days)
    stmt = (
        select(AutoImprovementLog)
        .where(AutoImprovementLog.loop_kind == "post_mortem")
        .where(AutoImprovementLog.ran_at >= cutoff)
        .where(AutoImprovementLog.asset.is_not(None))
        .order_by(desc(AutoImprovementLog.ran_at))
        .limit(limit * 3)  # over-fetch ; filter in Python on JSONB field
    )
    rows = list((await session.execute(stmt)).scalars().all())
    anti_skill: list[AutoImprovementLog] = []
    for r in rows:
        try:
            has_skill = bool(r.output_summary.get("has_skill_vs_baseline", True))
        except (AttributeError, TypeError):
            continue
        if not has_skill:
            anti_skill.append(r)
        if len(anti_skill) >= limit:
            break
    return anti_skill


async def _process_one_pocket(
    session: Any,
    *,
    row: AutoImprovementLog,
    runner_cfg: Any,
    dry_run: bool,
) -> dict[str, Any]:
    """Generate one addendum for one pocket. Returns summary."""
    asset = row.asset
    regime = row.regime or "unknown"
    if not asset:
        return {"skipped": "no asset on audit row"}

    out = row.output_summary or {}
    skill_delta = float(out.get("pbs_gap", 0.0))  # positive PBS gap = LLM worse
    mean_pbs = float(out.get("mean_pbs", 0.0))
    mean_baseline = float(out.get("mean_baseline_pbs", 0.0))
    in_sum = row.input_summary or {}
    n_obs = int(in_sum.get("n_observations", 0))

    # W116b stores skill_delta = mean_pbs - mean_baseline_pbs ; NEGATIVE
    # gap = LLM has skill (PBS lower than baseline). We want anti-skill
    # candidates : positive gap (mean_pbs > baseline). Flip the sign so
    # the prompt sees "anti-skill = negative skill_delta" (matches the
    # /v1/phase-d/pocket-summary convention).
    pocket_skill_delta = -skill_delta

    result = await generate_addendum_text(
        asset=asset,
        regime=regime,
        skill_delta=pocket_skill_delta,
        mean_pbs=mean_pbs,
        mean_baseline_pbs=mean_baseline,
        n_observations=n_obs,
        latest_drift_event_at=None,  # W116c v1 : not joined yet ; future round
        runner_cfg=runner_cfg,
    )
    if result is None:
        return {"skipped": "LLM call failed or ADR-017 violation"}

    if dry_run:
        return {
            "dry_run": True,
            "addendum_text": result.addendum_text,
            "importance": result.importance,
        }

    new_id = await record_new_addendum(
        session,
        regime=regime,
        asset=asset,
        content=result.addendum_text,
        importance=result.importance,
        source_card_id=None,  # W116c sources from audit_log not session_card
        ttl_days=_DEFAULT_TTL_DAYS,
    )
    await session.commit()
    return {
        "id": str(new_id),
        "addendum_text": result.addendum_text,
        "importance": result.importance,
    }


async def _run(*, since_days: int, max_pockets: int, dry_run: bool) -> int:
    sm = get_sessionmaker()

    # Feature flag check — fail-closed if disabled.
    async with sm() as flag_session:
        enabled = await is_enabled(flag_session, _FEATURE_FLAG_NAME)
    if not enabled:
        print(
            f"feature flag {_FEATURE_FLAG_NAME!r} is OFF — skipping "
            "W116c LLM addendum generation (set to true via UPDATE "
            "feature_flags ... once you're ready)."
        )
        return 0

    # Build the claude-runner config (ADR-023 : Haiku low for Couche-2
    # / W116c — keeps LLM cost low + stays under CF Free 100s edge cap).
    try:
        from ichor_agents.claude_runner import ClaudeRunnerConfig

        runner_cfg = ClaudeRunnerConfig.from_env(model="haiku", effort="low")
    except ImportError as e:
        print(f"ichor_agents not installed : {e}", file=sys.stderr)
        return 3
    if runner_cfg is None:
        print(
            "ICHOR_API_CLAUDE_RUNNER_URL unset — cannot route W116c LLM "
            "via claude-runner (ADR-009 Voie D forbids any other path).",
            file=sys.stderr,
        )
        return 4

    # Select recent anti-skill pockets.
    async with sm() as query_session:
        rows = await _select_anti_skill_pockets(
            query_session, since_days=since_days, limit=max_pockets
        )
    if not rows:
        print(f"no anti-skill post_mortem rows in last {since_days} d")
        return 0

    print(
        f"== w116c · {len(rows)} pocket(s) since {since_days}d "
        f"{'DRY-RUN' if dry_run else 'COMMIT'} =="
    )

    n_inserted = 0
    n_skipped = 0
    for row in rows:
        async with sm() as proc_session:
            summary = await _process_one_pocket(
                proc_session, row=row, runner_cfg=runner_cfg, dry_run=dry_run
            )
        if summary.get("skipped"):
            n_skipped += 1
            log.info(
                "w116c.skip",
                asset=row.asset,
                regime=row.regime,
                reason=summary["skipped"],
            )
            print(f"-- {row.asset:10s} {row.regime or '-':16s} skip · {summary['skipped']}")
            continue
        n_inserted += 1
        log.info(
            "w116c.addendum_generated",
            asset=row.asset,
            regime=row.regime,
            importance=summary["importance"],
        )
        print(
            f"OK {row.asset:10s} {row.regime or '-':16s} "
            f"imp={summary['importance']:.2f} : {summary['addendum_text'][:80]!r}"
        )

        # Audit the W116c run itself (loop_kind='meta_prompt' is the
        # closest fit per ADR-087 — W117 GEPA also uses meta_prompt for
        # its addendum-equivalent decisions).
        if not dry_run:
            await record_audit(
                loop_kind="meta_prompt",
                trigger_event=f"weekly:run_addendum_generator:{row.asset}:{row.regime}",
                asset=row.asset,
                regime=row.regime,
                input_summary={
                    "source_audit_id": str(row.id),
                    "n_observations": int((row.input_summary or {}).get("n_observations", 0)),
                },
                output_summary={
                    "addendum_id": summary["id"],
                    "importance": summary["importance"],
                    "text_preview": summary["addendum_text"][:80],
                },
                metric_name="addendum_importance",
                metric_after=summary["importance"],
                decision="adopted",
                model_version="w116c_addendum_v1_haiku_low",
            )

    print(f"\n{n_inserted} addendum(s) inserted · {n_skipped} skipped")
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(
            since_days=args.since_days,
            max_pockets=args.max_pockets,
            dry_run=args.dry_run,
        )
    finally:
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_addendum_generator",
        description=(
            "Phase D W116c — weekly LLM addendum generator. Reads recent "
            "post_mortem anti-skill audit rows, calls the LLM via "
            "claude-runner (Voie D, Max plan, Haiku low), inserts the "
            "generated text into pass3_addenda."
        ),
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=_DEFAULT_SINCE_DAYS,
        help=f"window of post_mortem rows to consider (default {_DEFAULT_SINCE_DAYS})",
    )
    parser.add_argument(
        "--max-pockets",
        type=int,
        default=_DEFAULT_MAX_POCKETS,
        help=f"max pockets per run (default {_DEFAULT_MAX_POCKETS}, rate-limit guard)",
    )
    parser.add_argument("--dry-run", action="store_true", help="don't commit, don't write audit")
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
