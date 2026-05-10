"""CLI runner for the 4 Couche-2 agents (CB-NLP, News-NLP, Sentiment, Positioning).

Usage (systemd-driven, cf scripts/hetzner/register-cron-couche2.sh):
    python -m ichor_api.cli.run_couche2_agent <kind>

  where <kind> is one of: cb_nlp, news_nlp, sentiment, positioning.

Each invocation:
  1. Loads the relevant input window from Postgres via
     `services/couche2_context.build_context_for_kind` (real rows, no
     boilerplate — Phase B Sprint 3).
  2. Runs the agent's FallbackChain (Cerebras → Groq, per ADR-021;
     Claude wiring in `services/couche2_runner` when claude-runner URL
     is configured).
  3. Persists the structured output to `couche2_outputs` via
     `services/couche2_persistence.persist_couche2_run`.

Idempotency: each row is keyed (id, ran_at) so re-running within the
same second creates a duplicate (same ran_at unlikely in practice;
harmless if it occurs — readers DISTINCT ON ran_at).
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
    make_macro_chain,
    make_news_nlp_chain,
    make_positioning_chain,
    make_sentiment_chain,
)

from ..db import get_sessionmaker
from ..services.couche2_context import build_context_for_kind
from ..services.couche2_persistence import persist_couche2_run

log = structlog.get_logger(__name__)

VALID_KINDS = ("cb_nlp", "news_nlp", "sentiment", "positioning", "macro")


def _make_chain(kind: str):
    return {
        "cb_nlp": make_cb_nlp_chain,
        "news_nlp": make_news_nlp_chain,
        "sentiment": make_sentiment_chain,
        "positioning": make_positioning_chain,
        "macro": make_macro_chain,
    }[kind]()


async def run_one(kind: str, *, hours: int = 6) -> int:
    """Execute one agent run. Returns exit code (0 ok, 1 error, 2 invalid)."""
    if kind not in VALID_KINDS:
        log.error("couche2.invalid_kind", kind=kind, valid=VALID_KINDS)
        return 2
    started = time.monotonic()

    SessionLocal = get_sessionmaker()
    async with SessionLocal() as ctx_session:
        ctx = await build_context_for_kind(ctx_session, kind, hours=hours)

    log.info(
        "couche2.context.built",
        kind=kind,
        n_rows=ctx.n_rows,
        sources=ctx.sources,
        body_chars=len(ctx.body),
    )

    chain = _make_chain(kind)
    output: Any = None
    err: str | None = None
    model_used = "unknown"
    # Wave 66 — internal retry on transient 5xx (CF Tunnel 502/524 + 503
    # while another subprocess in flight). cb_nlp + news_nlp big-prompt
    # paths intermittently breach the CF 100s edge cap on legacy sync
    # endpoint /v1/agent-task. One retry with 60s sleep recovers most
    # cases without the structural async migration (deferred Phase D.1).
    log.info("couche2.run.start", kind=kind)
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            output = await chain.run(ctx.body)
            model_used = chain.last_success or "unknown"
            log.info("couche2.run.ok", kind=kind, model=model_used, attempt=attempt + 1)
            err = None
            break
        except Exception as exc:
            err = repr(exc)[:1000]
            transient_5xx = any(
                marker in err for marker in ("HTTP 502", "HTTP 503", "HTTP 504", "HTTP 524")
            )
            if attempt < max_attempts - 1 and transient_5xx:
                log.info(
                    "couche2.run.retry_5xx",
                    kind=kind,
                    attempt=attempt + 1,
                    error_marker="transient_5xx",
                    next_delay_s=60,
                )
                await asyncio.sleep(60)
                continue
            log.warning("couche2.run.failed", kind=kind, error=err, attempts=attempt + 1)
            break

    duration_ms = int((time.monotonic() - started) * 1000)

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
                    input_sources=ctx.sources or None,
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
