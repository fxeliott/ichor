"""CLI runner for ADWIN concept-drift detection on Brier errors.

Wires session_card_audit.brier_contribution stream (per model_id)
→ packages/ml/regime/concept_drift.DriftMonitor (ADWIN + Page-Hinkley)
→ CONCEPT_DRIFT_DETECTED alert when EITHER detector fires.

Why Brier errors as the drift signal :
  - The reconciler computes brier_contribution per session card =
    (predicted_prob - realized_outcome)^2 ∈ [0, 1].
  - A model whose Brier shifts upward over time = calibration is
    degrading = the model's predictions don't match the live
    distribution anymore = concept drift.
  - ADWIN is online + non-parametric ; perfect for streaming Brier.

Algorithm :
  1. For each model_id with ≥30 brier-scored cards in the last 90d :
  2. Stream the rows in chronological order through DriftMonitor.update()
  3. If any drift events fire on the latest few rows, emit
     CONCEPT_DRIFT_DETECTED (catalog metric='drift_score',
     threshold 0.7 above) with the drift severity in the payload.

Cadence : daily 04:30 Europe/Paris (after brier-drift at 04:00 — the
two are complementary : brier-drift catches level shifts, ADWIN
catches distributional changes).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from ..db import get_engine, get_sessionmaker
from ..models import SessionCardAudit

log = structlog.get_logger(__name__)

_LOOKBACK_DAYS = 90
_MIN_OBS_FOR_FIT = 30
# Drift events that occurred in the last `_RECENT_WINDOW` Brier obs
# count toward the alert. Older drift is historical context, not a
# fresh signal.
_RECENT_WINDOW = 10


async def run(*, persist: bool, lookback_days: int = _LOOKBACK_DAYS) -> int:
    sm = get_sessionmaker()
    since = datetime.now(UTC) - timedelta(days=lookback_days)

    async with sm() as session:
        stmt = (
            select(
                SessionCardAudit.model_id,
                SessionCardAudit.asset,
                SessionCardAudit.generated_at,
                SessionCardAudit.brier_contribution,
            )
            .where(
                SessionCardAudit.generated_at >= since,
                SessionCardAudit.brier_contribution.is_not(None),
            )
            .order_by(SessionCardAudit.generated_at.asc())
        )
        rows = (await session.execute(stmt)).all()

    print(f"Concept drift · {len(rows)} brier-scored cards in last {lookback_days}d")

    # Group by model_id (drift is per-model, not per-asset).
    by_model: dict[str, list[tuple[str, datetime, float]]] = {}
    for model_id, asset, ts, brier in rows:
        by_model.setdefault(model_id or "unknown", []).append((asset, ts, float(brier)))

    qualifying = {m: v for m, v in by_model.items() if len(v) >= _MIN_OBS_FOR_FIT}
    print(f"  {len(qualifying)}/{len(by_model)} models have ≥ {_MIN_OBS_FOR_FIT} obs (qualifying)")

    if not qualifying:
        return 0

    from ichor_ml.regime.concept_drift import DriftMonitor

    n_alerts = 0
    async with sm() as session:
        for model_id, stream in qualifying.items():
            mon = DriftMonitor()
            recent_drift_events = []
            stream_len = len(stream)
            for i, (_asset, _ts, brier_err) in enumerate(stream):
                events = mon.update(brier_err)
                # Track events that fired in the last _RECENT_WINDOW obs
                if events and i >= stream_len - _RECENT_WINDOW:
                    for e in events:
                        recent_drift_events.append(e)

            if not recent_drift_events:
                continue

            # Use the max severity across events as the drift_score.
            max_sev = max(e.severity for e in recent_drift_events)
            detectors = sorted({e.detector_name for e in recent_drift_events})
            print(
                f"  [{model_id}] drift detected — {len(recent_drift_events)} events, "
                f"max_severity={max_sev:.3f}, detectors={detectors}"
            )

            if persist:
                from ..services.alerts_runner import check_metric

                hits = await check_metric(
                    session,
                    metric_name="drift_score",
                    current_value=float(max_sev),
                    asset=None,  # drift is model-scoped, not asset-scoped
                    extra_payload={
                        "model_id": model_id,
                        "n_recent_events": len(recent_drift_events),
                        "detectors": detectors,
                        "stream_length": stream_len,
                    },
                )
                n_alerts += len(hits)
        if persist:
            await session.commit()

    if persist:
        print(f"Concept drift · {n_alerts} alerts")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_concept_drift")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=_LOOKBACK_DAYS)
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist, lookback_days=args.lookback_days))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
