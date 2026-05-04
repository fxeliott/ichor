"""Polymarket impact mapping — semantic clustering by trading-impact theme.

Clusters fresh Polymarket markets into themes that affect Eliot's 8
phase-1 assets, then surfaces the top-N markets per theme with their
current YES probability and the directional impact on each asset.

Themes (extensible) :
  - **fed_policy**       : "Fed cut", "FOMC hike", "interest rate"
  - **recession**        : "recession", "GDP negative"
  - **trump_election**   : "Trump 2028", presidential odds
  - **ukraine_russia**   : "Ukraine ceasefire", "Russia"
  - **israel_iran**      : "Israel", "Iran"
  - **china_taiwan**     : "China", "Taiwan", "Xi"
  - **inflation**        : "CPI", "inflation"
  - **oil**              : "WTI", "oil prices", "OPEC"

Each theme has impact magnitudes per asset based on standard FX desk
heuristics (Fed cut → USD weak → EUR/USD up).

Output: a structured ImpactReport listing per-asset signed impacts
weighted by YES probability of the markets that match the theme.

VISION_2026 — closes "se servir de polymarket comme outil d'analyse" :
turns the raw snapshot feed into actionable directional signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PolymarketSnapshot


# ─────────────────────── theme catalog ────────────────────────────────


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    keyword_phrases: list[list[str]]
    """List of phrases ; a market matches the theme if ALL tokens of one
    phrase appear in its question (case-insensitive)."""
    impact_per_asset: dict[str, float]
    """Signed impact magnitude when YES = 1.0. Scaled by (yes - 0.5) * 2."""


_THEMES: list[Theme] = [
    Theme(
        key="fed_cut",
        label="Fed rate cut",
        keyword_phrases=[
            ["fed", "cut"],
            ["fomc", "cut"],
            ["interest rate", "cut"],
            ["powell", "dovish"],
        ],
        impact_per_asset={
            "EUR_USD": +0.30,
            "GBP_USD": +0.30,
            "AUD_USD": +0.30,
            "USD_JPY": -0.30,
            "USD_CAD": -0.20,
            "XAU_USD": +0.40,
            "NAS100_USD": +0.30,
            "SPX500_USD": +0.25,
        },
    ),
    Theme(
        key="fed_hike",
        label="Fed rate hike",
        keyword_phrases=[
            ["fed", "hike"],
            ["fomc", "hike"],
            ["interest rate", "hike"],
            ["powell", "hawkish"],
        ],
        impact_per_asset={
            "EUR_USD": -0.30,
            "GBP_USD": -0.30,
            "AUD_USD": -0.30,
            "USD_JPY": +0.30,
            "USD_CAD": +0.20,
            "XAU_USD": -0.40,
            "NAS100_USD": -0.30,
            "SPX500_USD": -0.25,
        },
    ),
    Theme(
        key="recession",
        label="US recession",
        keyword_phrases=[
            ["recession"],
            ["us recession"],
            ["gdp", "negative"],
        ],
        impact_per_asset={
            "EUR_USD": -0.10,
            "GBP_USD": -0.10,
            "AUD_USD": -0.30,
            "USD_JPY": -0.20,
            "USD_CAD": +0.10,
            "XAU_USD": +0.20,
            "NAS100_USD": -0.40,
            "SPX500_USD": -0.40,
        },
    ),
    Theme(
        key="trump_election",
        label="Trump 2028 / election odds",
        keyword_phrases=[
            ["trump", "2028"],
            ["trump", "election"],
            ["republican", "nominee"],
        ],
        impact_per_asset={
            "EUR_USD": -0.10,
            "USD_JPY": +0.05,
            "XAU_USD": +0.10,
            "NAS100_USD": +0.05,
            "SPX500_USD": +0.05,
        },
    ),
    Theme(
        key="ukraine_russia",
        label="Ukraine-Russia",
        keyword_phrases=[
            ["ukraine", "ceasefire"],
            ["russia", "ukraine"],
            ["putin"],
            ["zelensky"],
        ],
        impact_per_asset={
            "EUR_USD": +0.15,  # ceasefire → EUR risk premium fades
            "XAU_USD": -0.15,
            "DCOILWTICO": -0.10,
        },
    ),
    Theme(
        key="israel_iran",
        label="Israel-Iran tensions",
        keyword_phrases=[
            ["israel", "iran"],
            ["iran", "strike"],
            ["middle east"],
        ],
        impact_per_asset={
            "EUR_USD": -0.10,
            "USD_JPY": -0.10,
            "XAU_USD": +0.30,
            "NAS100_USD": -0.15,
            "SPX500_USD": -0.15,
        },
    ),
    Theme(
        key="china_taiwan",
        label="China-Taiwan",
        keyword_phrases=[
            ["china", "taiwan"],
            ["xi", "taiwan"],
            ["taiwan", "invasion"],
        ],
        impact_per_asset={
            "AUD_USD": -0.20,
            "USD_JPY": -0.15,
            "XAU_USD": +0.25,
            "NAS100_USD": -0.30,
            "SPX500_USD": -0.30,
        },
    ),
    Theme(
        key="inflation",
        label="Inflation prints",
        keyword_phrases=[
            ["cpi"],
            ["inflation", "above"],
            ["pce", "above"],
        ],
        impact_per_asset={
            "EUR_USD": -0.15,
            "USD_JPY": +0.15,
            "XAU_USD": +0.10,
            "NAS100_USD": -0.15,
            "SPX500_USD": -0.10,
        },
    ),
    Theme(
        key="oil_supply",
        label="Oil / OPEC",
        keyword_phrases=[
            ["wti"],
            ["opec"],
            ["oil prices"],
            ["crude oil"],
        ],
        impact_per_asset={
            "USD_CAD": -0.20,  # higher oil → CAD strengthens
            "XAU_USD": +0.10,
            "NAS100_USD": -0.10,
        },
    ),
]


# ─────────────────────── output container ─────────────────────────────


@dataclass(frozen=True)
class MarketHit:
    slug: str
    question: str
    yes: float
    weight: float
    """YES-derived weight in [-1, +1] : (yes - 0.5) * 2."""


@dataclass(frozen=True)
class ThemeHit:
    theme_key: str
    label: str
    n_markets: int
    avg_yes: float
    """Mean YES across matched markets."""
    markets: list[MarketHit]
    """Top 5 by absolute weight."""
    impact_per_asset: dict[str, float]
    """Signed [-1, +1] estimated impact on each asset."""


@dataclass(frozen=True)
class ImpactReport:
    generated_at: datetime
    n_markets_scanned: int
    themes: list[ThemeHit] = field(default_factory=list)
    asset_aggregate: dict[str, float] = field(default_factory=dict)
    """Sum of weighted impacts per asset across all themes."""


def _matches_phrase(text_lower: str, phrase: list[str]) -> bool:
    return all(token in text_lower for token in phrase)


async def assess_polymarket_impact(
    session: AsyncSession, *, hours: int = 24, limit: int = 200
) -> ImpactReport:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    raw_rows = list(
        (
            await session.execute(
                select(PolymarketSnapshot)
                .where(PolymarketSnapshot.fetched_at >= cutoff)
                .order_by(desc(PolymarketSnapshot.fetched_at))
                .limit(limit)
            )
        ).scalars().all()
    )
    # Dedupe by slug : keep only the most recent snapshot per market.
    seen_slugs: set[str] = set()
    rows = []
    for r in raw_rows:
        if r.slug in seen_slugs:
            continue
        seen_slugs.add(r.slug)
        rows.append(r)

    theme_hits: list[ThemeHit] = []
    asset_aggregate: dict[str, float] = {}

    for theme in _THEMES:
        matches: list[MarketHit] = []
        for r in rows:
            q = (r.question or "").lower()
            if not any(_matches_phrase(q, p) for p in theme.keyword_phrases):
                continue
            yes = (
                r.last_prices[0]
                if r.last_prices and len(r.last_prices) > 0
                else None
            )
            if yes is None:
                continue
            weight = (yes - 0.5) * 2.0  # in [-1, +1]
            matches.append(
                MarketHit(
                    slug=r.slug,
                    question=r.question[:140],
                    yes=round(yes, 3),
                    weight=round(weight, 3),
                )
            )
        if not matches:
            continue
        avg_yes = sum(m.yes for m in matches) / len(matches)
        # Per-asset impact = mean(weight) × theme.impact_per_asset[asset]
        mean_weight = sum(m.weight for m in matches) / len(matches)
        impacts: dict[str, float] = {}
        for asset, mag in theme.impact_per_asset.items():
            v = round(mag * mean_weight, 3)
            impacts[asset] = v
            asset_aggregate[asset] = asset_aggregate.get(asset, 0.0) + v
        # Sort by absolute weight, keep top 5
        matches.sort(key=lambda m: abs(m.weight), reverse=True)
        theme_hits.append(
            ThemeHit(
                theme_key=theme.key,
                label=theme.label,
                n_markets=len(matches),
                avg_yes=round(avg_yes, 3),
                markets=matches[:5],
                impact_per_asset=impacts,
            )
        )

    # Clamp aggregate to [-1, +1] per asset
    for k in list(asset_aggregate.keys()):
        asset_aggregate[k] = round(
            max(-1.0, min(1.0, asset_aggregate[k])), 3
        )

    # Sort themes by total impact magnitude
    theme_hits.sort(
        key=lambda t: sum(abs(v) for v in t.impact_per_asset.values()),
        reverse=True,
    )

    return ImpactReport(
        generated_at=datetime.now(timezone.utc),
        n_markets_scanned=len(rows),
        themes=theme_hits,
        asset_aggregate=asset_aggregate,
    )


def render_polymarket_impact_block(
    r: ImpactReport,
) -> tuple[str, list[str]]:
    """Markdown block for data_pool.py."""
    if not r.themes:
        return (
            f"## Polymarket impact ({r.n_markets_scanned} markets scanned)\n"
            f"- Aucun thème identifié dans les markets actuels.",
            [],
        )

    lines = [
        f"## Polymarket impact mapping ({r.n_markets_scanned} markets, {len(r.themes)} themes)"
    ]
    sources: list[str] = []
    for th in r.themes[:5]:
        lines.append(
            f"- **{th.label}** : n={th.n_markets} avg YES={th.avg_yes*100:.0f}%"
        )
        impacts = sorted(
            th.impact_per_asset.items(),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )[:5]
        impact_str = " · ".join(
            f"{a} {v:+.2f}" for a, v in impacts
        )
        lines.append(f"  · impacts : {impact_str}")
        for m in th.markets[:2]:
            lines.append(f"  · '{m.question[:70]}' YES={m.yes*100:.0f}%")
            sources.append(f"polymarket:{m.slug}")

    if r.asset_aggregate:
        lines.append("- Aggregate per asset (clamped ±1) :")
        agg_sorted = sorted(
            r.asset_aggregate.items(),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )
        for a, v in agg_sorted[:8]:
            sign = "+" if v >= 0 else ""
            lines.append(f"  · {a:<11s} {sign}{v:+.2f}")
    return "\n".join(lines), sources
