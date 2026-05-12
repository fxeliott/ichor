"""Phase D W115b — Vovk-Zhdanov AA Brier aggregator nightly cron.

Runs after the W105g reconciler (nightly 02:00 Paris) populates fresh
`session_card_audit.realized_*` columns. For each `(asset, regime)`
pocket :

  1. Pull the last N=200 reconciled cards.
  2. For each card, build 3 expert predictions :
     - Expert A (`prod_predictor`)  = card's conviction-derived p_up
                                       (the live LLM-generated forecast)
     - Expert B (`climatology`)     = empirical historical p_up rate
                                       for `(asset, session_type)` over
                                       the past 365 d (or all-time if
                                       window is short)
     - Expert C (`equal_weight`)    = 0.5 constant no-info baseline
  3. Replay through `VovkBrierAggregator(n_experts=3)`. Stateless re-
     feed each run — matches W114 pattern, makes the algorithm
     trivially debuggable.
  4. Upsert 3 rows in `brier_aggregator_weights` for
     `(asset, regime, expert_kind, pocket_version=1)`.
  5. Record ONE `auto_improvement_log` row per pocket
     (`loop_kind='brier_aggregator'`).

`regime` choice : we use `session_card_audit.regime_quadrant` when
non-NULL, falling back to `session_type` as the pocket key. ADR-087
treats "regime" as the Vovk-pocket grouping abstraction — the column
labeling stays "regime" because future macro-regime extraction (W118+)
will populate `regime_quadrant` directly and the CLI keeps working.

Usage :
  python -m ichor_api.cli.run_brier_aggregator [--asset CODE]
                                                [--window N]
                                                [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_engine, get_sessionmaker
from ..models import BrierAggregatorWeight, SessionCardAudit
from ..services.auto_improvement_log import record as record_audit
from ..services.brier import conviction_to_p_up
from ..services.vovk_aggregator import VovkBrierAggregator

log = structlog.get_logger(__name__)


_EXPERT_KINDS = ("prod_predictor", "climatology", "equal_weight")
_POCKET_VERSION = 1
_DEFAULT_WINDOW = 200
_CLIMATOLOGY_LOOKBACK_DAYS = 365


async def _distinct_pockets(session: AsyncSession) -> list[tuple[str, str]]:
    """Return distinct (asset, regime) tuples from recent scored cards.

    `regime` uses `regime_quadrant` when non-NULL, else `session_type`.
    """
    stmt = (
        select(
            SessionCardAudit.asset,
            func.coalesce(SessionCardAudit.regime_quadrant, SessionCardAudit.session_type).label(
                "regime"
            ),
        )
        .where(SessionCardAudit.brier_contribution.is_not(None))
        .distinct()
        .order_by(SessionCardAudit.asset)
    )
    rows = list((await session.execute(stmt)).all())
    return [(r[0], r[1]) for r in rows]


async def _climatology_rate(session: AsyncSession, asset: str) -> float:  # noqa: ARG001
    """Empirical historical P(y=1) for this asset.

    Round-19 stand-in : returns 0.5 (no-info baseline). Computing the
    real climatology requires `realized_open_session` on the card row,
    which we don't persist — the reconciler only stores
    `realized_close_session`, `realized_high_session`,
    `realized_low_session`. Re-querying Polygon bars per card would
    double the cron's DB pressure ; for round-19 the climatology expert
    is a no-info tie-breaker that the Vovk AA will down-weight if it
    proves uninformative.

    TODO W118 : add `realized_open_session` column to
    `session_card_audit` so this function can compute the real
    empirical y=1 rate per `(asset, session_type)` over the last
    365 d window. The Vovk update will then have a genuinely
    informative second expert.
    """
    return 0.5


def _expert_predictions(card: SessionCardAudit, climatology: float) -> list[float]:
    """3-expert vector for one card : [prod, climatology, equal_weight]."""
    bias = card.bias_direction
    if bias not in ("long", "short", "neutral"):
        # Defensive : skip malformed rows.
        return [0.5, climatology, 0.5]
    p_prod = conviction_to_p_up(bias, card.conviction_pct)  # type: ignore[arg-type]
    return [p_prod, climatology, 0.5]


def _realized_from_card(card: SessionCardAudit) -> int | None:
    """Derive y ∈ {0, 1} from a reconciled card. None if unknown.

    The reconciler stores `brier_contribution = (p_up - y)²` but NOT
    a dedicated y column. We back-derive y by matching the observed
    Brier against the two candidate formulas :

        BS(y=0) = p_up²
        BS(y=1) = (p_up - 1)²

    Pick whichever matches `brier_contribution` within float tolerance.
    This works even when the predictor was WRONG (BS large) — we just
    need to identify which y produced the observed score.

    Returns None when :
    - `brier_contribution` is NULL (not yet reconciled),
    - `bias_direction` is unrecognized,
    - neither formula matches (data corruption / schema drift).
    """
    if card.brier_contribution is None:
        return None
    bias = card.bias_direction
    if bias not in ("long", "short", "neutral"):
        return None
    p_up = conviction_to_p_up(bias, card.conviction_pct)  # type: ignore[arg-type]
    # Neutral / p_up==0.5 cards have bs0 == bs1 == 0.25 — both candidate
    # formulas match the observed Brier identically, so we can't recover
    # y. Skip them (they provide no Vovk learning signal anyway since
    # all 3 experts agree at 0.5).
    if abs(p_up - 0.5) < 1e-9:
        return None
    bs0 = p_up * p_up
    bs1 = (p_up - 1.0) ** 2
    diff0 = abs(card.brier_contribution - bs0)
    diff1 = abs(card.brier_contribution - bs1)
    # Pick the closer match. Tolerance 1e-6 covers reconciler float
    # drift ; if BOTH formulas miss by > tolerance, return None.
    if diff0 <= 1e-6 and diff0 < diff1:
        return 0
    if diff1 <= 1e-6 and diff1 < diff0:
        return 1
    return None


async def _aggregate_one_pocket(
    session: AsyncSession,
    *,
    asset: str,
    regime: str,
    window: int,
    dry_run: bool,
) -> dict[str, Any]:
    """Run one Vovk pocket update. Returns a summary dict for logging."""
    cards_stmt = (
        select(SessionCardAudit)
        .where(SessionCardAudit.asset == asset)
        .where(
            func.coalesce(SessionCardAudit.regime_quadrant, SessionCardAudit.session_type) == regime
        )
        .where(SessionCardAudit.brier_contribution.is_not(None))
        .order_by(desc(SessionCardAudit.generated_at))
        .limit(window)
    )
    rows = list((await session.execute(cards_stmt)).scalars().all())
    cards = list(reversed(rows))  # chronological order for AA

    if len(cards) < 4:
        return {"skipped": "fewer than 4 reconciled cards"}

    climatology = await _climatology_rate(session, asset)

    agg = VovkBrierAggregator(n_experts=3)
    for card in cards:
        y = _realized_from_card(card)
        if y is None:
            continue
        preds = _expert_predictions(card, climatology)
        agg.update(preds, y)

    weights = list(agg.weights)
    cumulative = list(agg.cumulative_losses)
    n_obs = agg.n_observations

    if dry_run:
        return {
            "dry_run": True,
            "weights": dict(zip(_EXPERT_KINDS, weights, strict=True)),
            "cumulative_losses": dict(zip(_EXPERT_KINDS, cumulative, strict=True)),
            "n_observations": n_obs,
        }

    # Upsert 3 rows : one per expert. ON CONFLICT (asset, regime,
    # expert_kind, pocket_version) DO UPDATE.
    for kind, w, cl in zip(_EXPERT_KINDS, weights, cumulative, strict=True):
        stmt = (
            pg_insert(BrierAggregatorWeight)
            .values(
                asset=asset,
                regime=regime,
                expert_kind=kind,
                weight=w,
                n_observations=n_obs,
                cumulative_loss=cl,
                pocket_version=_POCKET_VERSION,
            )
            .on_conflict_do_update(
                constraint="uq_brier_agg_pocket_expert",
                set_={
                    "weight": w,
                    "n_observations": n_obs,
                    "cumulative_loss": cl,
                    "updated_at": func.clock_timestamp(),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()

    return {
        "weights": dict(zip(_EXPERT_KINDS, weights, strict=True)),
        "cumulative_losses": dict(zip(_EXPERT_KINDS, cumulative, strict=True)),
        "n_observations": n_obs,
    }


async def _audit_pocket_update(*, asset: str, regime: str, summary: dict[str, Any]) -> UUID | None:
    """Record one `auto_improvement_log` row per pocket update. Returns
    the new row UUID, or None if the pocket was skipped."""
    if summary.get("skipped") or summary.get("dry_run"):
        return None
    return await record_audit(
        loop_kind="brier_aggregator",
        trigger_event=f"cron:run_brier_aggregator:{asset}:{regime}",
        asset=asset,
        regime=regime,
        input_summary={
            "n_observations": summary["n_observations"],
            "expert_kinds": list(_EXPERT_KINDS),
        },
        output_summary={
            "weights": summary["weights"],
            "cumulative_losses": summary["cumulative_losses"],
            "pocket_version": _POCKET_VERSION,
        },
        metric_name="vovk_cumulative_loss",
        metric_before=None,
        metric_after=min(summary["cumulative_losses"].values()),
        decision="adopted",
        model_version="vovk_aa_v1_eta_1",
    )


async def _run(*, asset_filter: str | None, window: int, dry_run: bool) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        pockets = await _distinct_pockets(session)
    if asset_filter:
        pockets = [(a, r) for (a, r) in pockets if a == asset_filter.upper()]
    if not pockets:
        print("no eligible (asset, regime) pockets")
        return 0

    print(f"== brier_aggregator · {len(pockets)} pocket(s) {'DRY-RUN' if dry_run else 'COMMIT'} ==")
    n_updated = 0
    n_skipped = 0
    for asset, regime in pockets:
        async with sm() as s2:
            summary = await _aggregate_one_pocket(
                s2,
                asset=asset,
                regime=regime,
                window=window,
                dry_run=dry_run,
            )
        if summary.get("skipped"):
            n_skipped += 1
            log.info(
                "brier_aggregator.skip",
                asset=asset,
                regime=regime,
                reason=summary["skipped"],
            )
            print(f"-- {asset:10s} {regime:14s} skip · {summary['skipped']}")
            continue
        n_updated += 1
        audit_id = await _audit_pocket_update(asset=asset, regime=regime, summary=summary)
        log.info(
            "brier_aggregator.updated",
            asset=asset,
            regime=regime,
            audit_id=str(audit_id) if audit_id else None,
            n_observations=summary["n_observations"],
            weights=summary["weights"],
        )
        weights_str = " ".join(f"{k}={v:.3f}" for k, v in summary["weights"].items())
        print(f"OK {asset:10s} {regime:14s} n={summary['n_observations']:4d}  {weights_str}")

    print(f"\n{n_updated} pocket(s) updated · {n_skipped} skipped")
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(
            asset_filter=args.asset,
            window=args.window,
            dry_run=args.dry_run,
        )
    finally:
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_brier_aggregator",
        description=(
            "Phase D W115b — Vovk-Zhdanov AA Brier aggregator nightly cron. "
            "Updates `brier_aggregator_weights` and writes one "
            "`auto_improvement_log` row per (asset, regime) pocket."
        ),
    )
    parser.add_argument("--asset", type=str, default=None, help="restrict to one asset")
    parser.add_argument(
        "--window",
        type=int,
        default=_DEFAULT_WINDOW,
        help=f"sliding window per pocket (default {_DEFAULT_WINDOW})",
    )
    parser.add_argument("--dry-run", action="store_true", help="don't commit")
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
