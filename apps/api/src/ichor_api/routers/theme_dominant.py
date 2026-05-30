"""``GET /v1/theme-dominant`` — r185 frontend endpoint exposing the
r182 N1 EXECUTION-phase theme sous-jacent classifier.

Per ROADMAP §3 r184-close binding-default : extend r181/r182/r183 backend
arc to the frontend visibility wave. Pass-2 consumer wiring r183 was
the backend-side ; this endpoint is the read-side that the frontend
``<ThemeRankingPanel>`` (r186+) will poll every 60s while the briefing
page is visible (Page Visibility API pause/resume, mirror
``<FreshDataBanner>`` r140 + ``<DxyCorrelationPanel>`` r171b +
``<PreviousSessionContextPanel>`` r186 pattern).

Asset-agnostic by construction : the theme dominant the GLOBAL market
(via Pass-1 régime + NFCI + VIX + DXY + 10Y + economic_events +
ai_gpr + GDELT), not the per-asset context. One endpoint serves all
5 priority assets — the frontend can show « le marché est driven by
geopolitics aujourd'hui » as a top-banner pane on every /briefing/X.

**Surface contract** :

- 200 OK + ``ThemeDominantOut`` JSON when ``classify_dominant_theme()``
  returns a valid ranking (top_theme strength >= 0.5)
- 404 Not Found when classifier returns None (no driver dominates
  clearly — honest absence per doctrine #11) ; caller renders an
  honest « aucun thème dominant aujourd'hui » state
- 500 only on internal DB error (caller retries with exponential backoff)

**Caching policy** : ``Cache-Control: private, no-store`` — the
ranking is LIVE state derived from rolling FRED/economic_events/
ai_gpr queries. Frontend polls every 60-120s ; server reads from
indexed PKs in O(log n).

**ADR-079 watermark** : the route prefix ``/v1/theme-dominant`` does
NOT need to be added to ``AIWatermarkMiddleware`` tagged prefixes
because the response is PURE FACTUAL DATA derived from raw data
inputs (no LLM emission). Pure data routes explicitly excluded
from the watermark per ADR-079.

**ADR-017 boundary** : ThemeDominantOut.top_theme is a Literal of
the 8 canonical drivers — these are descriptive labels for the
current macro REGIME driver, NEVER directional bias for any asset.
The Pydantic class is verifier-friendly (frozen + extra=forbid).

ADR refs : ADR-099 §Impl(r185) (this endpoint) ; ADR-017 (boundary) ;
ADR-079 (watermark exclusion rationale) ; r182 EXECUTION-phase
classifier (compute backbone).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.theme_classifier import (
    THEME_DRIVERS,
    ThemeDriverKey,
    ThemeRanking,
    classify_dominant_theme,
)

router = APIRouter(prefix="/v1/theme-dominant", tags=["theme_dominant"])


class ThemeDominantOut(BaseModel):
    """JSON-friendly read-only projection of ``ThemeRanking``.

    Mirror of the r181 FOUNDATION + r182 EXECUTION Pydantic frozen
    class. Inherits ``frozen=True`` + ``extra='forbid'`` discipline.

    Why a separate Pydantic vs returning ThemeRanking directly :
    backwards-compat for r186+ frontend lockstep CI guard (if a future
    round adds internal fields to ThemeRanking, the frontend surface
    contract stays stable). Also enables pre-computed convenience
    fields (top_theme_strength_pct as percentage int for UI render
    without extra client-side math).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    top_theme: ThemeDriverKey
    """Dominant driver. UI banner renders « Thème dominant aujourd'hui :
    {top_theme_fr} » using a frontend FR copy map (mirror
    sessionVerdict pattern)."""

    top_theme_strength_pct: int = Field(ge=0, le=100)
    """``top_theme`` strength as percentage int (0-100) for clean UI
    rendering. Pre-computed by ``_project_ranking()`` from
    ``ThemeRanking.driver_strengths[top_theme]`` × 100, rounded."""

    secondary_themes: list[ThemeDriverKey] = Field(default_factory=list, max_length=3)
    """Up to 3 secondary drivers contributing materially. Frontend
    renders as smaller pills below the dominant banner."""

    driver_strengths_pct: dict[ThemeDriverKey, int] = Field(default_factory=dict)
    """All 8 driver strengths as percentage int (0-100). Frontend
    can render a horizontal bar chart of all 8 if it wants a full
    breakdown view ; minimal UI just reads top_theme +
    secondary_themes."""

    computed_at_utc: datetime
    """Wall-clock UTC of the ranking computation. Frontend renders
    « calculé il y a N min » from this field for freshness disclosure."""

    provenance: Literal["practitioner_stamp"] = "practitioner_stamp"
    """Honest stamp per Pattern #20 mechanical R59-pre-commit-mandatory.
    The 8-driver taxonomy itself is practitioner-stamp (Eliot Fathom
    transcript page 1 étape 1), NOT peer-reviewed academic concept.
    Individual driver-strength rules cite peer-reviewed backbone
    (Bekaert-Hoerova-Lo Duca 2013 JME for VIX>30 funding-stress,
    Caldara-Iacoviello 2022 AER for GPR construction, Nakamura-
    Steinsson 2018 QJE for FOMC HFI discipline) — but the *aggregate*
    ranking is practitioner."""


def _project_ranking(ranking: ThemeRanking) -> ThemeDominantOut:
    """Pure : project internal ``ThemeRanking`` Pydantic to JSON-
    friendly ``ThemeDominantOut``. Pre-computes percentage-int fields
    for frontend convenience.

    Ensures full 8-driver percentage dict via THEME_DRIVERS tuple
    iteration — even drivers at baseline 0.2 get their slot. This
    keeps the frontend rendering predictable (8 bars, never missing
    keys).
    """
    strengths_pct = {
        driver: round(ranking.driver_strengths.get(driver, 0.0) * 100) for driver in THEME_DRIVERS
    }
    return ThemeDominantOut(
        top_theme=ranking.top_theme,
        top_theme_strength_pct=strengths_pct[ranking.top_theme],
        secondary_themes=list(ranking.secondary_themes),
        driver_strengths_pct=strengths_pct,
        computed_at_utc=ranking.computed_at_utc,
    )


@router.get(
    "",
    response_model=ThemeDominantOut,
    responses={
        404: {"description": "No driver dominates clearly (honest absence)"},
    },
)
async def get_theme_dominant(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ThemeDominantOut:
    """Return the current dominant theme sous-jacent driving the
    market (per Eliot Fathom transcript étape 1 methodology).

    Asset-agnostic : returns ONE ranking that applies to the global
    macro regime, consumed by every /briefing/X frontend as a
    top-banner contextual pane. Doctrine #11 calibrated honesty :
    when no driver meets the 0.5 dominance threshold, returns 404
    rather than fabricating a forced ranking.
    """
    now_utc = datetime.now(UTC)
    ranking = await classify_dominant_theme(session, now_utc=now_utc)

    if ranking is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No theme dominates the current market regime : "
                "all driver strengths below the 0.5 dominance threshold. "
                "Honest absence per doctrine #11 — the classifier "
                "refuses to fabricate a forced ranking when inputs "
                "are mixed/insufficient."
            ),
        )

    response.headers["Cache-Control"] = "private, no-store"
    return _project_ranking(ranking)
