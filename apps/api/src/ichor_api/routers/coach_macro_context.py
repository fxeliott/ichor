"""``GET /v1/coach-macro-context`` — Ichor Stride 8 Phase 2 narrative-synthesis
surface per ADR-106 §Impl(r161) + Eliot's r161 directive verbatim ("coach de
compréhension", "guide lumineux qui rend chaque élément limpide").

Returns the canonical ``CoachMacroContext`` aggregating the 4-cycle
business-cycle classification + dominant macro theme + 3 next upcoming
surprises + FR coach paragraph. Built deterministically by
``services/coach_macro_context_builder.build_coach_macro_context()`` from
FRED observations + EconomicEvent rows (no LLM call ; Voie D-clean).

**Surface contract** :

  - 200 OK + ``CoachMacroContext`` JSON — the builder always returns a
    fully-populated object even when classifiers are inconclusive
    (cycle="uncertain" / dominant_theme=None / top_next_surprises=[] are
    LEGITIMATE doctrine #11 calibrated-honesty outputs ; the panel
    surfaces them transparently rather than hiding the absence).
  - 500 only on internal DB error (caller — typically the Server
    Component fetcher — falls back to null per ``apiGet`` contract).

**Asset-agnostic by design** : the macro narrative is the SAME across the
5-asset priority universe (EUR_USD / GBP_USD / XAU_USD / SPX500_USD /
NAS100_USD). Per-asset reads (verdict / event-anticipation / etc.) live
on dedicated `/v1/verdict/session-ny/{asset}` + `/v1/event-anticipation/
{asset}` endpoints. The coach surface precedes them in the briefing
hierarchy because the macro story frames the per-asset interpretation.

**Caching policy** : ``Cache-Control: private, no-store`` — the macro
narrative is LIVE state (data freshness exposed via ``data_freshness_
days``), never cache at intermediate proxy. The frontend SSRs the
briefing page on every visit ; future r162+ Stride 7 will upgrade to
WebSocket/SSE push for cross-tab synchronisation.

**ADR-079 §50.2 watermark middleware** : the route prefix
``/v1/coach-macro-context`` is added to ``AIWatermarkMiddleware``'s
tagged prefix tuple AND ``Settings.ai_watermarked_route_prefixes`` in
lockstep (W90 invariant ``test_ai_watermark_default_prefixes_match_
settings``). All responses carry ``X-Ichor-AI-Generated: true``
headers because the coach_paragraph synthesis IS LLM-domain narrative
(probabilistic-research-output requiring AI disclosure per EU AI Act
§50.2 deadline 2026-08-02).

ADR refs : ADR-106 §"coach explicateur" + 7-stride roadmap (this is
Stride 8 Phase 2) ; ADR-079 (watermark middleware) ; ADR-017
(boundary preserved via ``CoachMacroContext`` Pydantic validators on
``coach_paragraph`` + ``CalendarSurprise.why_it_matters``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from ichor_brain.coach_macro_context import CoachMacroContext
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.coach_macro_context_builder import build_coach_macro_context

router = APIRouter(prefix="/v1/coach-macro-context", tags=["coach-macro-context"])


@router.get(
    "",
    response_model=CoachMacroContext,
    summary="Coach macro narrative — cycle + dominant theme + 3 next surprises + FR paragraph",
)
async def get_coach_macro_context(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CoachMacroContext:
    """Return the canonical asset-agnostic ``CoachMacroContext``.

    The builder always returns a fully-populated object — when the
    growth × inflation 2×2 classifier is ambiguous OR FRED data is past
    ``MAX_FRESHNESS_DAYS = 45``, the response carries
    ``cycle="uncertain"`` + ``cycle_confidence_pct=0`` and the
    ``coach_paragraph`` explains the situation transparently (doctrine
    #11 calibrated honesty). The frontend renders these states with
    explicit honest-uncertainty chrome rather than hiding the panel.
    """
    context = await build_coach_macro_context(session)
    # LIVE state — never cache at intermediate proxy. Mirror of
    # ``routers/verdict.py:126`` + ``routers/key_levels`` discipline.
    response.headers["Cache-Control"] = "private, no-store"
    return context
