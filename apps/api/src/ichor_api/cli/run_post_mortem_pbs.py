"""Phase D W116b — Penalized Brier Score post-mortem orchestrator (ADR-087).

Weekly Sunday 18:00 Paris cron. For each `(asset, regime)` pocket :

  1. Pull all session cards with `realized_scenario_bucket IS NOT NULL`
     AND `scenarios` JSONB NOT NULL over the last N=30 days.
  2. For each card, compute the **Ahmadian PBS** (Ahmadian 2025
     arXiv:2407.17697) on the 7-bucket scenarios vector :
        - p_vector built from `scenarios` JSONB in canonical
          BUCKET_LABELS order
        - realized_index = canonical index of
          `realized_scenario_bucket`
  3. Aggregate per pocket : mean PBS, n_obs, min/max, baseline gap
     (= mean PBS of equal-weight K=7 prediction = 1/7 over each bucket)
  4. Record ONE `auto_improvement_log` row per pocket
     (loop_kind='post_mortem', decision='adopted', metric_after=mean PBS,
     metric_before=baseline PBS).

This round-20 scope does NOT promote addenda to `pass3_addenda` yet —
that requires LLM-generated textual recommendations and is deferred to
W116c. The aggregate PBS rows in `auto_improvement_log` are the first-
class actionable surface : a human (or future LLM-meta) reads them and
decides where Pass-3 needs targeted improvement.

Usage :
  python -m ichor_api.cli.run_post_mortem_pbs [--asset CODE]
                                                [--window-days N]
                                                [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_engine, get_sessionmaker
from ..models import SessionCardAudit
from ..services.auto_improvement_log import record as record_audit
from ..services.penalized_brier import ahmadian_pbs, brier_score_multiclass

log = structlog.get_logger(__name__)


# Canonical 7-bucket order (ADR-085 §"The 7 buckets" — pinned by
# `test_pass6_bucket_labels_exactly_seven_canonical` invariant guard).
BUCKET_LABELS = (
    "crash_flush",
    "strong_bear",
    "mild_bear",
    "base",
    "mild_bull",
    "strong_bull",
    "melt_up",
)

_DEFAULT_WINDOW_DAYS = 30
_MIN_CARDS_PER_POCKET = 4
_AHMADIAN_LAMBDA = 2.0


def _p_vector_from_scenarios(scenarios_jsonb: Any) -> list[float] | None:
    """Extract 7-vector in canonical BUCKET_LABELS order. Returns None
    on any structural mismatch — caller skips the card."""
    if not isinstance(scenarios_jsonb, list) or len(scenarios_jsonb) != 7:
        return None
    p_map: dict[str, float] = {}
    for entry in scenarios_jsonb:
        if not isinstance(entry, dict):
            return None
        label = entry.get("label")
        p = entry.get("p")
        if not isinstance(label, str) or not isinstance(p, (int, float)):
            return None
        p_map[label] = float(p)
    if set(p_map.keys()) != set(BUCKET_LABELS):
        return None
    vec = [p_map[lbl] for lbl in BUCKET_LABELS]
    # Re-normalize defensively : the LLM output sums to ~1.0 with float
    # drift, the persisted vector should too, but tolerate small slop.
    total = sum(vec)
    if total <= 0.0:
        return None
    return [p / total for p in vec]


def _realized_index_from_bucket(bucket: str | None) -> int | None:
    """Canonical index of `realized_scenario_bucket` in BUCKET_LABELS.
    Returns None if the bucket label is unrecognized."""
    if bucket is None:
        return None
    try:
        return BUCKET_LABELS.index(bucket)
    except ValueError:
        return None


def _baseline_equal_weight_pbs(realized_index: int) -> float:
    """PBS of the uniform 1/7 prediction for any realized class.

    Closed form for K=7 uniform :
      BrierScore = (6/7)² + 6·(1/7)² = 36/49 + 6/49 = 42/49 ≈ 0.857
    argmax of uniform is ambiguous ; we treat it as a tie that fires
    the misclassification penalty (worst case → +λ = +2.0). The
    pocket's mean PBS should be MEANINGFULLY BELOW this baseline for
    the live LLM to have proper skill."""
    p = [1.0 / 7.0] * 7
    return brier_score_multiclass(p, realized_index) + _AHMADIAN_LAMBDA


def _pocket_key(card: SessionCardAudit) -> tuple[str, str]:
    """(asset, regime) — regime falls back to session_type when null."""
    regime = card.regime_quadrant if card.regime_quadrant else card.session_type
    return (card.asset, regime)


async def _distinct_pockets(session: AsyncSession, *, window_days: int) -> list[tuple[str, str]]:
    """Distinct (asset, regime) tuples with PBS-eligible cards over the
    window."""
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    stmt = (
        select(
            SessionCardAudit.asset,
            func.coalesce(SessionCardAudit.regime_quadrant, SessionCardAudit.session_type).label(
                "regime"
            ),
        )
        .where(SessionCardAudit.realized_scenario_bucket.is_not(None))
        .where(SessionCardAudit.generated_at >= cutoff)
        .distinct()
        .order_by(SessionCardAudit.asset)
    )
    rows = list((await session.execute(stmt)).all())
    return [(r[0], r[1]) for r in rows]


async def _aggregate_pocket(
    session: AsyncSession,
    *,
    asset: str,
    regime: str,
    window_days: int,
) -> dict[str, Any]:
    """Aggregate PBS over the pocket window. Returns summary dict."""
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    stmt = (
        select(SessionCardAudit)
        .where(SessionCardAudit.asset == asset)
        .where(
            func.coalesce(SessionCardAudit.regime_quadrant, SessionCardAudit.session_type) == regime
        )
        .where(SessionCardAudit.realized_scenario_bucket.is_not(None))
        .where(SessionCardAudit.scenarios.is_not(None))
        .where(SessionCardAudit.generated_at >= cutoff)
        .order_by(desc(SessionCardAudit.generated_at))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if len(rows) < _MIN_CARDS_PER_POCKET:
        return {"skipped": f"fewer than {_MIN_CARDS_PER_POCKET} eligible cards"}

    pbs_values: list[float] = []
    baseline_values: list[float] = []
    n_skipped_card = 0
    for card in rows:
        p_vec = _p_vector_from_scenarios(card.scenarios)
        if p_vec is None:
            n_skipped_card += 1
            continue
        r_idx = _realized_index_from_bucket(card.realized_scenario_bucket)
        if r_idx is None:
            n_skipped_card += 1
            continue
        try:
            pbs = ahmadian_pbs(
                p_vec,
                realized_index=r_idx,
                misclassification_penalty=_AHMADIAN_LAMBDA,
            )
        except ValueError:
            n_skipped_card += 1
            continue
        pbs_values.append(pbs)
        baseline_values.append(_baseline_equal_weight_pbs(r_idx))

    if not pbs_values:
        return {"skipped": f"no scoreable cards (n_skipped={n_skipped_card})"}

    mean_pbs = sum(pbs_values) / len(pbs_values)
    mean_baseline = sum(baseline_values) / len(baseline_values)
    return {
        "n_observations": len(pbs_values),
        "n_skipped_card": n_skipped_card,
        "mean_pbs": mean_pbs,
        "mean_baseline_pbs": mean_baseline,
        "pbs_gap": mean_pbs - mean_baseline,  # negative = pocket has skill
        "min_pbs": min(pbs_values),
        "max_pbs": max(pbs_values),
    }


async def _audit_pocket(*, asset: str, regime: str, summary: dict[str, Any]) -> UUID | None:
    """Record one auto_improvement_log row per pocket (loop_kind=
    'post_mortem'). Returns the new row UUID, or None on skip."""
    if summary.get("skipped") or summary.get("dry_run"):
        return None
    return await record_audit(
        loop_kind="post_mortem",
        trigger_event=f"weekly:run_post_mortem_pbs:{asset}:{regime}",
        asset=asset,
        regime=regime,
        input_summary={
            "n_observations": summary["n_observations"],
            "n_skipped_card": summary["n_skipped_card"],
            "ahmadian_lambda": _AHMADIAN_LAMBDA,
        },
        output_summary={
            "mean_pbs": summary["mean_pbs"],
            "mean_baseline_pbs": summary["mean_baseline_pbs"],
            "pbs_gap": summary["pbs_gap"],
            "min_pbs": summary["min_pbs"],
            "max_pbs": summary["max_pbs"],
            "has_skill_vs_baseline": summary["pbs_gap"] < 0.0,
        },
        metric_name="ahmadian_pbs_mean",
        metric_before=summary["mean_baseline_pbs"],
        metric_after=summary["mean_pbs"],
        decision="adopted",
        model_version="post_mortem_pbs_v1",
    )


async def _run(*, asset_filter: str | None, window_days: int, dry_run: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        pockets = await _distinct_pockets(session, window_days=window_days)
    if asset_filter:
        pockets = [(a, r) for (a, r) in pockets if a == asset_filter.upper()]
    if not pockets:
        print("no eligible (asset, regime) pockets")
        return 0

    print(
        f"== post_mortem_pbs · {len(pockets)} pocket(s) "
        f"window={window_days}d {'DRY-RUN' if dry_run else 'COMMIT'} =="
    )
    n_updated = 0
    n_skipped = 0
    for asset, regime in pockets:
        async with sm() as s2:
            summary = await _aggregate_pocket(
                s2, asset=asset, regime=regime, window_days=window_days
            )
        if summary.get("skipped"):
            n_skipped += 1
            log.info(
                "post_mortem_pbs.skip",
                asset=asset,
                regime=regime,
                reason=summary["skipped"],
            )
            print(f"-- {asset:10s} {regime:16s} skip · {summary['skipped']}")
            continue
        if dry_run:
            summary = {**summary, "dry_run": True}
        audit_id = await _audit_pocket(asset=asset, regime=regime, summary=summary)
        n_updated += 1
        skill_tag = "skill" if summary["pbs_gap"] < 0.0 else "no skill"
        log.info(
            "post_mortem_pbs.updated",
            asset=asset,
            regime=regime,
            audit_id=str(audit_id) if audit_id else None,
            n=summary["n_observations"],
            mean_pbs=round(summary["mean_pbs"], 4),
            baseline=round(summary["mean_baseline_pbs"], 4),
            gap=round(summary["pbs_gap"], 4),
        )
        print(
            f"OK {asset:10s} {regime:16s} n={summary['n_observations']:3d}  "
            f"pbs={summary['mean_pbs']:.3f} (base {summary['mean_baseline_pbs']:.3f}, "
            f"gap {summary['pbs_gap']:+.3f} {skill_tag})"
        )

    print(f"\n{n_updated} pocket(s) audited · {n_skipped} skipped")
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(
            asset_filter=args.asset,
            window_days=args.window_days,
            dry_run=args.dry_run,
        )
    finally:
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_post_mortem_pbs",
        description=(
            "Phase D W116b — weekly Penalized Brier Score post-mortem. "
            "Aggregates Ahmadian PBS per (asset, regime) over recent cards "
            "and writes one auto_improvement_log row per pocket."
        ),
    )
    parser.add_argument("--asset", type=str, default=None, help="restrict to one asset")
    parser.add_argument(
        "--window-days",
        type=int,
        default=_DEFAULT_WINDOW_DAYS,
        help=f"window in days (default {_DEFAULT_WINDOW_DAYS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="don't commit")
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
