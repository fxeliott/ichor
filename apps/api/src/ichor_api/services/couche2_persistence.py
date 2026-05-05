"""Couche-2 outputs persistence — write/read agent runs.

Pairs with model `Couche2Output` and migration `0009_couche2_outputs.py`.

Each agent (CB-NLP, News-NLP, Sentiment, Positioning) is invoked from a
cron CLI; the CLI calls `persist_couche2_run` with the validated Pydantic
output, which serializes to JSONB and stores along with provenance.
Reading from the data_pool builder uses `latest_per_kind` which dedupes
by ran_at DESC.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Couche2Output

AgentKind = (
    str  # "cb_nlp" | "news_nlp" | "sentiment" | "positioning" — DB CHECK constraint enforces
)


async def persist_couche2_run(
    session: AsyncSession,
    *,
    agent_kind: AgentKind,
    model_used: str,
    payload: BaseModel,
    input_window_start: datetime | None = None,
    input_window_end: datetime | None = None,
    input_sources: list[str] | None = None,
    duration_ms: int | None = None,
    token_input: int | None = None,
    token_output: int | None = None,
    cost_usd: float | None = None,
    error: str | None = None,
) -> Couche2Output:
    """Write one Couche-2 run. Returns the persisted row."""
    now = datetime.now(UTC)
    row = Couche2Output(
        id=uuid4(),
        ran_at=now,
        created_at=now,
        agent_kind=agent_kind,
        model_used=model_used,
        input_window_start=input_window_start,
        input_window_end=input_window_end,
        payload=payload.model_dump(mode="json"),
        input_sources=input_sources,
        duration_ms=duration_ms,
        token_input=token_input,
        token_output=token_output,
        cost_usd=Decimal(str(cost_usd)) if cost_usd is not None else None,
        error=error,
    )
    session.add(row)
    await session.flush()
    return row


async def latest_per_kind(
    session: AsyncSession,
    *,
    kinds: tuple[str, ...] = ("cb_nlp", "news_nlp", "sentiment", "positioning"),
    max_age_hours: int = 12,
) -> dict[str, Couche2Output]:
    """Latest successful run per agent kind, freshness-bounded."""
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    out: dict[str, Couche2Output] = {}
    for kind in kinds:
        row = (
            await session.execute(
                select(Couche2Output)
                .where(
                    Couche2Output.agent_kind == kind,
                    Couche2Output.ran_at >= cutoff,
                    Couche2Output.error.is_(None),
                )
                .order_by(desc(Couche2Output.ran_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is not None:
            out[kind] = row
    return out


def _summarize_payload(kind: str, payload: dict[str, Any]) -> str:
    """1-3 line text summary of a Couche-2 payload for the data_pool block.

    The full payload is JSONB-stored; the data_pool block just shows the
    critical fields. Pass-2 can request the full payload via a separate
    endpoint when needed.
    """
    if kind == "cb_nlp":
        stances = payload.get("stances", [])
        n_shifts = len(payload.get("shifts", []))
        bullets = [f"{s['cb']}={s['stance']} (conf {s['confidence']:.2f})" for s in stances[:6]]
        return f"  - Stances: {', '.join(bullets)}\n  - Recent shifts: {n_shifts}"
    if kind == "news_nlp":
        narratives = payload.get("narratives", [])
        if not narratives:
            return "  - No narratives above threshold."
        bullets = [
            f"{n['label']} ({n['sentiment']}, intensity {n['intensity']:.2f})"
            for n in narratives[:5]
        ]
        return "  - Top narratives:\n" + "\n".join(f"    · {b}" for b in bullets)
    if kind == "sentiment":
        mood = payload.get("overall_retail_mood", "n/a")
        contra = payload.get("contrarian_signal", "no_extreme")
        return f"  - Retail mood: {mood} · contrarian flag: {contra}"
    if kind == "positioning":
        n_extreme = sum(
            1 for c in payload.get("cot", []) if c.get("flag") in ("long_extreme", "short_extreme")
        )
        n_smart = len(payload.get("smart_money_divergence", []))
        return f"  - COT extremes: {n_extreme} · smart-money divergences: {n_smart}"
    return "  - (unknown agent kind)"


async def render_couche2_block(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Couche-2 — latest agent outputs (freshness-bounded).

    Emits a markdown block summarizing the 4 agent outputs (CB-NLP,
    News-NLP, Sentiment, Positioning). Falls through gracefully if any
    agent has no recent run.
    """
    latest = await latest_per_kind(session)
    lines = ["## Couche-2 agents (latest, last 12h)"]
    sources: list[str] = []
    if not latest:
        lines.append("- (no fresh agent runs — cron timers may be down)")
        return "\n".join(lines), []
    for kind in ("cb_nlp", "news_nlp", "sentiment", "positioning"):
        row = latest.get(kind)
        if row is None:
            lines.append(f"- {kind}: stale or missing")
            continue
        age = datetime.now(UTC) - row.ran_at
        age_h = age.total_seconds() / 3600
        lines.append(f"- **{kind}** (model={row.model_used}, age {age_h:.1f}h):")
        lines.append(_summarize_payload(kind, row.payload))
        sources.append(f"couche2:{kind}@{row.ran_at.isoformat()}")
    return "\n".join(lines), sources
