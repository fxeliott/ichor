"""DATA_SURPRISE_Z alert wiring.

Wires the previously DORMANT `DATA_SURPRISE_Z` alert (catalog metric
`data_surprise_z`, threshold ≥ 2.0). Builds on the existing
`assess_surprise_index()` proxy in `services/surprise_index.py` —
that function already computes per-series rolling z-scores on the 6
US macro headliners (PAYEMS / UNRATE / CPIAUCSL / PCEPI / INDPRO /
GDPC1) and polarity-corrects them.

This service is the bridge from the proxy index to the alert
catalog : it iterates over the per-series readings, fires
`check_metric("data_surprise_z", ...)` for each |z| ≥ 2.0
constituent, and records source-stamped audit metadata.

Why a bridge layer rather than firing directly inside
`assess_surprise_index` :
  - `assess_surprise_index` is already used by `data_pool.py` to
    feed Claude in Pass 1. Embedding alert side-effects there would
    leak the alerting concern into a read-only assessor.
  - The same proxy can power both the data_pool block AND the
    alert path with a single SQL pass — the bridge just iterates
    over the cached reading.

Source-stamping (ADR-017) :
  - Every fired alert carries `source: "FRED:<series_id>"` in
    extra_payload. Composite-level alerts (avg z) are NOT fired —
    only per-series. Eliot can drill from the alert to the precise
    macro print that triggered it.

Cron : daily 14h35 Paris (after the 14h30 US data release window).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .alerts_runner import check_metric
from .surprise_index import SurpriseIndexReading, assess_surprise_index

# Threshold mirrors the catalog default (`DATA_SURPRISE_Z` AlertDef
# `default_threshold=2.0`). Kept here as a constant for readability ;
# the real check is done by `check_metric` against the catalog row.
ALERT_Z_ABS_FLOOR: float = 2.0


@dataclass(frozen=True)
class DataSurpriseCheckResult:
    """Per-run summary so the CLI can log a one-line punch-list."""

    region: str
    composite_z: float | None
    composite_band: str
    n_series_evaluated: int
    n_series_alerting: int
    alerts_fired: list[str]
    """List of `<series_id>=<z>` strings for the alerts persisted."""


async def evaluate_data_surprise_z(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> DataSurpriseCheckResult:
    """Compute per-series surprise z-scores and fire alerts.

    Re-runs `assess_surprise_index` (the proxy already powers data_pool,
    so we tolerate the second SQL pass — surprise_index is cached
    only at the data_pool aggregation layer, not here).

    Returns a structured result so the CLI can print a punch-list.
    """
    reading: SurpriseIndexReading = await assess_surprise_index(session)
    alerts_fired: list[str] = []

    for series in reading.series:
        if series.z_score is None:
            continue
        if abs(series.z_score) < ALERT_Z_ABS_FLOOR:
            continue
        # Asset key for the catalog formatter — use the series_id so
        # the rendered alert reads "Surprise macro PAYEMS z=+2.31",
        # i.e. the trader sees the precise macro print at a glance.
        if persist:
            await check_metric(
                session,
                metric_name="data_surprise_z",
                current_value=series.z_score,
                asset=series.series_id,
                extra_payload={
                    "series_id": series.series_id,
                    "label": series.label,
                    "last_value": series.last_value,
                    "rolling_mean": series.rolling_mean,
                    "rolling_std": series.rolling_std,
                    "n_history": series.n_history,
                    "polarity": "inverted" if series.series_id == "UNRATE" else "natural",
                    "source": f"FRED:{series.series_id}",
                },
            )
        alerts_fired.append(f"{series.series_id}={series.z_score:+.2f}")

    return DataSurpriseCheckResult(
        region=reading.region,
        composite_z=reading.composite,
        composite_band=reading.band,
        n_series_evaluated=len(reading.series),
        n_series_alerting=len(alerts_fired),
        alerts_fired=alerts_fired,
    )
