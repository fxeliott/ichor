"""GET /v1/phase-d — read-only Phase D auto-improvement observability.

Surfaces the ADR-087 Phase D learn loop state via API instead of
SSH+psql. Exposes :

  - GET /v1/phase-d/audit-log          → recent `auto_improvement_log`
                                          rows (W113 audit table)
  - GET /v1/phase-d/aggregator-weights → current Vovk-AA pocket weights
                                          (W115 brier_aggregator_weights)

This router is INTENTIONALLY pure-data : the rows are computed by
nightly crons (W114 ADWIN drift, W115b Vovk aggregator, W116b PBS
post-mortem), the API only READS. No mutation paths — Phase D
loops are write-only via dedicated CLI scripts.

Routes are deliberately excluded from the AI watermark middleware
(ADR-079) — the data is collector / aggregator output, not
AI-generated content.

ADR-078 invariant : `auto_improvement_log` is NOT in the Cap5
`query_db` allowlist (frozenset of 6 tables) ; this read-only router
is the canonical operator surface for inspecting it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import AutoImprovementLog, BrierAggregatorWeight, Pass3Addendum

router = APIRouter(prefix="/v1/phase-d", tags=["phase-d"])


# ──────────────────────────── Response shapes ──────────────────────────


class AuditLogEntryOut(BaseModel):
    """One row of `auto_improvement_log` projected to the API surface."""

    id: UUID
    loop_kind: str
    trigger_event: str
    asset: str | None
    regime: str | None
    input_summary: dict[str, Any]
    output_summary: dict[str, Any]
    metric_before: float | None
    metric_after: float | None
    metric_name: str
    decision: str
    disposition: str | None
    model_version: str | None
    parent_id: UUID | None
    ran_at: datetime


class AuditLogListOut(BaseModel):
    rows: list[AuditLogEntryOut]
    count: int
    window_days: int | None
    loop_kind_filter: str | None


class AggregatorWeightOut(BaseModel):
    """One row of `brier_aggregator_weights` projected to the API."""

    id: UUID
    asset: str
    regime: str
    expert_kind: str
    weight: float
    n_observations: int
    cumulative_loss: float
    pocket_version: int
    updated_at: datetime


class AggregatorWeightsListOut(BaseModel):
    rows: list[AggregatorWeightOut]
    count: int
    asset_filter: str | None
    regime_filter: str | None
    pocket_version: int


class Pass3AddendumOut(BaseModel):
    """One row of `pass3_addenda` projected to the API surface."""

    id: UUID
    regime: str
    asset: str | None
    content: str
    importance: float
    status: str
    source_card_id: UUID | None
    created_at: datetime
    expires_at: datetime
    superseded_by: UUID | None


class Pass3AddendaListOut(BaseModel):
    rows: list[Pass3AddendumOut]
    count: int
    regime_filter: str | None
    asset_filter: str | None
    status_filter: str


# ──────────────────────────── /audit-log ──────────────────────────


_VALID_LOOP_KINDS = frozenset({"brier_aggregator", "adwin_drift", "post_mortem", "meta_prompt"})


@router.get("/audit-log", response_model=AuditLogListOut)
async def list_audit_log(
    session: Annotated[AsyncSession, Depends(get_session)],
    loop_kind: Annotated[
        str | None,
        Query(
            description=(
                "Restrict to one ADR-087 loop kind : "
                "brier_aggregator | adwin_drift | post_mortem | meta_prompt"
            ),
        ),
    ] = None,
    asset: Annotated[
        str | None,
        Query(
            pattern=r"^[A-Z0-9_]{3,16}$",
            description="Optional asset filter (e.g. EUR_USD).",
        ),
    ] = None,
    regime: Annotated[
        str | None,
        Query(
            pattern=r"^[a-z_]{2,64}$",
            description="Optional regime filter (e.g. usd_complacency).",
        ),
    ] = None,
    since_days: Annotated[
        int,
        Query(ge=1, le=365, description="Rolling window in days (default 7)."),
    ] = 7,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Max rows (default 100)."),
    ] = 100,
) -> AuditLogListOut:
    """List recent `auto_improvement_log` rows.

    Defaults to the last 7 days, ordered by `ran_at DESC`. Use the
    filters to narrow by loop kind / asset / regime. The endpoint is
    READ-ONLY — Phase D rows are written only by the dedicated
    nightly cron CLIs (`run_brier_aggregator`, `run_post_mortem_pbs`,
    and the inline drift dispatcher in `reconcile_outcomes`).
    """
    if loop_kind is not None and loop_kind not in _VALID_LOOP_KINDS:
        # Don't 400 ; just return empty for unknown kinds — keeps the
        # API tolerant of typo'd queries from operators.
        return AuditLogListOut(
            rows=[],
            count=0,
            window_days=since_days,
            loop_kind_filter=loop_kind,
        )

    cutoff = datetime.now(UTC) - timedelta(days=since_days)
    stmt = (
        select(AutoImprovementLog)
        .where(AutoImprovementLog.ran_at >= cutoff)
        .order_by(desc(AutoImprovementLog.ran_at))
        .limit(limit)
    )
    if loop_kind is not None:
        stmt = stmt.where(AutoImprovementLog.loop_kind == loop_kind)
    if asset is not None:
        stmt = stmt.where(AutoImprovementLog.asset == asset)
    if regime is not None:
        stmt = stmt.where(AutoImprovementLog.regime == regime)

    rows = (await session.execute(stmt)).scalars().all()
    out = [
        AuditLogEntryOut(
            id=r.id,
            loop_kind=r.loop_kind,
            trigger_event=r.trigger_event,
            asset=r.asset,
            regime=r.regime,
            input_summary=r.input_summary,
            output_summary=r.output_summary,
            metric_before=r.metric_before,
            metric_after=r.metric_after,
            metric_name=r.metric_name,
            decision=r.decision,
            disposition=r.disposition,
            model_version=r.model_version,
            parent_id=r.parent_id,
            ran_at=r.ran_at,
        )
        for r in rows
    ]
    return AuditLogListOut(
        rows=out,
        count=len(out),
        window_days=since_days,
        loop_kind_filter=loop_kind,
    )


# ──────────────────────────── /aggregator-weights ──────────────────────────


@router.get("/aggregator-weights", response_model=AggregatorWeightsListOut)
async def list_aggregator_weights(
    session: Annotated[AsyncSession, Depends(get_session)],
    asset: Annotated[
        str | None,
        Query(
            pattern=r"^[A-Z0-9_]{3,16}$",
            description="Optional asset filter.",
        ),
    ] = None,
    regime: Annotated[
        str | None,
        Query(
            pattern=r"^[a-z_]{2,64}$",
            description="Optional regime filter.",
        ),
    ] = None,
    pocket_version: Annotated[
        int,
        Query(ge=1, description="Pocket version (default 1)."),
    ] = 1,
) -> AggregatorWeightsListOut:
    """List current Vovk-AA pocket weights.

    Returns 3 rows per (asset, regime) pocket — one for each
    `expert_kind` (prod_predictor / climatology / equal_weight).
    Ordered by `(asset, regime, expert_kind)`.

    Use this endpoint to inspect WHICH (asset, regime) pockets the
    live LLM forecaster has discrimination skill on (high
    `prod_predictor.weight` + low `prod_predictor.cumulative_loss`)
    vs which pockets need attention (prod_predictor weight ≤
    equal_weight weight).
    """
    stmt = (
        select(BrierAggregatorWeight)
        .where(BrierAggregatorWeight.pocket_version == pocket_version)
        .order_by(
            BrierAggregatorWeight.asset,
            BrierAggregatorWeight.regime,
            BrierAggregatorWeight.expert_kind,
        )
    )
    if asset is not None:
        stmt = stmt.where(BrierAggregatorWeight.asset == asset)
    if regime is not None:
        stmt = stmt.where(BrierAggregatorWeight.regime == regime)

    rows = (await session.execute(stmt)).scalars().all()
    out = [
        AggregatorWeightOut(
            id=r.id,
            asset=r.asset,
            regime=r.regime,
            expert_kind=r.expert_kind,
            weight=r.weight,
            n_observations=r.n_observations,
            cumulative_loss=r.cumulative_loss,
            pocket_version=r.pocket_version,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    return AggregatorWeightsListOut(
        rows=out,
        count=len(out),
        asset_filter=asset,
        regime_filter=regime,
        pocket_version=pocket_version,
    )


# ──────────────────────────── /pass3-addenda ──────────────────────────


_VALID_ADDENDUM_STATUSES = frozenset({"active", "expired", "superseded", "rejected"})


@router.get("/pass3-addenda", response_model=Pass3AddendaListOut)
async def list_pass3_addenda(
    session: Annotated[AsyncSession, Depends(get_session)],
    regime: Annotated[
        str | None,
        Query(
            pattern=r"^[a-z_]{2,64}$",
            description="Optional regime filter (e.g. usd_complacency).",
        ),
    ] = None,
    asset: Annotated[
        str | None,
        Query(
            pattern=r"^[A-Z0-9_]{3,16}$",
            description="Optional asset filter.",
        ),
    ] = None,
    status: Annotated[
        str,
        Query(
            description=(
                "Addendum lifecycle filter : active | expired | "
                "superseded | rejected (default 'active')."
            ),
        ),
    ] = "active",
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Max rows (default 100)."),
    ] = 100,
) -> Pass3AddendaListOut:
    """List `pass3_addenda` rows.

    Defaults to `status='active'`, ordered by `importance DESC`. The
    actual Pass-3 injection consumer is
    `services.pass3_addendum_injector.select_active_addenda` which
    applies an exponential decay re-rank in-Python on top of this DB
    sort — this endpoint surfaces the raw rows for operator
    inspection, NOT the decay-weighted selection.

    Unknown status values return empty (lenient — typo'd queries
    don't 400).
    """
    if status not in _VALID_ADDENDUM_STATUSES:
        return Pass3AddendaListOut(
            rows=[],
            count=0,
            regime_filter=regime,
            asset_filter=asset,
            status_filter=status,
        )

    stmt = (
        select(Pass3Addendum)
        .where(Pass3Addendum.status == status)
        .order_by(desc(Pass3Addendum.importance))
        .limit(limit)
    )
    if regime is not None:
        stmt = stmt.where(Pass3Addendum.regime == regime)
    if asset is not None:
        stmt = stmt.where(Pass3Addendum.asset == asset)

    rows = (await session.execute(stmt)).scalars().all()
    out = [
        Pass3AddendumOut(
            id=r.id,
            regime=r.regime,
            asset=r.asset,
            content=r.content,
            importance=r.importance,
            status=r.status,
            source_card_id=r.source_card_id,
            created_at=r.created_at,
            expires_at=r.expires_at,
            superseded_by=r.superseded_by,
        )
        for r in rows
    ]
    return Pass3AddendaListOut(
        rows=out,
        count=len(out),
        regime_filter=regime,
        asset_filter=asset,
        status_filter=status,
    )
