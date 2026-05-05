"""Alert evaluation engine — given a stream of metric observations, fire
matching alerts from the catalog when thresholds cross.

Stateless evaluation: caller passes the previous + current metric value;
this module returns 0 or 1 AlertDef matches with the action ("trigger",
"resolve") and the source payload. Persistence (Postgres insert + Redis
publish) is the caller's responsibility.

For Crisis Mode: see crisis_mode.py — composite of N≥2 simultaneous
crisis_mode-flagged alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .catalog import ALL_ALERTS, AlertDef


@dataclass
class AlertHit:
    alert_def: AlertDef
    metric_value: float
    threshold: float
    direction_observed: Literal["above", "below", "cross_up", "cross_down"]
    source_payload: dict


def _direction_matches(observed: str, expected: str) -> bool:
    return observed == expected


def evaluate_metric(
    metric_name: str,
    current_value: float,
    *,
    previous_value: float | None = None,
    asset: str | None = None,
    extra_payload: dict | None = None,
) -> list[AlertHit]:
    """Walk the alert catalog, return all alerts whose conditions match.

    Args:
        metric_name: must match AlertDef.metric_name (string equality).
        current_value: latest observation.
        previous_value: needed for cross_up / cross_down detection. If None,
            cross direction matches degrade to above/below at boundary.
        asset: optional asset code (for asset-scoped alerts).
        extra_payload: passed through to AlertHit.source_payload (snapshot of
            inputs used to evaluate, for audit).

    Returns:
        List of AlertHit (often empty, rarely > 1 per metric).
    """
    hits: list[AlertHit] = []

    for ad in ALL_ALERTS:
        if ad.metric_name != metric_name:
            continue

        observed: str | None = None
        if ad.default_direction == "above" and current_value >= ad.default_threshold:
            observed = "above"
        elif ad.default_direction == "below" and current_value <= ad.default_threshold:
            observed = "below"
        elif ad.default_direction == "cross_up":
            if (
                previous_value is not None
                and previous_value < ad.default_threshold <= current_value
            ):
                observed = "cross_up"
        elif ad.default_direction == "cross_down":
            if (
                previous_value is not None
                and previous_value > ad.default_threshold >= current_value
            ):
                observed = "cross_down"

        if observed is None:
            continue

        payload = dict(extra_payload or {})
        payload.update(
            {
                "current_value": current_value,
                "previous_value": previous_value,
                "metric_name": metric_name,
                "asset": asset,
            }
        )

        hits.append(
            AlertHit(
                alert_def=ad,
                metric_value=current_value,
                threshold=ad.default_threshold,
                direction_observed=observed,  # type: ignore[arg-type]
                source_payload=payload,
            )
        )

    return hits
