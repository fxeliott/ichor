"""Chantier-C DimensionVote **write-side** builders (C-3b COT + C-3 volume).

Extracted VERBATIM from ``data_pool.py`` (pure structural move, zero behavior
change) to shrink the god-file. The 4 functions only call each other ; their
external callers (``cli/run_session_card.py`` + the C-3 wiring tests) import
them through the back-compat re-export in ``data_pool`` (see its ``__all__``),
so this move is byte-identical at every public import path.

The 3 shared constants (``_COT_MARKET_BY_ASSET``, ``_VOLUME_ASSETS``,
``_VOLUME_RVOL_MAX_AGE_DAYS``) STAY in ``data_pool`` because ``_section_*``
read-side blocks there also read them. We import them back **lazily, inside the
functions that use them** (mirroring the lazy ``cot_vote`` / ``volume_vote``
imports below) so this module carries NO module-level edge back to ``data_pool``.
It is therefore import-safe from ANY entry point — not only when ``data_pool`` is
imported first (a module-level back-import would deadlock a standalone
``import dimension_vote_builders``; this keeps the re-export the single direction).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CftcTffObservation, CotPosition
from .data_liveness import classify_liveness
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
    from .data_pool import _COT_MARKET_BY_ASSET

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
    from .data_pool import _VOLUME_RVOL_MAX_AGE_DAYS
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
    from .data_pool import _VOLUME_ASSETS
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


async def build_geopolitics_vote_for_asset(
    session: AsyncSession, asset: str, *, now_utc: datetime
) -> DimensionVote:
    """Geopolitics write-side — read the AI-GPR trailing-30d z-score (the SAME flash the
    ``GEOPOL_FLASH`` alert computes and ``_section_geopolitics`` liveness-gates) and map it
    to ONE **non-directional** Chantier-C ``DimensionVote`` via the pure
    ``geopolitics_vote.build_geopolitics_vote``.

    AI-GPR is a single GLOBAL scalar (``data_pool.py:5017``), so ``asset`` does not change
    the value — the same anti-uncertainty credit attaches to every asset. The parameter is
    kept for a uniform per-asset call contract (the write-side loops per asset, exactly like
    the COT / volume builders) so the capture block stays a flat list of
    ``build_*_vote_for_asset`` calls.

    Pure persistence of an already-computable structure (Voie D) : ``persist=False`` so this
    read NEVER fires the alert (that is the alert CLI's job) — no LLM, no new feed. An empty
    table, a not-yet-warm window (< 20 obs), a stale source, or any read error all resolve to
    an honest-absence vote (contributes EXACTLY 0 to the fuser — ADR-103) ; the caller wraps
    this best-effort so card generation never fails on a geopolitics read.
    """
    from .geopol_flash_check import evaluate_geopol_flash
    from .geopolitics_vote import GPR_MAX_AGE_DAYS, build_geopolitics_vote

    now_date = now_utc.astimezone(UTC).date()
    # persist=False: a pure read for the vote, never a write/alert side-effect.
    flash = await evaluate_geopol_flash(session, persist=False)
    live = classify_liveness(
        "AI-GPR",
        flash.current_date,
        now=now_date,
        max_age_days=GPR_MAX_AGE_DAYS,
        impacted="geopolitics",
    )
    return build_geopolitics_vote(
        status=live.status,
        z_score=flash.z_score,
        age_days=live.age_days,
        max_age_days=GPR_MAX_AGE_DAYS,
    )


def _tff_vote_from_rows(
    asset: str,
    market: str,
    rows: Sequence[CftcTffObservation],
    *,
    now_date: date,
) -> DimensionVote:
    """Pure mapper : recent ``CftcTffObservation`` rows (newest-first) → one Chantier-C
    ``DimensionVote`` (positioning_tff). Split out of the async fetch so the row→vote logic
    is unit-testable WITHOUT a DB.

    Liveness is recomputed from the freshest ``report_date`` exactly as
    ``_section_tff_positioning`` does, so the vote's ``status``/``age_days`` match the TFF
    band the LLM saw. The heavy lifting (band-aligned Δ4w/Δ1w, OI normalisation, SPX500-only
    polarity, fail-closed gates) lives in the pure ``positioning_tff_vote.build_positioning_tff_vote``
    — this only adapts the ORM rows (LevFunds net = lev_money_long − lev_money_short)."""
    from .positioning_tff_vote import TFF_MAX_AGE_DAYS, build_positioning_tff_vote

    latest_date = rows[0].report_date if rows else None
    live = classify_liveness(
        f"CFTC:TFF:{market}",
        latest_date,
        now=now_date,
        max_age_days=TFF_MAX_AGE_DAYS,
        impacted=f"tff:{asset}",
    )
    history = [(r.report_date, r.lev_money_long - r.lev_money_short) for r in rows]
    open_interest = rows[0].open_interest if rows else None
    return build_positioning_tff_vote(
        asset=asset,
        status=live.status,
        history=history,
        open_interest=open_interest,
        age_days=live.age_days,
        max_age_days=TFF_MAX_AGE_DAYS,
    )


async def build_positioning_tff_vote_for_asset(
    session: AsyncSession, asset: str, *, now_utc: datetime
) -> DimensionVote:
    """positioning_tff write-side — fetch the recent CFTC-TFF rows for ``asset`` (the SAME
    market ``_section_tff_positioning`` feeds the LLM with) and map LevFunds net positioning
    to ONE Chantier-C ``DimensionVote`` via the pure ``positioning_tff_vote``.

    Only ``SPX500_USD`` gets a directional vote (the asset COT does not cover) — every other
    asset abstains WITHOUT a DB read, since a directional TFF read on EUR/GBP/XAU/NAS would
    double-count ``cot_vote`` on the identical CFTC market codes (the producer abstains there
    anyway; this skips the useless query).

    Pure persistence of an already-computable structure (Voie D) : no LLM, no new feed. An
    asset off the SPX500-only map, an empty / stale table, or any read error all resolve to an
    honest-absence vote (contributes EXACTLY 0 — ADR-103) ; the caller wraps this best-effort
    so card generation never fails on a TFF read.
    """
    from .data_pool import _TFF_MARKET_BY_ASSET
    from .positioning_tff_vote import TFF_MAX_AGE_DAYS, build_positioning_tff_vote

    now_date = now_utc.astimezone(UTC).date()
    market = _TFF_MARKET_BY_ASSET.get(asset)
    # SPX500-only directional edge (COT covers the rest) → cheap DB-free abstain otherwise.
    if asset != "SPX500_USD" or market is None:
        return build_positioning_tff_vote(
            asset=asset,
            status="absent",
            history=(),
            open_interest=None,
            age_days=None,
            max_age_days=TFF_MAX_AGE_DAYS,
        )
    stmt = (
        select(CftcTffObservation)
        .where(CftcTffObservation.market_code == market)
        .order_by(desc(CftcTffObservation.report_date))
        .limit(13)  # ~3 months of weekly reports — enough for the Δ4w trend band
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return _tff_vote_from_rows(asset, market, rows, now_date=now_date)
