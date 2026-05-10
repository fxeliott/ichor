"""CLI runner for MODEL_PREDICTION_OUTLIER detection.

Wires bias_signals.probability stream → per-(asset, horizon) z-score
→ MODEL_PREDICTION_OUTLIER alert when |z| ≥ 3.0.

Algorithm :
  1. For each (asset, horizon_hours) with ≥30 bias_signals in the
     last 90d, compute mean + std of probability.
  2. Latest probability → z = (latest - mean) / std.
  3. If |z| ≥ 3.0 (catalog metric='pred_z', threshold 3.0 above),
     fire MODEL_PREDICTION_OUTLIER asset-scoped.

A 3-sigma outlier on a model's calibrated probability output is
either :
  - a genuine regime shift (the model is responding to it correctly)
  - a model failure (drift untracked by ADWIN/Brier yet)
Either way the trader needs to know — Eliot's discretionary review
catches both cases.

Cadence : daily 04:45 Europe/Paris (after concept-drift at 04:30 ;
the three ML self-monitors run consecutively).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from ..db import get_engine, get_sessionmaker
from ..models import BiasSignal

log = structlog.get_logger(__name__)

_LOOKBACK_DAYS = 90
_MIN_OBS = 30


async def run(*, persist: bool, lookback_days: int = _LOOKBACK_DAYS) -> int:
    sm = get_sessionmaker()
    since = datetime.now(UTC) - timedelta(days=lookback_days)

    async with sm() as session:
        stmt = (
            select(
                BiasSignal.asset,
                BiasSignal.horizon_hours,
                BiasSignal.created_at,
                BiasSignal.probability,
            )
            .where(BiasSignal.created_at >= since)
            .order_by(BiasSignal.created_at.asc())
        )
        rows = (await session.execute(stmt)).all()

    print(f"Prediction outlier · {len(rows)} bias_signals in last {lookback_days}d")

    grouped: dict[tuple[str, int], list[float]] = {}
    for asset, horizon, _ts, prob in rows:
        if prob is None:
            continue
        grouped.setdefault((asset, int(horizon)), []).append(float(prob))

    qualifying = {k: v for k, v in grouped.items() if len(v) >= _MIN_OBS}
    print(f"  {len(qualifying)}/{len(grouped)} (asset, horizon) pairs have ≥ {_MIN_OBS} obs")

    if not qualifying:
        return 0

    n_alerts = 0
    async with sm() as session:
        for (asset, horizon), probs in qualifying.items():
            latest = probs[-1]
            mean = sum(probs) / len(probs)
            var = sum((p - mean) ** 2 for p in probs) / max(1, len(probs) - 1)
            std = var**0.5
            if std <= 0:
                continue
            z = (latest - mean) / std
            print(
                f"  [{asset:10s} h={horizon:3d}h] latest={latest:.3f} mean={mean:.3f}±{std:.3f} "
                f"z={z:+.2f}"
            )

            if persist:
                from ..services.alerts_runner import check_metric

                hits = await check_metric(
                    session,
                    metric_name="pred_z",
                    current_value=abs(z),
                    asset=asset,
                    extra_payload={
                        "z_signed": z,
                        "horizon_hours": horizon,
                        "latest_probability": latest,
                        "history_mean": mean,
                        "history_std": std,
                        "n_obs": len(probs),
                    },
                )
                n_alerts += len(hits)
        if persist:
            await session.commit()

    if persist:
        print(f"Prediction outlier · {n_alerts} alerts triggered")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_prediction_outlier")
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
