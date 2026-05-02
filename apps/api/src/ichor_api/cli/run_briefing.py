"""The binary Hetzner cron timers call.

Usage: python -m ichor_api.cli.run_briefing <briefing_type>
   where briefing_type ∈ {pre_londres, pre_ny, ny_mid, ny_close, weekly, crisis}

Workflow (all error-handled with structured logging):
  1. Resolve the asset list from settings.briefing_assets_p1+p2 + briefing_type
  2. Insert briefings row with status='pending'
  3. Assemble context_markdown from:
       - latest BiasSignal per asset (current_signals)
       - last 24h alerts (severity >= warning)
       - last 24h news_nlp aggregate (TBD Phase 0 W2 collectors)
       - macro calendar next 6h (TBD)
  4. Update row → status='context_assembled', store context + token estimate
  5. POST to {claude_runner_url}/v1/briefing-task with CF Access headers
  6. On success: store briefing_markdown + claude_raw_response + duration
  7. (Phase 0 W4) trigger TTS + upload to R2 → store audio_mp3_url
  8. PUBLISH to Redis 'ichor:briefings:new' for WS push
  9. Status → 'completed'

Failure modes handled:
  - claude-runner timeout/error → status='failed', error_message stored,
    fallback to Cerebras+Groq (Couche 2) for a degraded briefing
  - DB unreachable → exit 1 (systemd will retry next cycle)
  - All providers fail → store a static template "Service degradation" briefing
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from ..config import Settings, get_settings
from ..db import get_engine, get_sessionmaker
from ..models import Alert, BiasSignal, Briefing
from sqlalchemy import desc, select

log = structlog.get_logger(__name__)


VALID_TYPES = {"pre_londres", "pre_ny", "ny_mid", "ny_close", "weekly", "crisis"}


def _resolve_assets(briefing_type: str, settings: Settings) -> list[str]:
    """Phase 1 actifs core (5) on pre_londres ; full 8 on others."""
    if briefing_type == "pre_londres":
        return settings.briefing_assets_p1
    return settings.briefing_assets_p1 + settings.briefing_assets_p2


async def _assemble_context(briefing_type: str, assets: list[str]) -> tuple[str, int]:
    """Pull bias signals + alerts + news from Postgres into a markdown blob.

    Returns (markdown, approximate_token_estimate).
    """
    sm = get_sessionmaker()
    async with sm() as session:
        # Latest BiasSignal per asset, h=24
        stmt = (
            select(BiasSignal)
            .where(
                BiasSignal.asset.in_(assets),
                BiasSignal.horizon_hours == 24,
            )
            .order_by(BiasSignal.asset, desc(BiasSignal.generated_at))
            .distinct(BiasSignal.asset)
        )
        signals = (await session.execute(stmt)).scalars().all()

        # Recent unacked warnings + critical
        alerts_stmt = (
            select(Alert)
            .where(Alert.severity.in_(["warning", "critical"]), Alert.acknowledged_at.is_(None))
            .order_by(desc(Alert.triggered_at))
            .limit(20)
        )
        alerts = (await session.execute(alerts_stmt)).scalars().all()

    parts: list[str] = []
    parts.append(f"# Briefing context ({briefing_type})")
    parts.append(f"Generated at {datetime.now(timezone.utc).isoformat()}")
    parts.append("")

    parts.append("## Bias signals (24h horizon, latest per asset)")
    if signals:
        parts.append("| Asset | Direction | Probability | CI 80% | Models |")
        parts.append("|-------|-----------|-------------|--------|--------|")
        for s in signals:
            mods = ",".join(sorted(s.weights_snapshot.keys()))
            parts.append(
                f"| {s.asset} | {s.direction} | {s.probability:.2f} | "
                f"[{s.credible_interval_low:.2f},{s.credible_interval_high:.2f}] | {mods} |"
            )
    else:
        parts.append("*(no bias signals in the last 24h — Phase 0 collectors not yet running)*")
    parts.append("")

    parts.append("## Active alerts (warning + critical, last 24h)")
    if alerts:
        for a in alerts:
            parts.append(
                f"- **{a.severity.upper()}** [{a.alert_code}] "
                f"{a.title} — {a.metric_name}={a.metric_value} ({a.direction} {a.threshold})"
            )
    else:
        parts.append("*(no active alerts — system nominal)*")
    parts.append("")

    parts.append("## TODO Phase 0 W2 — context expansion")
    parts.append("- Macro calendar next 6h (FRED + ECB)")
    parts.append("- News-NLP aggregate (Reuters/AP/FT, last 24h)")
    parts.append("- COT positioning shifts (weekly)")
    parts.append("- Vol surface anomalies (vollib)")
    parts.append("")

    text = "\n".join(parts)
    # Rough token estimate: 1 token ≈ 4 chars (English/French average)
    return text, len(text) // 4


async def _post_to_claude_runner(
    settings: Settings,
    briefing_type: str,
    assets: list[str],
    context: str,
) -> dict[str, Any]:
    """POST to the claude-runner tunnel. Returns the parsed response JSON."""
    url = settings.claude_runner_url.rstrip("/") + "/v1/briefing-task"
    headers = {
        "Content-Type": "application/json",
        "CF-Access-Client-Id": settings.cf_access_client_id,
        "CF-Access-Client-Secret": settings.cf_access_client_secret,
    }
    payload = {
        "briefing_type": briefing_type,
        "assets": assets,
        "context_markdown": context,
        "model": "opus" if briefing_type in {"weekly", "crisis"} else "sonnet",
        "effort": "high" if briefing_type in {"weekly", "crisis", "ny_close"} else "medium",
    }
    async with httpx.AsyncClient(timeout=420) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


async def main(briefing_type: str) -> int:
    if briefing_type not in VALID_TYPES:
        log.error("cli.bad_briefing_type", got=briefing_type, valid=sorted(VALID_TYPES))
        return 2

    settings = get_settings()
    assets = _resolve_assets(briefing_type, settings)
    triggered_at = datetime.now(timezone.utc)

    sm = get_sessionmaker()

    # 1. Insert pending row
    async with sm() as session:
        b = Briefing(
            briefing_type=briefing_type,
            triggered_at=triggered_at,
            assets=assets,
            status="pending",
        )
        session.add(b)
        await session.flush()
        briefing_id = b.id
        await session.commit()

    log.info("cli.briefing.created", id=str(briefing_id), type=briefing_type, assets=assets)

    # 2. Assemble context
    try:
        context, tok_est = await _assemble_context(briefing_type, assets)
        async with sm() as session:
            row = await session.get(Briefing, briefing_id)
            row.context_markdown = context
            row.context_token_estimate = tok_est
            row.status = "context_assembled"
            await session.commit()
    except Exception as e:
        log.error("cli.context_assemble_failed", id=str(briefing_id), error=str(e))
        async with sm() as session:
            row = await session.get(Briefing, briefing_id)
            row.status = "failed"
            row.error_message = f"context_assemble_failed: {e}"
            await session.commit()
        return 3

    # 3. POST to claude-runner
    try:
        result = await _post_to_claude_runner(settings, briefing_type, assets, context)
    except Exception as e:
        log.error("cli.claude_runner_call_failed", id=str(briefing_id), error=str(e))
        async with sm() as session:
            row = await session.get(Briefing, briefing_id)
            row.status = "failed"
            row.error_message = f"claude_runner_call_failed: {e}"
            await session.commit()
        return 4

    # 4. Persist result
    async with sm() as session:
        row = await session.get(Briefing, briefing_id)
        row.claude_runner_task_id = result.get("task_id")
        row.briefing_markdown = result.get("briefing_markdown")
        row.claude_raw_response = result.get("raw_claude_json")
        row.claude_duration_ms = result.get("duration_ms")
        row.status = "completed" if result.get("status") == "success" else "failed"
        if row.status == "failed":
            row.error_message = result.get("error_message")
        await session.commit()

    # 5. Pub/Sub to dashboard WS
    try:
        from redis import asyncio as aioredis
        redis = aioredis.from_url(settings.redis_url)
        await redis.publish(
            "ichor:briefings:new",
            json.dumps({"id": str(briefing_id), "type": briefing_type, "assets": assets}),
        )
        await redis.close()
    except Exception as e:
        log.warning("cli.redis_publish_failed", error=str(e))

    log.info("cli.briefing.done", id=str(briefing_id), status=row.status, duration_ms=row.claude_duration_ms)
    return 0 if row.status == "completed" else 5


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m ichor_api.cli.run_briefing <briefing_type>", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
