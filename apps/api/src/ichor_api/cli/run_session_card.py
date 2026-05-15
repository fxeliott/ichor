"""Generate one session card and persist it to `session_card_audit`.

Usage :
  python -m ichor_api.cli.run_session_card EUR_USD pre_londres [--dry-run]

`--dry-run` (default) uses an in-memory scripted runner with canned
4-pass JSON responses — no Claude call, no quota burn. Useful for
smoke-testing the persistence + UI plumbing.

When `--live` is passed the runner posts to the Win11 claude-runner
through the Cloudflare Tunnel (Voie D). Requires the runner to be up
and `cf_access_client_id`/`cf_access_client_secret` to be set in
`/etc/ichor/api.env`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import structlog

from ..config import get_settings
from ..db import get_engine, get_sessionmaker

log = structlog.get_logger(__name__)


# Single source of truth — derived from `SessionType` Literal via
# `get_args` in ichor_brain.types. Closes the drift bug from ADR-024
# (where this set was hardcoded and went out of sync with the batch
# wrapper) — see ADR-031.
from ichor_brain.types import VALID_SESSION_TYPES as _VALID_SESSIONS


async def _run(
    asset: str,
    session_type: str,
    *,
    live: bool,
    enable_tools: bool = False,
    enable_rag: bool = False,
    notify_per_card: bool = False,
) -> int:
    asset = asset.upper()
    if session_type not in _VALID_SESSIONS:
        print(
            f"unknown session_type {session_type!r} (expected one of {sorted(_VALID_SESSIONS)})",
            file=sys.stderr,
        )
        return 2

    # Lazy import so that running this CLI doesn't force-install
    # `ichor_brain` into base test environments.
    try:
        from ichor_brain import (
            HttpRunnerClient,
            InMemoryRunnerClient,
            Orchestrator,
        )
        from ichor_brain.persistence import to_audit_row
    except ImportError as e:
        print(
            f"ichor_brain not installed in this venv: {e}\n"
            "Install it with: pip install -e packages/ichor_brain",
            file=sys.stderr,
        )
        return 3

    settings = get_settings()

    if live:
        runner = HttpRunnerClient(
            base_url=settings.claude_runner_url,
            cf_access_client_id=settings.cf_access_client_id,
            cf_access_client_secret=settings.cf_access_client_secret,
        )
    else:
        # Dry-run : use canned EUR/USD pré-Londres responses so the
        # persistence + UI path can be validated without a Claude call.
        runner = InMemoryRunnerClient(_dry_run_responses(asset))

    sm = get_sessionmaker()
    if live:
        # Real DB-backed data pool : every numeric claim source-stamped
        # so the Critic Agent can verify and Pass-2 mechanisms[].sources
        # can cite back. See services/data_pool.py.
        from ..services.data_pool import build_asset_data_only, build_data_pool

        async with sm() as build_session:
            pool = await build_data_pool(
                build_session,
                asset,
                session_type=session_type,  # type: ignore[arg-type]
            )
            asset_data = await build_asset_data_only(build_session, asset)
        data_pool = pool.markdown
        log.info(
            "data_pool.built",
            asset=asset,
            sections=pool.sections_emitted,
            sources_count=len(pool.sources),
            markdown_chars=len(pool.markdown),
        )
    else:
        # Dry-run keeps the historical static pool for back-compat with
        # the canned responses below.
        data_pool = (
            "DXY 105.30; US10Y 4.18 (-12bps); VIX 18.2 (+4.1); "
            "DFII10 1.85; BAMLH0A0HYM2 3.10; ECB Lagarde dovish on May 2."
        )
        asset_data = (
            f"{asset} : DGS10=4.18 IRLTLT01DEM156N=2.45 COT MM_short=80th_pct "
            "URL https://www.ecb.europa.eu/press/key/date/2026/html/ecb.sp260502.en.html"
        )

    # W105d : Pass-6 scenario_decompose enabled by default in live mode.
    # Dry-run stays Pass-1..4 only so canned responses don't break.
    # Calibration block is fetched per (asset, session_type) — falls
    # back to the canonical thresholds if no row exists yet (cold-start
    # before the W105b weekly Sunday cron has populated bins).
    calibration_block: str | None = None
    if live:
        try:
            from ..services.scenario_calibration import (
                compute_calibration_bins,
                format_calibration_block,
            )

            async with sm() as cal_session:
                cal = await compute_calibration_bins(
                    cal_session,
                    asset,
                    session_type,  # type: ignore[arg-type]
                )
                calibration_block = format_calibration_block(cal)
        except Exception as e:  # noqa: BLE001
            log.warning("calibration.fallback", asset=asset, error=str(e))
            calibration_block = None

    # W87 STEP-5 Cap5 tools activation — when `enable_tools=True` (CLI
    # opt-in flag), wire ToolConfig so Pass-1 régime + Pass-2 asset +
    # Pass-6 scenarios can call `mcp__ichor__query_db` and
    # `mcp__ichor__calc` during their reasoning. The MCP server spec
    # below tells the claude CLI subprocess (on Win11) to spawn
    # `python -m ichor_mcp.server` over stdio ; the MCP server itself
    # forwards to apps/api `/v1/tools/{query_db,calc}` over HTTPS with
    # the X-Ichor-Tool-Token header.
    #
    # Disabled by default in CLI for prudent prod rollout : flip ON via
    # `--enable-tools` once a single-asset smoke confirms the agentic
    # loop (tool_use → tool_result) completes within the runner's
    # rate-limit window and the audit trail (`tool_call_audit` table)
    # captures every invocation.
    tool_config = None
    if live and enable_tools:
        from ichor_brain.runner_client import ToolConfig

        tool_config = ToolConfig(
            mcp_config={
                "mcpServers": {
                    "ichor": {
                        "command": "python",
                        "args": ["-m", "ichor_mcp.server"],
                    }
                }
            },
            allowed_tools=(
                "mcp__ichor__query_db",
                "mcp__ichor__calc",
            ),
            max_turns=8,
            # Pass-3 stress + Pass-4 invalidation excluded by design —
            # they operate on prior-pass narrative, not raw market data
            # (cf ADR-077 §"Tool-pass scope rationale").
            enabled_for_passes=frozenset({"regime", "asset", "scenarios"}),
        )
        log.info("cap5.tools.enabled", passes=sorted(tool_config.enabled_for_passes))

    # W110d ADR-086 — past-only RAG analogues injection into Pass-1.
    # Opt-in via `--enable-rag` (default OFF for prudent rollout). The
    # retrieval is embargoed at >= 1 day (ADR-086 Invariant 1) and uses
    # bge-small-en-v1.5 ONNX CPU (Voie D Invariant 2). Failures are
    # best-effort : Pass-1 falls back to its pre-W110d prompt shape.
    analogues_section = ""
    if live and enable_rag:
        try:
            from ..services.rag_embeddings import (
                format_analogues_prompt_section,
                retrieve_analogues,
            )

            query_text = f"asset={asset} session={session_type}\n\n" + data_pool[:2000]
            async with sm() as rag_session:
                analogues = await retrieve_analogues(
                    rag_session,
                    query_text=query_text,
                    query_at=datetime.now(UTC),
                    asset=asset,
                    session_type=session_type,
                    k=5,
                    embargo_days=1,
                )
            analogues_section = format_analogues_prompt_section(analogues)
            log.info(
                "rag.analogues.retrieved",
                asset=asset,
                session_type=session_type,
                k=len(analogues),
                top_cos_dist=(analogues[0].cosine_distance if analogues else None),
            )
        except Exception as e:  # noqa: BLE001 — best-effort RAG path
            log.warning("rag.analogues.fallback", asset=asset, error=str(e))
            analogues_section = ""

    # W116c stage 2 (round-24) — Pass-3 addenda injection consumer.
    # Reads active addenda from pass3_addenda (populated by future W116c
    # PBS LLM generator) and renders them into the stress-pass prompt.
    # Gated by feature flag `pass3_addenda_injection_enabled` (default
    # False until W116c populates the table with meaningful content).
    # Regime key falls back to `session_type` because Pass-1 hasn't run
    # yet — matches the W115b/W116b pocket convention
    # COALESCE(regime_quadrant, session_type).
    pass3_addenda_section = ""
    if live:
        try:
            from ..services.feature_flags import is_enabled
            from ..services.pass3_addendum_injector import select_active_addenda

            async with sm() as ff_session:
                injection_on = await is_enabled(ff_session, "pass3_addenda_injection_enabled")
            if injection_on:
                async with sm() as addenda_session:
                    addenda = await select_active_addenda(
                        addenda_session,
                        regime=session_type,
                        asset=asset,
                    )
                if addenda:
                    bullets = "\n".join(f"- {a.content}" for a in addenda)
                    pass3_addenda_section = bullets
                    log.info(
                        "pass3_addenda.injected",
                        asset=asset,
                        session_type=session_type,
                        n=len(addenda),
                    )
        except Exception as e:  # noqa: BLE001 — best-effort injection
            log.warning("pass3_addenda.fallback", asset=asset, error=str(e))
            pass3_addenda_section = ""

    orch = Orchestrator(
        runner=runner,
        enable_scenarios=live,
        tool_config=tool_config,
    )
    result = await orch.run(
        session_type=session_type,  # type: ignore[arg-type]
        asset=asset,
        data_pool=data_pool,
        asset_data=asset_data,
        now=datetime.now(UTC),
        calibration_block=calibration_block,
        analogues_section=analogues_section,
        pass3_addenda_section=pass3_addenda_section,
    )

    # === r51 ADR-017 + Critic verdict safety gate (P0.1 + P0.2) ===
    # Closes gap identified by r50.5 wave-2 audit (subagents F + I) :
    # boundary regex was wired only in addendum_generator (W116c) and
    # Pass 6 _reject_trade_tokens ; the main session_card persist path
    # had ZERO content-level safety check, and Critic verdict was
    # purely cosmetic (persisted to column without gating, surfaced via
    # /v1/today DISTINCT-ON exactly like an approved card).
    from ..services.session_card_safety_gate import evaluate_safety_gate

    _safety = evaluate_safety_gate(result.card)
    if _safety.rejected:
        log.warning(
            "session_card.safety_reject",
            asset=asset,
            session_type=session_type,
            **_safety.log_fields(),
        )
        _reason_label = (
            "ADR-017 token" if _safety.primary_reason == "adr017_token" else "Critic blocked"
        )
        print(
            f"REJECT · session_card NOT persisted (safety gate)\n"
            f"  asset      : {asset}\n"
            f"  session    : {session_type}\n"
            f"  adr017     : {len(_safety.adr017_violations)} violations "
            f"{list(_safety.adr017_violations[:3])}\n"
            f"  critic     : {_safety.critic_verdict}\n"
            f"  reason     : {_reason_label}",
            file=sys.stderr,
        )
        # Exit code 4 = safety reject (distinct from 0 success / 2 invalid
        # arg / 3 import error). Batch wrapper logs non-zero rc and
        # continues to next asset (run_session_cards_batch.py:107).
        return 4

    async with sm() as session:
        row = to_audit_row(result.card)
        session.add(row)
        await session.commit()
        log.info(
            "session_card.persisted",
            id=str(row.id),
            asset=row.asset,
            session_type=row.session_type,
            verdict=row.critic_verdict,
            duration_ms=row.claude_duration_ms,
        )

    # Publish a Redis pub/sub event so any open dashboard WS sees the
    # new card in real-time (ichor:session_card:new). Best-effort —
    # if Redis is unreachable we don't fail the persistence.
    try:
        import json as _json

        from redis import asyncio as aioredis  # type: ignore[import]

        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis.publish(
            "ichor:session_card:new",
            _json.dumps(
                {
                    "id": str(row.id),
                    "asset": row.asset,
                    "session_type": row.session_type,
                    "bias": row.bias_direction,
                    "conviction_pct": row.conviction_pct,
                    "verdict": row.critic_verdict,
                    "regime_quadrant": row.regime_quadrant,
                }
            ),
        )
        await redis.aclose()
    except Exception as e:
        log.warning("session_card.publish_failed", error=str(e))

    # Per-card PWA push notification — DISABLED BY DEFAULT to avoid the
    # N+1 storm (6 cards × per-card push + 1 end-of-batch summary push =
    # 7 push notifications per cron tick, UX noise). The batch runner
    # `run_session_cards_batch.py:108-124` emits a single summary push
    # end-of-batch ; per-card pushes opt-in via `notify_per_card=True`
    # for ad-hoc CLI runs or future event-driven crisis cards.
    if notify_per_card and row.critic_verdict and row.critic_verdict != "blocked":
        try:
            from ..services.push import send_to_all

            asset_pretty = row.asset.replace("_", "/")
            title = f"Ichor · {asset_pretty} · {row.session_type.replace('_', ' ')}"
            body = f"{row.bias_direction.upper()} {row.conviction_pct:.0f}% · {row.critic_verdict}"
            await send_to_all(title, body, url=f"/sessions/{row.asset}")
        except Exception as e:
            log.warning("session_card.push_failed", error=str(e))

    print(
        f"OK · session_card_audit row written\n"
        f"  asset      : {row.asset}\n"
        f"  session    : {row.session_type}\n"
        f"  bias       : {row.bias_direction}\n"
        f"  conviction : {row.conviction_pct:.0f} %\n"
        f"  critic     : {row.critic_verdict}\n"
        f"  duration   : {row.claude_duration_ms} ms\n"
        f"  hash       : {row.source_pool_hash[:16]}…"
    )
    return 0


def _dry_run_responses(asset: str):
    """Canned 4-pass responses tuned for the asset (EUR/USD-flavored)."""
    import json

    from ichor_brain.runner_client import RunnerResponse

    payloads = [
        {
            "quadrant": "haven_bid",
            "rationale": (
                "VIX printed 18.2 (up from 14.1), DXY at 105.30 (+1.2%), "
                "US10Y down to 4.18% — flight-to-safety move."
            ),
            "confidence_pct": 72.0,
            "macro_trinity_snapshot": {
                "DXY": 105.3,
                "US10Y": 4.18,
                "VIX": 18.2,
                "DFII10": 1.85,
                "BAMLH0A0HYM2": 3.1,
            },
        },
        {
            "asset": asset,
            "bias_direction": "short",
            "conviction_pct": 65.0,
            "magnitude_pips_low": 25.0,
            "magnitude_pips_high": 60.0,
            "timing_window_start": None,
            "timing_window_end": None,
            "mechanisms": [
                {
                    "claim": "US-DE 10Y diff widened +12bps in last 5 sessions",
                    "sources": ["DGS10", "IRLTLT01DEM156N"],
                }
            ],
            "catalysts": [],
            "correlations_snapshot": {f"{asset}_DXY_60d": -0.91},
            "polymarket_overlay": [],
        },
        {
            "counter_claims": [
                {
                    "claim": "EZ HICP services component re-accelerating",
                    "strength_pct": 35.0,
                    "sources": ["https://ec.europa.eu/eurostat"],
                }
            ],
            "revised_conviction_pct": 50.0,
            "notes": "65 - (35 * 0.5) ≈ 50.",
        },
        {
            "conditions": [
                {
                    "condition": "DXY breaks below 104.50 intraday",
                    "threshold": "104.50",
                    "source": "DXY",
                }
            ],
            "review_window_hours": 8,
        },
    ]
    return [
        RunnerResponse(
            text=f"```json\n{json.dumps(p)}\n```",
            raw={"stub": True},
            duration_ms=8_000,
        )
        for p in payloads
    ]


async def _main(args: list[str]) -> int:
    live = "--live" in args
    enable_tools = "--enable-tools" in args
    enable_rag = "--enable-rag" in args
    notify_per_card = "--notify-per-card" in args
    args = [
        a
        for a in args
        if a
        not in {
            "--live",
            "--dry-run",
            "--enable-tools",
            "--enable-rag",
            "--notify-per-card",
        }
    ]
    if len(args) < 2:
        print(
            "usage: python -m ichor_api.cli.run_session_card "
            "<asset> <session_type> "
            "[--dry-run|--live] [--enable-tools] [--enable-rag] "
            "[--notify-per-card]",
            file=sys.stderr,
        )
        return 2
    asset, session_type = args[0], args[1]
    try:
        return await _run(
            asset,
            session_type,
            live=live,
            enable_tools=enable_tools,
            enable_rag=enable_rag,
            notify_per_card=notify_per_card,
        )
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
