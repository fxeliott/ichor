"""Chantier-C DimensionVote **write-side** builders (C-3b COT + C-3 volume).

Extracted VERBATIM from ``data_pool.py`` (pure structural move, zero behavior
change) to shrink the god-file. The 4 functions only call each other ; their
external callers (``cli/run_session_card.py`` + the C-3 wiring tests) import
them through the back-compat re-export in ``data_pool`` (see its ``__all__``),
so this move is byte-identical at every public import path.

The 3 shared constants (``_COT_MARKET_BY_ASSET``, ``_VOLUME_ASSETS``,
``_VOLUME_RVOL_MAX_AGE_DAYS``) STAY in ``data_pool`` because ``_section_*``
read-side blocks there also read them ; we import them back here. That makes a
one-way pair (this module ← data_pool for constants ; data_pool ← this module
for the re-export) — the re-export line in data_pool sits AFTER the constants
are defined, so no partial-init cycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CotPosition
from .data_liveness import classify_liveness
from .data_pool import (
    _COT_MARKET_BY_ASSET,
    _VOLUME_ASSETS,
    _VOLUME_RVOL_MAX_AGE_DAYS,
)
from .dimension_vote import DimensionVote
from .microstructure import RelativeVolumeReading, assess_relative_volume


def _cot_vote_from_rows(
    asset: str,
    market: str,
    rows: Sequence[CotPosition],
    *,
    now_date: date,
) -> DimensionVote:
    """Pure mapper : recent ``CotPosition`` rows (newest-first) → one
    Chantier-C ``DimensionVote`` (C-3b). Split out of the async fetch so the
    row→vote logic is unit-testable WITHOUT a DB (the suite stubs DB 503).

    Liveness is recomputed from the freshest ``report_date`` exactly as
    ``_section_cot`` does, so the vote's ``status``/``age_days`` match the COT
    band the LLM saw. The heavy lifting (band-aligned Δ4w/Δ1w, OI normalisation,
    per-asset polarity, fail-closed gates) lives in the pure
    ``cot_vote.build_cot_vote`` — this only adapts the ORM rows to its contract.
    """
    from .cot_vote import COT_MAX_AGE_DAYS, build_cot_vote

    latest_date = rows[0].report_date if rows else None
    live = classify_liveness(
        f"CFTC:COT:{market}",
        latest_date,
        now=now_date,
        max_age_days=COT_MAX_AGE_DAYS,
        impacted=f"cot:{asset}",
    )
    history = [(r.report_date, r.managed_money_net) for r in rows]
    open_interest = rows[0].open_interest if rows else None
    return build_cot_vote(
        asset=asset,
        status=live.status,
        history=history,
        open_interest=open_interest,
        age_days=live.age_days,
        max_age_days=COT_MAX_AGE_DAYS,
    )


async def build_cot_vote_for_asset(
    session: AsyncSession, asset: str, *, now_utc: datetime
) -> DimensionVote:
    """C-3b write-side — fetch the recent COT rows for ``asset`` (the SAME query
    ``_section_cot`` feeds the LLM prompt with) and map them to ONE Chantier-C
    ``DimensionVote`` via the pure ``cot_vote.build_cot_vote``.

    Pure persistence of an already-computable structure (Voie D) : no LLM, no new
    feed. An asset outside the COT whitelist, an empty / stale table, or any
    read error all resolve to an honest-absence vote (contributes EXACTLY 0 to
    the fuser — ADR-103) ; the caller wraps this best-effort so card generation
    never fails on a COT read.
    """
    from .cot_vote import COT_MAX_AGE_DAYS, build_cot_vote

    now_date = now_utc.astimezone(UTC).date()
    market = _COT_MARKET_BY_ASSET.get(asset)
    if market is None:
        # Outside the COT whitelist → no source expected → abstain (status gate).
        return build_cot_vote(
            asset=asset,
            status="absent",
            history=(),
            open_interest=None,
            age_days=None,
            max_age_days=COT_MAX_AGE_DAYS,
        )
    stmt = (
        select(CotPosition)
        .where(CotPosition.market_code == market)
        .order_by(desc(CotPosition.report_date))
        .limit(13)  # mirror _section_cot — same rows the LLM prompt saw
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return _cot_vote_from_rows(asset, market, rows, now_date=now_date)


def _volume_vote_from_reading(
    asset: str,
    reading: RelativeVolumeReading,
    *,
    now_date: date,
) -> DimensionVote:
    """Pure mapper : a ``RelativeVolumeReading`` (the SAME read ``_section_volume_rvol``
    feeds the LLM with) → one Chantier-C **non-directional** ``DimensionVote`` (C-3
    volume). Split out of the async fetch so the read→vote logic is unit-testable
    WITHOUT a DB (the suite stubs DB 503).

    Liveness is recomputed from ``reading.latest_date`` exactly as
    ``_section_volume_rvol`` does, so the vote's ``status``/``age_days`` match the
    volume band the LLM saw. The heavy lifting (above-baseline magnitude, freshness
    decay, fail-closed gates, non-directional contract — volume confirms
    participation, never direction) lives in the pure ``volume_vote.build_volume_vote``
    — this only adapts the reading to its contract.
    """
    from .volume_vote import VOLUME_MAX_AGE_DAYS, build_volume_vote

    live = classify_liveness(
        f"market_data:{asset}:volume",
        reading.latest_date,
        now=now_date,
        max_age_days=_VOLUME_RVOL_MAX_AGE_DAYS,
        impacted=f"volume_rvol:{asset}",
    )
    return build_volume_vote(
        asset=asset,
        status=live.status,
        volume_available=reading.volume_available,
        rvol_ratio=reading.rvol_ratio,
        age_days=live.age_days,
        volume_zscore=reading.volume_zscore,
        max_age_days=VOLUME_MAX_AGE_DAYS,
    )


async def build_volume_vote_for_asset(
    session: AsyncSession, asset: str, *, now_utc: datetime
) -> DimensionVote:
    """C-3 volume write-side — read the relative-volume participation for ``asset``
    (the SAME read ``_section_volume_rvol`` feeds the LLM prompt with) and map it to
    ONE **non-directional** Chantier-C ``DimensionVote`` via the pure
    ``volume_vote.build_volume_vote``.

    Pure persistence of an already-computable structure (Voie D) : no LLM, no new
    feed. An asset with no consolidated venue volume (FX), an empty / stale daily
    series, or any read error all resolve to an honest-absence vote (contributes
    EXACTLY 0 to the fuser — ADR-103) ; the caller wraps this best-effort so card
    generation never fails on a volume read.
    """
    from .volume_vote import VOLUME_MAX_AGE_DAYS, build_volume_vote

    now_date = now_utc.astimezone(UTC).date()
    if asset not in _VOLUME_ASSETS:
        # FX / no consolidated venue volume → abstain (no DB I/O), mirror the
        # honest-N/A path of _section_volume_rvol.
        return build_volume_vote(
            asset=asset,
            status="absent",
            volume_available=False,
            rvol_ratio=None,
            age_days=None,
            max_age_days=VOLUME_MAX_AGE_DAYS,
        )
    reading = await assess_relative_volume(session, asset)
    return _volume_vote_from_reading(asset, reading, now_date=now_date)
