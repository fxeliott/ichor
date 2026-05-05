"""CLI runner template for the 4 Couche-2 agents (CB-NLP, News-NLP, Sentiment, Positioning).

Usage (systemd-driven, cf scripts/hetzner/register-cron-couche2.sh):
    python -m ichor_api.cli.run_couche2_agent <kind>

  where <kind> is one of: cb_nlp, news_nlp, sentiment, positioning.

Each invocation:
  1. Loads the relevant input window from Postgres (cb_speeches, news_items,
     polymarket_snapshots, etc.).
  2. Builds a context markdown block.
  3. Runs the agent's FallbackChain (Claude → Cerebras → Groq, per ADR-021;
     Claude wiring in Phase B Sprint 3).
  4. Persists the structured output to `couche2_outputs` via the persistence
     service.

Idempotency: each row is keyed (id, ran_at) so re-running within the same
second creates a duplicate (same ran_at unlikely in practice; harmless if
it occurs — readers DISTINCT ON ran_at).
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from ichor_agents.agents import (
    make_cb_nlp_chain,
    make_news_nlp_chain,
    make_positioning_chain,
    make_sentiment_chain,
)

from ..db import get_session_factory
from ..services.couche2_persistence import persist_couche2_run

log = structlog.get_logger(__name__)

VALID_KINDS = ("cb_nlp", "news_nlp", "sentiment", "positioning")


async def _build_context(kind: str, *, hours: int = 6) -> tuple[str, list[str]]:
    """Build the user prompt context for one agent kind.

    V0 implementation: minimal context-string. Phase B Sprint 3 enriches
    each kind with proper Postgres data loading (CbSpeech / NewsItem /
    AAII / COT / GEX rows).
    """
    now = datetime.now(UTC)
    earliest = now - timedelta(hours=hours)
    sources: list[str] = []
    if kind == "cb_nlp":
        body = (
            "Latest CB speeches in the last 7 days are in cb_speeches table. "
            "Synthesize Fed/ECB/BoE/BoJ/SNB/PBoC stances + identify shifts."
        )
    elif kind == "news_nlp":
        body = (
            f"Headlines since {earliest.isoformat()} are in news_items. "
            "Cluster by narrative and produce per-asset sentiment + entities."
        )
    elif kind == "sentiment":
        body = (
            "AAII weekly latest reading + Reddit posts last 6h. "
            "Detect contrarian extremes and emerging themes."
        )
    elif kind == "positioning":
        body = (
            "COT latest weekly + FlashAlpha GEX + Polymarket whales > $10K + "
            "yfinance options chains. Detect positioning extremes."
        )
    else:
        raise ValueError(f"unknown kind: {kind}")
    return body, sources


def _make_chain(kind: str):
    return {
        "cb_nlp": make_cb_nlp_chain,
        "news_nlp": make_news_nlp_chain,
        "sentiment": make_sentiment_chain,
        "positioning": make_positioning_chain,
    }[kind]()


async def run_one(kind: str, *, hours: int = 6) -> int:
    """Execute one agent run. Returns exit code (0 ok, 1 error)."""
    if kind not in VALID_KINDS:
        log.error("couche2.invalid_kind", kind=kind, valid=VALID_KINDS)
        return 2
    started = time.monotonic()
    body, sources = await _build_context(kind, hours=hours)
    chain = _make_chain(kind)

    output: Any = None
    err: str | None = None
    model_used = "unknown"
    try:
        log.info("couche2.run.start", kind=kind)
        output = await chain.run(body)
        # The first provider that succeeded — heuristic: first cfg in list.
        first_cfg = chain.providers[0]
        model_used = f"{first_cfg.name}:{first_cfg.default_model}"
        log.info("couche2.run.ok", kind=kind, model=model_used)
    except Exception as exc:
        err = repr(exc)[:1000]
        log.warning("couche2.run.failed", kind=kind, error=err)

    duration_ms = int((time.monotonic() - started) * 1000)

    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        try:
            if output is not None:
                await persist_couche2_run(
                    session,
                    agent_kind=kind,
                    model_used=model_used,
                    payload=output,
                    input_window_start=datetime.now(UTC) - timedelta(hours=hours),
                    input_window_end=datetime.now(UTC),
                    input_sources=sources or None,
                    duration_ms=duration_ms,
                )
            else:
                # Persist a row with error so observability surfaces the failure.
                from pydantic import BaseModel

                class _ErrorPayload(BaseModel):
                    error: str

                await persist_couche2_run(
                    session,
                    agent_kind=kind,
                    model_used=model_used,
                    payload=_ErrorPayload(error=err or "unknown"),
                    duration_ms=duration_ms,
                    error=err,
                )
            await session.commit()
        except Exception as commit_exc:
            log.error("couche2.persist.failed", error=str(commit_exc)[:200])
            await session.rollback()
            return 1

    return 0 if err is None else 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <kind>  (one of: {', '.join(VALID_KINDS)})", file=sys.stderr)
        return 2
    return asyncio.run(run_one(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
