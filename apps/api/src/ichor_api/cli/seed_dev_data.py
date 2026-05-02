"""Seed development data — populate sample bias_signals + alerts + 1 briefing
so the dashboard has something to show before real collectors land.

Run:  python -m ichor_api.cli.seed_dev_data [--clean]

Idempotent: existing rows with the same (asset, generated_at) are kept.
--clean wipes all rows first.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text

from ..db import get_engine, get_sessionmaker
from ..models import Alert, BiasSignal, Briefing


SAMPLE_ASSETS = ["EUR_USD", "XAU_USD", "NAS100_USD", "USD_JPY", "SPX500_USD",
                 "GBP_USD", "AUD_USD", "USD_CAD"]


async def seed(clean: bool = False) -> None:
    sm = get_sessionmaker()
    now = datetime.now(timezone.utc)

    if clean:
        async with sm() as session:
            for table in ("alerts", "bias_signals", "briefings"):
                await session.execute(text(f"DELETE FROM {table}"))
            await session.commit()
        print("Wiped alerts + bias_signals + briefings tables")

    # 8 bias signals (one per asset, h=24)
    async with sm() as session:
        for i, asset in enumerate(SAMPLE_ASSETS):
            # Alternate direction for visual variety
            direction = ["long", "short", "neutral"][i % 3]
            base_p = 0.5 + (0.1 * (i % 3 - 1))  # 0.4, 0.5, 0.6 cycle
            sig = BiasSignal(
                asset=asset,
                horizon_hours=24,
                direction=direction,
                probability=max(0.5, base_p) if direction == "long"
                            else max(0.5, 1 - base_p) if direction == "short"
                            else 0.5,
                credible_interval_low=max(0.0, base_p - 0.15),
                credible_interval_high=min(1.0, base_p + 0.15),
                contributing_predictions=[uuid4(), uuid4()],
                weights_snapshot={"lightgbm": 0.5, "xgboost": 0.5},
                notes="Seeded sample (no real model behind this row).",
                generated_at=now - timedelta(minutes=15),
            )
            session.add(sig)
        await session.commit()
        print(f"Inserted {len(SAMPLE_ASSETS)} sample bias_signals")

    # 3 alerts spanning severity range
    async with sm() as session:
        alerts_data = [
            {
                "alert_code": "VIX_SPIKE",
                "severity": "warning",
                "asset": None,
                "metric_name": "VIXCLS",
                "metric_value": 27.4,
                "threshold": 25.0,
                "direction": "above",
                "title": "VIX spike a 27.4 (seuil 25)",
                "description": "Sample warning — VIX above warning threshold",
            },
            {
                "alert_code": "HY_OAS_CRISIS",
                "severity": "critical",
                "asset": None,
                "metric_name": "BAMLH0A0HYM2",
                "metric_value": 850,
                "threshold": 800,
                "direction": "above",
                "title": "HY OAS critique a 850 bps (Crisis Mode trigger)",
                "description": "Sample critical — HY credit spread crisis level",
            },
            {
                "alert_code": "DXY_BREAKOUT_UP",
                "severity": "info",
                "asset": None,
                "metric_name": "DXY_close",
                "metric_value": 105.2,
                "threshold": 105.0,
                "direction": "cross_up",
                "title": "DXY breakout haussier 105.2",
                "description": "Sample info — DXY broke 105 to the upside",
            },
        ]
        for data in alerts_data:
            session.add(Alert(triggered_at=now - timedelta(minutes=30), **data))
        await session.commit()
        print(f"Inserted {len(alerts_data)} sample alerts")

    # 1 sample briefing
    async with sm() as session:
        b = Briefing(
            briefing_type="pre_londres",
            triggered_at=now - timedelta(hours=2),
            assets=SAMPLE_ASSETS[:5],
            status="completed",
            context_token_estimate=4500,
            briefing_markdown=(
                "# Briefing pre-Londres (sample)\n\n"
                "## Macro tape\n\n"
                "Pas de surprise sur le CPI US d'hier (3.2 pour cent vs 3.1 attendu, "
                "ecart faible). La Fed reste data-dependent. Pas de catalyst "
                "immediat avant le NFP de vendredi.\n\n"
                "## Per-asset tilt\n\n"
                "**EUR/USD**: leger biais vendeur (probabilite 55-60 pour cent), "
                "carry differentiel maintenu en faveur du dollar.\n\n"
                "**XAU/USD**: neutre, attente de catalyseur reel (FOMC ou geopolitique).\n\n"
                "## Honest uncertainty\n\n"
                "Briefing automatique sans donnees reelles — sample seed pour test "
                "dashboard. Ne pas trader dessus.\n\n"
                "---\n"
                "*Briefing genere par intelligence artificielle (sample). Analyse non "
                "personnalisee a but informatif uniquement.*"
            ),
            claude_duration_ms=42_000,
        )
        session.add(b)
        await session.commit()
        print(f"Inserted 1 sample briefing (id={b.id})")

    await get_engine().dispose()


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    asyncio.run(seed(clean=clean))
