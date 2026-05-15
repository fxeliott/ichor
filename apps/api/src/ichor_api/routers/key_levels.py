"""GET /v1/key-levels — non-technical key levels per ADR-083 D3.

Exposes the 9 KeyLevel computers (TGA + HKMA + gamma_flip x2 + SKEW +
HY OAS + VIX + polymarket x3) as a JSON array following ADR-083 D3
canonical shape :

    [
      {
        "asset": "USD",
        "level": 838.584,
        "kind": "tga_liquidity_gate",
        "side": "above_liquidity_drain_below_inject",
        "source": "FRED:WTREGEN 2026-05-13",
        "note": "TGA $839B above $700B threshold..."
      },
      ...
    ]

This endpoint is the architectural bridge from r54-r58 backend
(KeyLevels consumed by Pass 2 LLM via data_pool markdown) toward the
ADR-083 D4 Living Analysis View frontend (rule 4 frontend gel decision
required from Eliot before /analysis route ships).

For now, the JSON output enables Eliot to inspect the exact data shape
via curl + decide whether to lift rule 4 for D4 frontend consumption.

Rule 4 honored : zero apps/web2 touch ; pure backend addition.
Voie D : pure-Python compute, ZERO LLM call, ZERO new feed.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.key_levels import (
    compute_call_wall_levels,
    compute_gamma_flip_levels,
    compute_hkma_peg_break,
    compute_hy_oas_percentile,
    compute_polymarket_decision_levels,
    compute_put_wall_levels,
    compute_skew_regime_switch,
    compute_tga_key_level,
    compute_vix_regime_switch,
)

router = APIRouter(prefix="/v1/key-levels", tags=["key-levels"])


class KeyLevelOut(BaseModel):
    """ADR-083 D3 canonical KeyLevel JSON shape."""

    asset: str
    level: float
    kind: Literal[
        "tga_liquidity_gate",
        "rrp_liquidity_gate",
        "gamma_flip",
        "gex_call_wall",
        "gex_put_wall",
        "peg_break_hkma",
        "peg_break_pboc_fix",
        "vix_regime_switch",
        "skew_regime_switch",
        "hy_oas_percentile",
        "polymarket_decision",
    ]
    side: str
    source: str
    note: str = ""


class KeyLevelsResponse(BaseModel):
    """Response envelope : `count` + `items` + `as_of` (server clock)."""

    count: int
    items: list[KeyLevelOut]


@router.get("", response_model=KeyLevelsResponse)
async def get_key_levels(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> KeyLevelsResponse:
    """Return all currently-firing KeyLevels across the 5 ADR-083 D3 phases.

    Order : TGA → HKMA → gamma_flip (per asset) → VIX → SKEW → HY OAS →
    polymarket_decision (top-N=3 by volume). Empty list if no level
    fires (all in NORMAL bands).
    """
    out: list[KeyLevelOut] = []

    # Phase 1 : TGA liquidity gate (returns KeyLevel | None)
    tga = await compute_tga_key_level(session)
    if tga is not None:
        out.append(KeyLevelOut(**tga.to_dict()))

    # Phase 2a : HKMA peg break
    hkma = await compute_hkma_peg_break(session)
    if hkma is not None:
        out.append(KeyLevelOut(**hkma.to_dict()))

    # Phase 3 : gamma_flip (batch returns list[KeyLevel])
    for kl in await compute_gamma_flip_levels(session):
        out.append(KeyLevelOut(**kl.to_dict()))

    # Phase 3-extension r60 : call_wall + put_wall (gex_snapshots extras)
    for kl in await compute_call_wall_levels(session):
        out.append(KeyLevelOut(**kl.to_dict()))
    for kl in await compute_put_wall_levels(session):
        out.append(KeyLevelOut(**kl.to_dict()))

    # Phase 4 : VIX + SKEW + HY OAS (each returns KeyLevel | None)
    for computer in (
        compute_vix_regime_switch,
        compute_skew_regime_switch,
        compute_hy_oas_percentile,
    ):
        kl = await computer(session)
        if kl is not None:
            out.append(KeyLevelOut(**kl.to_dict()))

    # Phase 5 : polymarket_decision (batch returns list[KeyLevel])
    for kl in await compute_polymarket_decision_levels(session):
        out.append(KeyLevelOut(**kl.to_dict()))

    return KeyLevelsResponse(count=len(out), items=out)
