"""Seed development data — populate sample bias_signals + alerts + briefings
so the dashboard has something to show before real collectors land.

Run:  python -m ichor_api.cli.seed_dev_data [--clean]

Idempotent for `--clean=False`: rows are inserted unconditionally; pre-existing
rows are not deduped (the schema has UUID PKs). Pass --clean to wipe first.
"""

from __future__ import annotations

import asyncio
import math
import random
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from ..db import get_engine, get_sessionmaker
from ..models import Alert, BiasSignal, Briefing

SAMPLE_ASSETS: list[str] = [
    "EUR_USD",
    "XAU_USD",
    "NAS100_USD",
    "USD_JPY",
    "SPX500_USD",
    "GBP_USD",
    "AUD_USD",
    "USD_CAD",
]

# How many historical bias_signals to seed per asset (drives the
# /assets/[code] sparkline density).
HISTORY_POINTS = 48  # 48 × 30min = 24h
HISTORY_STEP_MIN = 30


def _walk_probability(rng: random.Random, n: int, base: float = 0.55) -> list[float]:
    """Random walk in [0.2, 0.8] — visually plausible probability series."""
    series = []
    p = base
    for _ in range(n):
        # Mean-reverting noise around base
        p += rng.gauss(0, 0.02) + (base - p) * 0.05
        p = max(0.2, min(0.8, p))
        series.append(round(p, 4))
    return series


async def _wipe(sm: object) -> None:
    """Wipe sample-data tables. Refuses to run in production.

    Statements are hardcoded — no f-string into `text()` — so neither
    the table list nor the SQL is ever data-driven (see MED-3 in the
    2026-05-03 security audit).
    """
    from ..config import get_settings

    settings = get_settings()
    if settings.environment == "production":
        raise RuntimeError(
            "seed_dev_data --clean refuses to run when environment=production. "
            "Set ICHOR_API_ENVIRONMENT=development to override (DESTRUCTIVE)."
        )

    async with sm() as session:  # type: ignore[attr-defined]
        await session.execute(text("DELETE FROM alerts"))
        await session.execute(text("DELETE FROM bias_signals"))
        await session.execute(text("DELETE FROM briefings"))
        await session.commit()
    print("Wiped alerts + bias_signals + briefings tables")


async def _seed_bias_signals(sm: object, now: datetime, rng: random.Random) -> None:
    async with sm() as session:  # type: ignore[attr-defined]
        for i, asset in enumerate(SAMPLE_ASSETS):
            base_p = 0.45 + 0.1 * (i % 3)  # 0.45, 0.55, 0.65 cycle
            walk = _walk_probability(rng, HISTORY_POINTS, base=base_p)
            for k, prob in enumerate(walk):
                # k=0 is oldest, k=N-1 is newest
                ts = now - timedelta(minutes=HISTORY_STEP_MIN * (HISTORY_POINTS - 1 - k))
                direction = "long" if prob >= 0.5 else "short"
                ci_half = 0.06 + 0.02 * math.sin(k / 5)
                signal = BiasSignal(
                    asset=asset,
                    horizon_hours=24,
                    direction=direction,
                    probability=prob,
                    credible_interval_low=max(0.0, prob - ci_half),
                    credible_interval_high=min(1.0, prob + ci_half),
                    contributing_predictions=[uuid4(), uuid4()],
                    weights_snapshot={
                        "lightgbm": 0.30,
                        "xgboost": 0.25,
                        "random_forest": 0.20,
                        "logistic_reg": 0.15,
                        "bayesian_numpyro": 0.10,
                    },
                    notes="Seeded sample (no real model behind this row).",
                    generated_at=ts,
                )
                session.add(signal)
        await session.commit()
        print(
            f"Inserted {len(SAMPLE_ASSETS) * HISTORY_POINTS} bias_signals "
            f"({len(SAMPLE_ASSETS)} assets × {HISTORY_POINTS} pts)"
        )


async def _seed_alerts(sm: object, now: datetime, rng: random.Random) -> None:
    async with sm() as session:  # type: ignore[attr-defined]
        # Global alerts (asset=None)
        global_alerts = [
            {
                "alert_code": "VIX_SPIKE",
                "severity": "warning",
                "asset": None,
                "metric_name": "VIXCLS",
                "metric_value": 27.4,
                "threshold": 25.0,
                "direction": "above",
                "title": "VIX spike a 27.4 (seuil 25)",
                "description": "Sample warning — VIX above warning threshold.",
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
                "description": "Sample critical — HY credit spread crisis level.",
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
                "description": "Sample info — DXY broke 105 to the upside.",
            },
        ]
        for data in global_alerts:
            session.add(Alert(triggered_at=now - timedelta(minutes=30), **data))

        # Per-asset alerts so /assets/[code] is populated
        per_asset = [
            (
                "EUR_USD",
                "FX_RANGE_BREAK",
                "warning",
                "EUR/USD breakout du range 4h",
                "EUR_USD_close",
                1.0823,
                1.0810,
                "above",
                90,
            ),
            (
                "XAU_USD",
                "XAU_BREAKOUT_ATH",
                "info",
                "XAUUSD nouvel ATH 2961",
                "XAU_USD_high",
                2961,
                2900,
                "above",
                180,
            ),
            (
                "NAS100_USD",
                "VPIN_SPIKE",
                "warning",
                "NAS100 toxicite microstructure elevee",
                "vpin_1h",
                0.42,
                0.35,
                "above",
                45,
            ),
            (
                "USD_JPY",
                "BOJ_HAWKISH_SHIFT",
                "info",
                "BoJ hawkish vs prior meeting",
                "boj_net_hawkish",
                0.45,
                0.30,
                "cross_up",
                240,
            ),
            (
                "GBP_USD",
                "FX_RANGE_BREAK",
                "info",
                "GBP/USD touche 1.2700",
                "GBP_USD_high",
                1.2701,
                1.2700,
                "cross_up",
                120,
            ),
        ]
        for asset, code, sev, title, metric, val, thr, direction, mins_ago in per_asset:
            session.add(
                Alert(
                    alert_code=code,
                    severity=sev,
                    asset=asset,
                    metric_name=metric,
                    metric_value=val,
                    threshold=thr,
                    direction=direction,
                    title=title,
                    description=f"Seeded alert for dashboard demo ({asset}).",
                    triggered_at=now - timedelta(minutes=mins_ago),
                )
            )
        await session.commit()
        print(f"Inserted {len(global_alerts) + len(per_asset)} sample alerts")


async def _seed_briefings(sm: object, now: datetime) -> None:
    async with sm() as session:  # type: ignore[attr-defined]
        briefings = [
            {
                "briefing_type": "pre_londres",
                "triggered_at": now - timedelta(hours=2),
                "assets": SAMPLE_ASSETS[:5],
                "status": "completed",
                "context_token_estimate": 4500,
                "claude_duration_ms": 42_000,
                "briefing_markdown": (
                    "# Briefing pre-Londres (sample)\n\n"
                    "## Macro tape\n\n"
                    "Pas de surprise sur le CPI US d'hier (3.2% vs 3.1% attendu, "
                    "ecart faible). La Fed reste data-dependent. Pas de catalyst "
                    "immediat avant le NFP de vendredi.\n\n"
                    "## Per-asset tilt\n\n"
                    "**EUR/USD**: leger biais vendeur (probabilite 55-60%), "
                    "carry differentiel maintenu en faveur du dollar.\n\n"
                    "**XAU/USD**: neutre, attente catalyseur (FOMC ou geopolitique).\n\n"
                    "## Honest uncertainty\n\n"
                    "Briefing automatique sans donnees reelles — sample seed. Ne pas "
                    "trader dessus.\n\n"
                    "---\n"
                    "*Briefing genere par intelligence artificielle (sample). Analyse non "
                    "personnalisee a but informatif uniquement.*"
                ),
            },
            {
                "briefing_type": "ny_mid",
                "triggered_at": now - timedelta(hours=8),
                "assets": SAMPLE_ASSETS,
                "status": "completed",
                "context_token_estimate": 5100,
                "claude_duration_ms": 58_000,
                "briefing_markdown": (
                    "# Briefing NY mid (sample)\n\n"
                    "Sample briefing pour mid-NY session. Marche orderly, vol moderee.\n\n"
                    "*Briefing genere par intelligence artificielle (sample).*"
                ),
            },
            {
                "briefing_type": "weekly",
                "triggered_at": now - timedelta(days=2),
                "assets": SAMPLE_ASSETS,
                "status": "completed",
                "context_token_estimate": 8200,
                "claude_duration_ms": 95_000,
                "briefing_markdown": (
                    "# Weekly review (sample)\n\n"
                    "Recap macro semaine. Sample.\n\n"
                    "*Briefing genere par intelligence artificielle (sample).*"
                ),
            },
        ]
        for data in briefings:
            session.add(Briefing(**data))
        await session.commit()
        print(f"Inserted {len(briefings)} sample briefings")


async def seed(clean: bool = False, *, seed_value: int = 42) -> None:
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    rng = random.Random(seed_value)

    if clean:
        await _wipe(sm)

    await _seed_bias_signals(sm, now, rng)
    await _seed_alerts(sm, now, rng)
    await _seed_briefings(sm, now)

    await get_engine().dispose()


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    asyncio.run(seed(clean=clean))
