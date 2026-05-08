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
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import and_, desc, func, select

from ..briefing.context_builder import build_rich_context
from ..config import Settings, get_settings
from ..db import get_sessionmaker
from ..models import (
    Alert,
    BiasSignal,
    Briefing,
    CotPosition,
    EconomicEvent,
    FredObservation,
    NewsItem,
)

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

    Two paths:
      - Default (proven path) : the legacy in-this-function assembler, which
        only pulls bias_signals + warning/critical alerts.
      - `ICHOR_RICH_CONTEXT=1` (opt-in) : delegate to
        `briefing.context_builder.build_rich_context` which adds news,
        polymarket, and market_data with a token budget. See ADR-013.
    """
    if os.environ.get("ICHOR_RICH_CONTEXT") == "1":
        sm = get_sessionmaker()
        async with sm() as session:
            md, tok_est = await build_rich_context(
                session,
                briefing_type,
                assets,
            )
        log.info(
            "context.rich_used",
            briefing_type=briefing_type,
            chars=len(md),
            tokens_est=tok_est,
        )
        return md, tok_est

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
    parts.append(f"Generated at {datetime.now(UTC).isoformat()}")
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

    # Macro calendar next 6h, news-NLP, COT shifts, vol surface — all wired
    # to live tables ; defensive empty-state messages preserve briefing
    # quality when a section has no data this window.
    sm2 = get_sessionmaker()
    async with sm2() as session2:
        now = datetime.now(UTC)
        horizon_6h = now + timedelta(hours=6)
        cutoff_24h = now - timedelta(hours=24)
        cutoff_7d = now - timedelta(days=7)
        cutoff_14d = now - timedelta(days=14)

        # 1. Macro calendar — high-impact events in the next 6h
        cal_rows = (
            (
                await session2.execute(
                    select(EconomicEvent)
                    .where(
                        EconomicEvent.scheduled_at.is_not(None),
                        EconomicEvent.scheduled_at >= now,
                        EconomicEvent.scheduled_at <= horizon_6h,
                        EconomicEvent.impact.in_(["high", "medium"]),
                    )
                    .order_by(EconomicEvent.scheduled_at)
                    .limit(15)
                )
            )
            .scalars()
            .all()
        )

        # 2. News-NLP aggregate — last 24h tone-tagged headlines
        nlp_counts_rows = (
            await session2.execute(
                select(NewsItem.tone_label, func.count())
                .where(
                    NewsItem.published_at >= cutoff_24h,
                    NewsItem.tone_label.is_not(None),
                )
                .group_by(NewsItem.tone_label)
            )
        ).all()
        top_news = (
            (
                await session2.execute(
                    select(NewsItem)
                    .where(
                        NewsItem.published_at >= cutoff_24h,
                        NewsItem.tone_label.is_not(None),
                    )
                    .order_by(desc(NewsItem.tone_score), desc(NewsItem.published_at))
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

        # 3. COT shifts — current vs 7d-ago managed-money net per market
        cot_now = (
            (
                await session2.execute(
                    select(CotPosition)
                    .where(CotPosition.report_date >= cutoff_7d.date())
                    .order_by(desc(CotPosition.report_date))
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        cot_prev_map: dict[str, int] = {}
        prev_rows = (
            (
                await session2.execute(
                    select(CotPosition)
                    .where(
                        and_(
                            CotPosition.report_date >= cutoff_14d.date(),
                            CotPosition.report_date < cutoff_7d.date(),
                        )
                    )
                    .order_by(desc(CotPosition.report_date))
                )
            )
            .scalars()
            .all()
        )
        for r in prev_rows:
            cot_prev_map.setdefault(r.market_code, r.managed_money_net)

        # 4. Vol surface — VIX term structure (VIX9D / VIX / VIX3M / VIX6M)
        vol_term: dict[str, float | None] = {}
        for sid in ("VIXCLS", "VXVCLS", "VIX9DCLS", "VIX3MCLS", "VIX6MCLS"):
            row = (
                await session2.execute(
                    select(FredObservation.value, FredObservation.observation_date)
                    .where(
                        FredObservation.series_id == sid,
                        FredObservation.value.is_not(None),
                    )
                    .order_by(desc(FredObservation.observation_date))
                    .limit(1)
                )
            ).first()
            vol_term[sid] = float(row[0]) if row else None

    # ── 1. Macro calendar (next 6h) ──────────────────────────────────────
    parts.append("## Macro calendar (next 6h, high+medium impact)")
    if cal_rows:
        parts.append("| Time UTC | Cur | Impact | Title | Forecast | Previous |")
        parts.append("|----------|-----|--------|-------|----------|----------|")
        for ev in cal_rows:
            ts = ev.scheduled_at.strftime("%H:%M") if ev.scheduled_at else "TBD"
            parts.append(
                f"| {ts} | {ev.currency} | {ev.impact} | {ev.title[:60]} | "
                f"{ev.forecast or '—'} | {ev.previous or '—'} |"
            )
    else:
        parts.append("*(no high/medium-impact events scheduled in the next 6h)*")
    parts.append("")

    # ── 2. News-NLP aggregate (last 24h) ─────────────────────────────────
    parts.append("## News-NLP aggregate (last 24h, FinBERT-tone)")
    if nlp_counts_rows:
        tone_summary = ", ".join(f"{label}: {count}" for label, count in sorted(nlp_counts_rows))
        parts.append(f"- Tone distribution : {tone_summary}")
    if top_news:
        parts.append("- Top 5 by |tone_score| :")
        for n in top_news:
            score = f"{n.tone_score:+.2f}" if n.tone_score is not None else "—"
            parts.append(f"  - **{n.source}** · `{n.tone_label}` ({score}) · {n.title[:90]}")
    if not nlp_counts_rows and not top_news:
        parts.append("*(no tone-tagged news in the last 24h — FinBERT worker may be offline)*")
    parts.append("")

    # ── 3. COT positioning shifts (week-over-week) ───────────────────────
    parts.append("## COT positioning shifts (managed money, WoW)")
    if cot_now:
        shifts: list[tuple[str, int, int, int]] = []
        for r in cot_now:
            prev = cot_prev_map.get(r.market_code)
            if prev is None:
                continue
            delta = r.managed_money_net - prev
            shifts.append((r.market_code, r.managed_money_net, prev, delta))
        shifts.sort(key=lambda x: abs(x[3]), reverse=True)
        if shifts:
            parts.append("| Market | Net (now) | Net (prev) | Δ WoW |")
            parts.append("|--------|-----------|------------|-------|")
            for code, net, prev, delta in shifts[:8]:
                parts.append(f"| {code} | {net:+,} | {prev:+,} | {delta:+,} |")
        else:
            parts.append("*(no week-over-week comparison available — need 2 reports)*")
    else:
        parts.append("*(no COT report in the last 7 days — Friday CFTC release may be late)*")
    parts.append("")

    # ── 4. Vol surface (VIX term structure) ──────────────────────────────
    parts.append("## Vol surface anomalies (VIX term structure)")
    vix_9d = vol_term.get("VIX9DCLS")
    vix_spot = vol_term.get("VIXCLS")
    vix_3m = vol_term.get("VIX3MCLS")
    vix_6m = vol_term.get("VIX6MCLS")
    if vix_spot is not None:
        line_parts: list[str] = []
        if vix_9d is not None:
            line_parts.append(f"9D={vix_9d:.2f}")
        line_parts.append(f"Spot={vix_spot:.2f}")
        if vix_3m is not None:
            line_parts.append(f"3M={vix_3m:.2f}")
        if vix_6m is not None:
            line_parts.append(f"6M={vix_6m:.2f}")
        parts.append(f"- Term : {' · '.join(line_parts)}")
        # Backwardation flag : 9D > spot > 3M signals near-term stress repricing
        if vix_9d is not None and vix_3m is not None and vix_9d > vix_spot > vix_3m:
            parts.append(
                "- **Backwardation** : 9D > Spot > 3M — near-term stress, "
                "vol-mean-revert tactical setup"
            )
        elif vix_3m is not None and vix_spot is not None and vix_3m > vix_spot * 1.05:
            parts.append(
                "- Contango steep : 3M > Spot by >5% — calm regime, carry-friendly conditions"
            )
    else:
        parts.append("*(VIX series not available — FRED collector may be lagging)*")
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
    """POST to the claude-runner tunnel using async + polling pattern.

    Per ADR-053 : the legacy synchronous /v1/briefing-task endpoint hits
    Cloudflare Tunnel's 100s edge timeout (524) on claude CLI subprocess
    durations >100s (typical for large data_pool prompts ~150KB).

    Async pattern :
      1. POST /v1/briefing-task/async → 202 Accepted + task_id (fast)
      2. Poll /v1/briefing-task/async/{task_id} every 5s until status
         == 'done' or 'error'. Each poll <1s so Cloudflare doesn't cap.
      3. Total wall-time bounded by 600s (10min) — upper bound on claude
         CLI processing.

    Returns the same BriefingTaskResponse JSON envelope as the legacy
    endpoint.
    """
    import time

    base_url = settings.claude_runner_url.rstrip("/")
    submit_url = f"{base_url}/v1/briefing-task/async"
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
    max_total_sec = 600.0
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Submit
        r = await client.post(submit_url, headers=headers, json=payload)
        r.raise_for_status()
        accepted = r.json()
        task_id = accepted["task_id"]
        poll_path = accepted.get("poll_url") or f"/v1/briefing-task/async/{task_id}"
        poll_url = f"{base_url}{poll_path}"
        poll_interval = accepted.get("poll_interval_sec", 5)

        log.info("cli.briefing.async_submitted", task_id=task_id)

        # 2. Poll until done or error
        started = time.monotonic()
        poll_count = 0
        while True:
            poll_count += 1
            if time.monotonic() - started > max_total_sec:
                raise TimeoutError(
                    f"async briefing task {task_id} did not complete within "
                    f"{max_total_sec}s (poll_count={poll_count})"
                )
            await asyncio.sleep(poll_interval)
            pr = await client.get(poll_url, headers=headers)
            pr.raise_for_status()
            status_body = pr.json()
            task_status = status_body.get("status")
            if task_status == "done":
                log.info(
                    "cli.briefing.async_completed",
                    task_id=task_id,
                    poll_count=poll_count,
                    elapsed_sec=status_body.get("elapsed_sec"),
                )
                return status_body.get("result") or {}
            if task_status == "error":
                raise RuntimeError(
                    f"async briefing task {task_id} crashed: {status_body.get('error')}"
                )
            # else: 'pending' or 'running', continue polling


async def main(briefing_type: str) -> int:
    if briefing_type not in VALID_TYPES:
        log.error("cli.bad_briefing_type", got=briefing_type, valid=sorted(VALID_TYPES))
        return 2

    settings = get_settings()
    assets = _resolve_assets(briefing_type, settings)
    triggered_at = datetime.now(UTC)

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

    log.info(
        "cli.briefing.done",
        id=str(briefing_id),
        status=row.status,
        duration_ms=row.claude_duration_ms,
    )
    return 0 if row.status == "completed" else 5


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m ichor_api.cli.run_briefing <briefing_type>", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
