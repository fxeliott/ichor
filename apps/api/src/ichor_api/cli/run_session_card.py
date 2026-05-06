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


# 5 session windows aligned with run_session_cards_batch.py + the
# SessionType Literal in ichor_brain. The drift between this set
# and the batch set silently killed every ny_mid/ny_close run since
# 2026-05-04 (cf SESSION_LOG_2026-05-06.md).
_VALID_SESSIONS = {"pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"}


async def _run(asset: str, session_type: str, *, live: bool) -> int:
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

    orch = Orchestrator(runner=runner)
    result = await orch.run(
        session_type=session_type,  # type: ignore[arg-type]
        asset=asset,
        data_pool=data_pool,
        asset_data=asset_data,
        now=datetime.now(UTC),
    )

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

    # Send PWA push notification on approved/amendments cards (best-effort
    # — never fail the persistence). Skip blocked since not actionable.
    if row.critic_verdict and row.critic_verdict != "blocked":
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
    args = [a for a in args if a not in {"--live", "--dry-run"}]
    if len(args) < 2:
        print(
            "usage: python -m ichor_api.cli.run_session_card "
            "<asset> <session_type> [--dry-run|--live]",
            file=sys.stderr,
        )
        return 2
    asset, session_type = args[0], args[1]
    try:
        return await _run(asset, session_type, live=live)
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
