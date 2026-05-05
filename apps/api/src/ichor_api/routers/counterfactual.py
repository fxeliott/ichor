"""POST /v1/sessions/{id}/counterfactual — on-demand Pass 5.

Body : {"scrubbed_event": "<short text>"}
Returns the CounterfactualReading produced by Claude through the
existing claude-runner Voie D pipeline, plus the original card's
generated_at + critic_verdict for context.

VISION_2026 delta I — Pass 5 wiring.

Side-effects : NONE in V1. Counterfactuals are exploratory ; we
don't persist them yet. Phase 2 will add a sibling table
`session_card_counterfactuals(session_card_id, asked_at, scrubbed_event,
result_json)` if Eliot uses the feature regularly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import SessionCardAudit

router = APIRouter(prefix="/v1/sessions", tags=["counterfactual"])


class CounterfactualRequest(BaseModel):
    scrubbed_event: str = Field(min_length=1, max_length=500)


class CounterfactualResponse(BaseModel):
    session_card_id: str
    asset: str
    original_generated_at: datetime
    original_bias: str
    original_conviction_pct: float
    asked_at: datetime
    scrubbed_event: str
    counterfactual_bias: str
    counterfactual_conviction_pct: float
    delta_narrative: str
    new_dominant_drivers: list[str]
    confidence_delta: float


@router.post("/{card_id}/counterfactual", response_model=CounterfactualResponse)
async def run_counterfactual(
    card_id: str,
    body: CounterfactualRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CounterfactualResponse:
    """Trigger Pass 5 on a stored session card."""
    try:
        card_uuid = UUID(card_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid card_id : {e}",
        )

    # Latest version of the card (composite PK includes generated_at,
    # so we sort desc and take 1).
    stmt = (
        select(SessionCardAudit)
        .where(SessionCardAudit.id == card_uuid)
        .order_by(desc(SessionCardAudit.generated_at))
        .limit(1)
    )
    card = (await session.execute(stmt)).scalars().first()
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session card {card_id} not found",
        )

    settings = get_settings()
    if not settings.claude_runner_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="claude-runner URL not configured",
        )

    # Lazy imports — keep ichor_brain optional in test envs.
    try:
        from ichor_brain.passes.counterfactual import CounterfactualPass
        from ichor_brain.runner_client import HttpRunnerClient, RunnerCall
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ichor_brain not installed : {e}",
        )

    # Reconstruct a JSON-friendly view of the original card for the
    # counterfactual prompt. We don't dump claude_raw_response (it can
    # be huge) — only the structured fields the LLM needs.
    original_view = {
        "asset": card.asset,
        "session_type": card.session_type,
        "regime_quadrant": card.regime_quadrant,
        "bias_direction": card.bias_direction,
        "conviction_pct": card.conviction_pct,
        "magnitude_pips_low": card.magnitude_pips_low,
        "magnitude_pips_high": card.magnitude_pips_high,
        "mechanisms": card.mechanisms,
        "catalysts": card.catalysts,
        "invalidations": card.invalidations,
        "critic_verdict": card.critic_verdict,
    }
    import json as _json

    pass5 = CounterfactualPass()
    runner = HttpRunnerClient(
        base_url=settings.claude_runner_url,
        cf_access_client_id=settings.cf_access_client_id,
        cf_access_client_secret=settings.cf_access_client_secret,
    )
    prompt = pass5.build_prompt(
        original_card_json=_json.dumps(original_view, default=str),
        data_pool=(
            "(Original data pool not stored — Pass 5 reasons over the "
            "card's mechanisms + catalysts + critic verdict directly.)"
        ),
        scrubbed_event=body.scrubbed_event,
    )
    rcall = RunnerCall(prompt=prompt, system=pass5.system_prompt, model="haiku", effort="low")
    rresp = await runner.run(rcall)
    parsed = pass5.parse(rresp.text)

    return CounterfactualResponse(
        session_card_id=str(card.id),
        asset=card.asset,
        original_generated_at=card.generated_at,
        original_bias=card.bias_direction,
        original_conviction_pct=card.conviction_pct,
        asked_at=datetime.now(UTC),
        scrubbed_event=body.scrubbed_event,
        counterfactual_bias=parsed.counterfactual_bias,
        counterfactual_conviction_pct=parsed.counterfactual_conviction_pct,
        delta_narrative=parsed.delta_narrative,
        new_dominant_drivers=list(parsed.new_dominant_drivers),
        confidence_delta=parsed.confidence_delta,
    )
