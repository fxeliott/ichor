"""CLI runner for the Crisis Mode auto-trigger.

Wires the previously test-only `alerts.crisis_mode.assess_crisis`
into a systemd timer (every 5 min). When ≥2 crisis_mode-flagged
alerts are un-acknowledged in the trailing 60min window, this
runner :

  1. Inserts a synthetic alert with code='CRISIS_MODE_ACTIVE',
     severity='critical', listing the triggering codes in the
     source_payload.
  2. De-dups against any CRISIS_MODE_ACTIVE row already triggered
     in the same window (no spam).
  3. (Future) publishes to Redis pubsub for live dashboard push.

Symmetrical resolution : when the crisis count drops back below 2,
inserts CRISIS_MODE_RESOLVED — the dashboard listener can clear
the banner.

Usage:
    python -m ichor_api.cli.run_crisis_check          # dry-run
    python -m ichor_api.cli.run_crisis_check --persist
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import structlog
from sqlalchemy import desc, select

from ..alerts.crisis_mode import assess_crisis
from ..db import get_engine, get_sessionmaker
from ..models import Alert

log = structlog.get_logger(__name__)

_CRISIS_ACTIVE_CODE = "CRISIS_MODE_ACTIVE"
_CRISIS_RESOLVED_CODE = "CRISIS_MODE_RESOLVED"
_DEDUP_WINDOW_MIN = 60


async def _last_crisis_active(session) -> Alert | None:
    """Most recent CRISIS_MODE_ACTIVE row that hasn't been resolved."""
    stmt = (
        select(Alert)
        .where(Alert.alert_code == _CRISIS_ACTIVE_CODE)
        .order_by(desc(Alert.triggered_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _last_crisis_resolved(session, *, after: datetime) -> Alert | None:
    """Most recent CRISIS_MODE_RESOLVED triggered after `after`."""
    stmt = (
        select(Alert)
        .where(
            Alert.alert_code == _CRISIS_RESOLVED_CODE,
            Alert.triggered_at >= after,
        )
        .order_by(desc(Alert.triggered_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _emit_active(session, *, codes: list[str], score: float) -> None:
    now = datetime.now(UTC)
    session.add(
        Alert(
            id=uuid4(),
            created_at=now,
            updated_at=now,
            alert_code=_CRISIS_ACTIVE_CODE,
            severity="critical",
            asset=None,
            triggered_at=now,
            metric_name="crisis_concurrent_count",
            metric_value=float(len(codes)),
            threshold=2.0,
            direction="above",
            source_payload={"triggering_codes": codes, "severity_score": score},
            title=f"Crisis Mode actif — {len(codes)} déclencheurs : {', '.join(codes[:5])}",
            description=(
                "Composite Crisis Mode triggered : ≥2 crisis_mode alerts "
                "un-acknowledged in the trailing 60min window."
            ),
        )
    )
    # Live-push to dashboard via Redis pubsub. Channel name is
    # documented in the original alerts/crisis_mode.py:6 docstring.
    # Fail-soft : a Redis hiccup must not block the DB write.
    await _publish_crisis_event(
        action="active",
        payload={
            "triggering_codes": codes,
            "severity_score": score,
            "ts": now.isoformat(),
        },
    )


async def _emit_resolved(session, *, prior_codes: list[str]) -> None:
    now = datetime.now(UTC)
    session.add(
        Alert(
            id=uuid4(),
            created_at=now,
            updated_at=now,
            alert_code=_CRISIS_RESOLVED_CODE,
            severity="info",
            asset=None,
            triggered_at=now,
            metric_name="crisis_concurrent_count",
            metric_value=0.0,
            threshold=2.0,
            direction="below",
            source_payload={"prior_codes": prior_codes},
            title="Crisis Mode résolu",
            description=(
                "Crisis Mode dropped below threshold (alerts acknowledged or aged out)."
            ),
        )
    )
    await _publish_crisis_event(
        action="resolved",
        payload={"prior_codes": prior_codes, "ts": now.isoformat()},
    )


_REDIS_CHANNEL = "ichor:crisis:active"


async def _publish_crisis_event(*, action: str, payload: dict) -> None:
    """Publish a JSON event on the crisis pubsub channel.

    Best-effort : if redis-py isn't installed or the connection fails,
    log at debug and proceed. The DB write remains the source of truth.
    """
    try:
        import json

        from ..config import get_settings
        from ..services.rate_limiter import make_redis_client

        client = make_redis_client(get_settings().redis_url)
        if client is None:
            return
        try:
            msg = json.dumps({"action": action, **payload})
            await client.publish(_REDIS_CHANNEL, msg)
        finally:
            try:
                await client.close()
            except Exception:
                pass
    except Exception as exc:
        log.debug("crisis_check.redis_publish_failed", error=str(exc)[:200])


async def run(*, persist: bool, min_concurrent: int = 2, lookback_min: int = 60) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        assessment = await assess_crisis(
            session, min_concurrent=min_concurrent, lookback_minutes=lookback_min
        )
        last_active = await _last_crisis_active(session)
        # "Currently active in DB" = last CRISIS_MODE_ACTIVE that hasn't
        # been followed by a CRISIS_MODE_RESOLVED.
        currently_active_in_db = False
        if last_active is not None:
            resolved_after = await _last_crisis_resolved(
                session, after=last_active.triggered_at
            )
            currently_active_in_db = resolved_after is None

    print(
        f"Crisis check · is_active={assessment.is_active} "
        f"codes={assessment.triggering_codes} score={assessment.severity_score:.1f} "
        f"db_state_active={currently_active_in_db}"
    )

    if persist:
        async with sm() as session:
            # State machine :
            #  - assessment ON, db OFF → emit ACTIVE
            #  - assessment ON, db ON  → no-op (sustained crisis ; we
            #    don't re-emit to keep the alerts table clean)
            #  - assessment OFF, db ON → emit RESOLVED
            #  - assessment OFF, db OFF → no-op
            if assessment.is_active and not currently_active_in_db:
                await _emit_active(
                    session,
                    codes=list(set(assessment.triggering_codes)),
                    score=assessment.severity_score,
                )
                await session.commit()
                print("Crisis check · emitted CRISIS_MODE_ACTIVE")
            elif not assessment.is_active and currently_active_in_db:
                # Pull prior_codes from the last ACTIVE row's payload
                prior_codes: list[str] = []
                if last_active and isinstance(last_active.source_payload, dict):
                    prior_codes = list(
                        last_active.source_payload.get("triggering_codes") or []
                    )
                await _emit_resolved(session, prior_codes=prior_codes)
                await session.commit()
                print("Crisis check · emitted CRISIS_MODE_RESOLVED")
            else:
                print("Crisis check · no transition (sustained or quiet)")

    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_crisis_check")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--min-concurrent", type=int, default=2)
    parser.add_argument("--lookback-min", type=int, default=_DEDUP_WINDOW_MIN)
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(
            run(
                persist=args.persist,
                min_concurrent=args.min_concurrent,
                lookback_min=args.lookback_min,
            )
        )
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
