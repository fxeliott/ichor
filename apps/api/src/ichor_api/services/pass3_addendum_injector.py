"""Phase D W116 — Pass-3 addendum injector (ADR-087).

Selects the top-K active addenda for a regime via a score-based
eviction policy with exponential decay. The selection is the READ
path consumed by the orchestrator just before Pass-3 prompt assembly.

Score model :

    effective_score(addendum) = importance · exp(−Δt / τ)

where Δt = `now() - created_at`, τ = `decay_halflife_days · ln(2)⁻¹`.

* `importance` = W116 PBS evaluator's Brier-improvement attribution
  (higher → addendum more valuable).
* Decay : score halves every `decay_halflife_days` days (default 30).
* Hard cap : ≤ `max_active` returned per call (default 3).
* Hard cutoff : `status='active' AND expires_at > now()`.

The DB index `ix_pass3_addenda_regime_active_importance` is the hot
path. Decay weighting happens in-Python after the DB pulls a small
candidate pool (size ≈ N_active_for_regime, typically <30).

This module also exposes `record_new_addendum(...)` — the WRITE path
consumed by the W116 PBS post-mortem evaluator when it promotes a
finding. Score-based eviction of existing addenda happens AT READ
time (no expiry job needed for the 90 d horizon).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Pass3Addendum

log = structlog.get_logger(__name__)


# Defaults aligned with researcher SOTA brief (round-15) :
DEFAULT_MAX_ACTIVE_PER_REGIME = 3
DEFAULT_DECAY_HALFLIFE_DAYS = 30.0
DEFAULT_TTL_DAYS = 90.0


def _effective_score(
    importance: float,
    created_at: datetime,
    now: datetime,
    halflife_days: float,
) -> float:
    """`importance · 2^(-Δt/halflife)`. Returns a non-negative float."""
    if halflife_days <= 0.0:
        # Degenerate : no decay. Just return importance.
        return importance
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    return importance * math.pow(2.0, -age_days / halflife_days)


async def select_active_addenda(
    session: AsyncSession,
    *,
    regime: str,
    asset: str | None = None,
    max_active: int = DEFAULT_MAX_ACTIVE_PER_REGIME,
    halflife_days: float = DEFAULT_DECAY_HALFLIFE_DAYS,
    now: datetime | None = None,
) -> list[Pass3Addendum]:
    """Return the top-K active addenda for `regime` (and optionally
    `asset`), ranked by decayed importance score, hard-capped at
    `max_active`.

    `now` is injectable for tests. Defaults to `datetime.now(UTC)`.
    """
    if max_active < 0:
        raise ValueError(f"max_active must be ≥ 0, got {max_active!r}")
    if max_active == 0:
        return []

    now_ts = now if now is not None else datetime.now(UTC)

    stmt = (
        select(Pass3Addendum)
        .where(Pass3Addendum.regime == regime)
        .where(Pass3Addendum.status == "active")
        .where(Pass3Addendum.expires_at > now_ts)
    )
    if asset is not None:
        # Asset-specific addenda OR regime-wide (asset IS NULL).
        from sqlalchemy import or_

        stmt = stmt.where(or_(Pass3Addendum.asset == asset, Pass3Addendum.asset.is_(None)))
    # Pre-filter by raw importance so we don't load 1000+ rows when N
    # active is large. The decay re-rank below stays in-Python.
    stmt = stmt.order_by(Pass3Addendum.importance.desc()).limit(max(max_active * 4, 12))

    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return []

    # In-Python decay re-rank.
    scored = [
        (a, _effective_score(a.importance, a.created_at, now_ts, halflife_days)) for a in rows
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [a for a, _ in scored[:max_active]]


async def record_new_addendum(
    session: AsyncSession,
    *,
    regime: str,
    content: str,
    importance: float,
    asset: str | None = None,
    source_card_id: UUID | None = None,
    ttl_days: float = DEFAULT_TTL_DAYS,
    now: datetime | None = None,
) -> UUID:
    """Insert one new addendum with `status='active'` and TTL-derived
    `expires_at`. Returns the new row UUID.

    Caller is responsible for the W116 PBS evaluation that produced
    `importance` ; this helper does NOT re-score. Caller is also
    responsible for marking ancestors `superseded` via a separate
    UPDATE if needed.
    """
    if ttl_days <= 0.0:
        raise ValueError(f"ttl_days must be > 0, got {ttl_days!r}")
    if importance < 0.0:
        raise ValueError(f"importance must be ≥ 0, got {importance!r}")
    if not (8 <= len(content) <= 4096):
        raise ValueError(
            f"content length {len(content)} not in [8, 4096] "
            "(matches CHECK constraint ck_pass3_addenda_content_size)"
        )

    now_ts = now if now is not None else datetime.now(UTC)
    expires_at = now_ts + timedelta(days=ttl_days)

    result = await session.execute(
        insert(Pass3Addendum)
        .values(
            regime=regime,
            asset=asset,
            content=content,
            importance=importance,
            status="active",
            source_card_id=source_card_id,
            created_at=now_ts,
            expires_at=expires_at,
        )
        .returning(Pass3Addendum.id)
    )
    new_id = result.scalar_one()
    log.info(
        "pass3_addenda.recorded",
        id=str(new_id),
        regime=regime,
        asset=asset,
        importance=importance,
        ttl_days=ttl_days,
    )
    return new_id
