"""Real-time alert runner — bridges metric writes to the alert catalog.

Audit (2026-05-05) revealed the 33-entry alert catalog
(`alerts/catalog.py`) was 100% UNWIRED in production : the evaluator
existed but no caller invoked it. Eliot had never received an
auto-generated alert.

This service closes that gap. Each collector handler that writes a
metric (FRED VIXCLS, gex_snapshots dealer_gex_total, FRED
BAMLH0A0HYM2, etc.) calls `check_metric()` after persistence, which :

  1. Fetches the previous value of that metric (one row back).
  2. Optionally computes a delta synthetic series (`*_d` suffix —
     the catalog encodes thresholds on deltas like SOFR_d, gex_d).
  3. Runs alerts.evaluator.evaluate_metric.
  4. Persists each AlertHit as an `alerts` row, idempotent on a
     short de-dup window so flapping doesn't spam.

ADR-022 §alerts integration. Crisis Mode auto-detection follows in
a separate cron (services/crisis_mode_runner) on top of this stream.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import desc, select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from ..alerts.catalog import ALL_ALERTS
from ..alerts.evaluator import AlertHit, evaluate_metric
from ..models import Alert, FredObservation, PolygonGexSnapshot

log = structlog.get_logger(__name__)

# De-dup window : if the same alert_code+asset fired within this
# window, we don't insert a new row. Prevents "VIX_SPIKE every 5 min"
# spam during a sustained spike.
_DEDUP_WINDOW = timedelta(hours=2)


async def _fetch_previous_fred_value(
    session: AsyncSession, *, series_id: str, before: datetime
) -> float | None:
    """Get the value of `series_id` strictly before `before`."""
    stmt = (
        select(FredObservation.value)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.created_at < before,
        )
        .order_by(desc(FredObservation.created_at))
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return float(row) if row is not None else None


async def _fetch_previous_gex_value(
    session: AsyncSession, *, asset: str, before: datetime
) -> float | None:
    """Get the previous dealer_gex_total for an asset (yfinance/flashalpha)."""
    stmt = (
        select(PolygonGexSnapshot.dealer_gex_total)
        .where(
            PolygonGexSnapshot.asset == asset,
            PolygonGexSnapshot.captured_at < before,
        )
        .order_by(desc(PolygonGexSnapshot.captured_at))
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return float(row) if row is not None else None


async def _is_recent_duplicate(
    session: AsyncSession, *, alert_code: str, asset: str | None
) -> bool:
    """True if the same code+asset already fired within _DEDUP_WINDOW."""
    cutoff = datetime.now(UTC) - _DEDUP_WINDOW
    sql = (
        "SELECT 1 FROM alerts WHERE alert_code = :code "
        "AND triggered_at >= :cutoff "
        + ("AND asset = :asset " if asset else "AND asset IS NULL ")
        + "LIMIT 1"
    )
    params: dict[str, Any] = {"code": alert_code, "cutoff": cutoff}
    if asset:
        params["asset"] = asset
    row = (await session.execute(sa_text(sql), params)).first()
    return row is not None


def _format_title_safe(template: str, *, value: float, payload: dict[str, Any] | None) -> str:
    """Render the title_template with `value` + any source_payload key.

    Catalog templates may reference {tenor}, {asset}, {pair}, {model_id},
    {market}, {match_event}, etc. — all live in source_payload. Missing
    placeholders fall back to '?' to keep the title human-readable
    instead of raising KeyError.
    """

    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "?"

    fmt = _SafeDict(value=value)
    if payload:
        for k, v in payload.items():
            fmt[k] = v
    try:
        # str.format_map ignores extra fields; uses _SafeDict for missing.
        return template.format_map(fmt)
    except (IndexError, ValueError):
        # Defensive : malformed template falls back to the raw code.
        return template


def _persist_hit(session: AsyncSession, hit: AlertHit, *, asset: str | None) -> None:
    """Add the Alert ORM row; commit is the caller's responsibility."""
    now = datetime.now(UTC)
    title = _format_title_safe(
        hit.alert_def.title_template,
        value=hit.metric_value,
        payload=hit.source_payload,
    )
    session.add(
        Alert(
            id=uuid4(),
            created_at=now,
            updated_at=now,
            alert_code=hit.alert_def.code,
            severity=hit.alert_def.severity,
            asset=asset,
            triggered_at=now,
            metric_name=hit.alert_def.metric_name,
            metric_value=float(hit.metric_value),
            threshold=float(hit.threshold),
            direction=hit.direction_observed,
            source_payload=hit.source_payload,
            title=title[:256],
            description=hit.alert_def.description or None,
        )
    )


async def check_metric(
    session: AsyncSession,
    *,
    metric_name: str,
    current_value: float,
    previous_value: float | None = None,
    asset: str | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> list[AlertHit]:
    """Generic entry point — evaluate + de-dup + persist any alerts.

    Returns the AlertHits actually persisted (post-dedup). Caller must
    `await session.commit()` for the writes to land.
    """
    hits = evaluate_metric(
        metric_name,
        current_value,
        previous_value=previous_value,
        asset=asset,
        extra_payload=extra_payload,
    )
    if not hits:
        return []

    persisted: list[AlertHit] = []
    for hit in hits:
        if await _is_recent_duplicate(session, alert_code=hit.alert_def.code, asset=asset):
            log.debug("alert.dedup_skip", code=hit.alert_def.code, asset=asset)
            continue
        _persist_hit(session, hit, asset=asset)
        persisted.append(hit)
        log.info(
            "alert.triggered",
            code=hit.alert_def.code,
            severity=hit.alert_def.severity,
            asset=asset,
            metric=metric_name,
            value=current_value,
        )
    return persisted


# ── Convenience wrappers per metric source ─────────────────────────


async def check_fred_alerts(
    session: AsyncSession,
    *,
    series_id: str,
    current_value: float,
    asset: str | None = None,
) -> list[AlertHit]:
    """Auto-fetch previous + evaluate against the catalog.

    For series with a delta-flavored alert (e.g., BAMLH0A0HYM2 has
    BAMLH0A0HYM2_d), we ALSO check the synthetic delta metric using
    (current - previous) ; the catalog encodes both level and delta
    thresholds on the same FRED series id.
    """
    now = datetime.now(UTC)
    prev = await _fetch_previous_fred_value(session, series_id=series_id, before=now)

    persisted = await check_metric(
        session,
        metric_name=series_id,
        current_value=current_value,
        previous_value=prev,
        asset=asset,
    )

    # Delta metric — the catalog uses the convention <series>_d for
    # period-over-period changes. Trigger a second evaluation if any
    # AlertDef references it.
    delta_metric = f"{series_id}_d"
    if any(a.metric_name == delta_metric for a in ALL_ALERTS) and prev is not None:
        delta = current_value - prev
        persisted += await check_metric(
            session,
            metric_name=delta_metric,
            current_value=delta,
            previous_value=None,
            asset=asset,
            extra_payload={"current_level": current_value, "previous_level": prev},
        )
    return persisted


async def check_gex_alerts(
    session: AsyncSession,
    *,
    asset: str,
    dealer_gex_total: float,
) -> list[AlertHit]:
    """GEX_FLIP / DEALER_GAMMA_FLIP — both fire on cross_down through 0.

    The catalog references two metric names (gex_d for the global
    sign-cross flag, gex_dealer for the per-asset variant). We feed
    both with the previous→current pair so the cross_down direction
    can be detected.
    """
    now = datetime.now(UTC)
    prev = await _fetch_previous_gex_value(session, asset=asset, before=now)

    persisted: list[AlertHit] = []
    persisted += await check_metric(
        session,
        metric_name="gex_dealer",
        current_value=dealer_gex_total,
        previous_value=prev,
        asset=asset,
    )
    persisted += await check_metric(
        session,
        metric_name="gex_d",
        current_value=dealer_gex_total,
        previous_value=prev,
        asset=asset,
    )
    return persisted
