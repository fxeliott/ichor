"""KeyLevel orchestration — single source of truth for the 9-call sequence.

Extracts the inline orchestration that previously lived in
`routers/key_levels.py:get_key_levels` so two consumers can share it :

1. **Real-time read endpoint** `/v1/key-levels` (router) — wraps the
   output in `KeyLevelOut` Pydantic objects + `KeyLevelsResponse`
   envelope for HTTP consumers.

2. **4-pass orchestrator finalization** (`cli/run_session_card.py`)
   — captures the snapshot as raw `list[dict[str, Any]]` and persists
   it into `session_card_audit.key_levels` JSONB column (migration
   0049, r62) so D4 frontend replay + Brier post-mortem can read the
   exact KeyLevel state at card generation time.

Output shape per ADR-083 D3 canonical (mirror of `KeyLevel.to_dict()`) :

    [
      {
        "asset": "USD",
        "level": 838.584,
        "kind": "tga_liquidity_gate",
        "side": "above_liquidity_drain_below_inject",
        "source": "FRED:WTREGEN 2026-05-13",
        "note": "TGA $839B above $700B threshold..."
      },
      ... 0-N entries depending on which bands are firing
    ]

Empty list `[]` is the canonical "all bands NORMAL" state.

Voie D respect : pure-Python compute, ZERO LLM call. Each computer
returns either `KeyLevel | None` or `list[KeyLevel]` from already-
collected upstream data ; this service stitches them together in
ADR-083 D3 phase order.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from . import (
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


async def compose_key_levels_snapshot(session: AsyncSession) -> list[dict[str, Any]]:
    """Orchestrate the 9 KeyLevel computers + return the snapshot.

    Returns a flat list of `KeyLevel.to_dict()` outputs in ADR-083 D3
    phase order :

    1. Phase 1   — TGA liquidity gate
    2. Phase 2a  — HKMA peg break
    3. Phase 3   — gamma_flip (per asset, batch)
    4. Phase 3-ext (r60) — call_wall + put_wall (gex_snapshots extras)
    5. Phase 4   — VIX + SKEW + HY OAS regime switches
    6. Phase 5   — polymarket_decision (top-N by volume, batch)

    Empty list `[]` if no level fires (all bands NORMAL).

    The output is directly JSONB-serializable — used both by the
    /v1/key-levels HTTP endpoint (wrapped in Pydantic) and by the
    4-pass orchestrator persistence path (raw dict for JSONB column).
    """
    out: list[dict[str, Any]] = []

    # Phase 1 : TGA liquidity gate (returns KeyLevel | None)
    tga = await compute_tga_key_level(session)
    if tga is not None:
        out.append(tga.to_dict())

    # Phase 2a : HKMA peg break
    hkma = await compute_hkma_peg_break(session)
    if hkma is not None:
        out.append(hkma.to_dict())

    # Phase 3 : gamma_flip (batch returns list[KeyLevel])
    for kl in await compute_gamma_flip_levels(session):
        out.append(kl.to_dict())

    # Phase 3-extension r60 : call_wall + put_wall (gex_snapshots extras)
    for kl in await compute_call_wall_levels(session):
        out.append(kl.to_dict())
    for kl in await compute_put_wall_levels(session):
        out.append(kl.to_dict())

    # Phase 4 : VIX + SKEW + HY OAS (each returns KeyLevel | None)
    for computer in (
        compute_vix_regime_switch,
        compute_skew_regime_switch,
        compute_hy_oas_percentile,
    ):
        kl = await computer(session)
        if kl is not None:
            out.append(kl.to_dict())

    # Phase 5 : polymarket_decision (batch returns list[KeyLevel])
    for kl in await compute_polymarket_decision_levels(session):
        out.append(kl.to_dict())

    return out
