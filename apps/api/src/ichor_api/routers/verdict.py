"""``GET /v1/verdict/session-ny/{asset}`` — Ichor canonical session verdict
endpoint per ADR-106 D5.

Returns the latest ``SessionVerdict`` for the given priority-5 asset's
current-day NY session (13h00-20h00 Paris window). Pure read endpoint —
the verdict is built deterministically by
``services/session_verdict_builder.py`` from the latest
``session_card_audit`` row (no LLM call, no external dep, Voie D-clean).

**Surface contract per ADR-106 D5** :

  - 200 OK + ``SessionVerdict`` JSON when a session_card_audit row exists
    for today's Paris-date (whether or not Pass-6 scenarios are populated
    — the builder handles the fallback path with
    ``derived_from_scenarios=False``)
  - 404 Not Found when no session_card_audit row exists yet today
    (caller — typically the frontend — renders an honest "verdict en
    attente, session non encore amorcée" state)
  - 200 OK + ``SessionVerdict`` JSON ALSO when the verdict has expired
    (``now_utc > expires_at_utc``, past the ~20h15 Paris cutoff). Expiry is
    a normal lifecycle state, not an error : the verdict body is returned so
    the frontend can render a clean "session terminée" state from
    ``expires_at_utc`` (its ``isVerdictExpired`` helper) instead of the panel
    vanishing + the client poll logging a browser-console 410 every minute.
    (Pre-2026-06-03 this returned 410 Gone with no body — superseded.)
  - 422 Unprocessable Entity when the ``asset`` path param doesn't match
    the canonical pattern (handled by FastAPI ``Path`` constraint)
  - 500 only on internal DB error (caller retries with exponential backoff)

**Caching policy** : ``Cache-Control: private, no-store`` — the verdict
is LIVE state, never cache at intermediate proxy. The frontend polls
this endpoint every 30s while the briefing page is visible (Page
Visibility API pause/resume, mirror of ``<FreshDataBanner>`` r140
pattern). Future r162+ Stride 7 will upgrade to WebSocket/SSE push.

**ADR-079 §50.2 watermark middleware** : the route prefix
``/v1/verdict`` is added to ``AIWatermarkMiddleware``'s tagged
prefix tuple (see ``main.py`` mount + the middleware Settings
field). All responses carry ``X-Ichor-AI-Generated: true`` headers
because the verdict is LLM-derived (via Pass-6 scenarios) even when
the fallback path returns ``derived_from_scenarios=False`` (the
fallback is itself a probabilistic-research-output, not raw data).

ADR refs : ADR-106 §D5 (this endpoint contract), §D2 (builder
algorithm), §D6 (doctrine alignment) ; ADR-079 (watermark middleware) ;
ADR-017 (boundary preserved via SessionVerdict Pydantic validators).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.session_verdict import SessionVerdict
from ..services.session_verdict_builder import build_session_verdict

router = APIRouter(prefix="/v1/verdict", tags=["verdict"])


@router.get(
    "/session-ny/{asset}",
    response_model=SessionVerdict,
    responses={
        404: {"description": "No session_card_audit row for today yet"},
        422: {"description": "Asset path param malformed"},
    },
)
async def get_session_verdict(
    asset: Annotated[
        str,
        Path(
            # Mirror of ``routers/event_anticipation.py:96`` r152 CRIT-1 fix
            # pattern : index-style codes (NAS100_USD, SPX500_USD) carry
            # digits in the prefix, so ``[A-Z0-9]{3,8}`` is required. The
            # actual whitelist enforcement (priority-5 frontend universe :
            # EUR_USD, GBP_USD, XAU_USD, SPX500_USD, NAS100_USD) is layered
            # on top by the ``SessionVerdict.asset`` Pydantic ``Literal``
            # validator — a non-priority asset path will pass the regex
            # but trigger a 422 at Pydantic construction time inside the
            # builder.
            pattern=r"^[A-Z0-9]{3,8}_[A-Z]{3,8}$|^[A-Z0-9]{3,8}$",
            description="Priority-5 asset code : EUR_USD / GBP_USD / XAU_USD / SPX500_USD / NAS100_USD",
        ),
    ],
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionVerdict:
    """Return today's NY-session verdict for the given priority-5 asset.

    Builds the verdict deterministically from the latest
    ``session_card_audit`` row in the (asset, today's Paris-date)
    window. Handles the fallback path gracefully when Pass-6 is
    dormant (returns ``derived_from_scenarios=False`` + downgraded
    conviction per ADR-106 D1).
    """
    now_utc = datetime.now(UTC)
    verdict = await build_session_verdict(session, asset=asset, now_utc=now_utc)

    if verdict is None:
        # No session_card_audit row for today's Paris-midnight onwards.
        # Render-side state : "verdict en attente, session non encore
        # amorcée" — the frontend interpret as 404-class soft-empty.
        raise HTTPException(
            status_code=404,
            detail=(
                f"No session_card_audit row for asset={asset} today "
                f"(Paris-midnight onwards). Pre-session briefing has "
                f"not yet been emitted ; first emission fires at the "
                f"pre-Londres timer (~07h00 Paris)."
            ),
        )

    # Expired (now_utc > expires_at_utc, NY-session window closed past
    # ~20h15 Paris) is a NORMAL lifecycle state, NOT an error. Pre-2026-06-03
    # this raised 410 Gone with no body, which (a) made the client poll log a
    # browser-console "Failed to load resource: 410" every minute and (b) left
    # the frontend's own `isVerdictExpired()` / "session terminée" rendering as
    # dead code (the expired verdict body never reached it). We now return the
    # verdict with 200 and let the frontend present a clean "session terminée"
    # state from `expires_at_utc` — zero console noise, honest disclosure.
    # `Cache-Control: private, no-store` regardless (LIVE state, never cached
    # at an intermediate proxy ; an expired verdict can become a fresh one on
    # the next briefing emission within the same browser session).
    response.headers["Cache-Control"] = "private, no-store"
    return verdict
