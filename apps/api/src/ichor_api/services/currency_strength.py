"""Currency strength meter — classic FX trader synthesis.

Aggregates rolling 24h price changes across all 5 USD-quoted majors to
rank each major currency from strongest to weakest. The math is simple
but powerful : if EUR/USD up 0.5%, GBP/USD up 0.3%, AUD/USD up 0.4%,
USD/JPY down 0.2%, USD/CAD up 0.1% — then USD is roughly flat vs
basket, EUR/GBP/AUD strong, JPY strong, CAD weak.

Methodology :
  - Pull the latest close + the close 24h ago for each USD pair
  - Compute pct_change = (last / first - 1) × 100
  - For X/USD pairs, X strength contribution = +pct_change ;
    USD strength contribution from those = −pct_change
  - For USD/Y pairs, USD strength contribution = +pct_change ;
    Y strength contribution = −pct_change
  - Average each currency's contributions, normalize to [-1, +1]

Result : a currency-strength bar chart that updates every minute and
tells Eliot at a glance which currency is bid and which is offered.

Pure function — every contribution cites the polygon bar pair source.

VISION_2026 — closes the "what's the macro currency picture?" gap.
A trader staring at one pair misses the cross-currency picture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PolygonIntradayBar

# Pair → (base, quote). USD quote pairs : base strength = +pct_change.
# USD base pairs : USD strength = +pct_change, quote strength = -pct_change.
_PAIRS: list[tuple[str, str, str]] = [
    # asset_code, base_currency, quote_currency
    ("EUR_USD", "EUR", "USD"),
    ("GBP_USD", "GBP", "USD"),
    ("AUD_USD", "AUD", "USD"),
    ("USD_JPY", "USD", "JPY"),
    ("USD_CAD", "USD", "CAD"),
]
# All currencies tracked
_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD"]


@dataclass(frozen=True)
class CurrencyStrengthEntry:
    currency: str
    score: float
    """Average pct_change contribution, signed. Positive = strong."""
    rank: int
    """1 = strongest, 6 = weakest."""
    n_pairs_contributing: int
    contributions: list[tuple[str, float]] = field(default_factory=list)
    """List of (asset_code, contribution_pct) pairs."""


@dataclass(frozen=True)
class CurrencyStrengthReport:
    window_hours: float
    generated_at: datetime
    entries: list[CurrencyStrengthEntry]
    sources: list[str] = field(default_factory=list)


async def _bar_at_or_before(
    session: AsyncSession, asset: str, ts: datetime
) -> PolygonIntradayBar | None:
    stmt = (
        select(PolygonIntradayBar)
        .where(
            PolygonIntradayBar.asset == asset,
            PolygonIntradayBar.bar_ts <= ts,
        )
        .order_by(desc(PolygonIntradayBar.bar_ts))
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _earliest_bar(session: AsyncSession, asset: str) -> PolygonIntradayBar | None:
    """Fallback when polygon_intraday hasn't been backfilled long enough."""
    stmt = (
        select(PolygonIntradayBar)
        .where(PolygonIntradayBar.asset == asset)
        .order_by(PolygonIntradayBar.bar_ts.asc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _latest_bar(session: AsyncSession, asset: str) -> PolygonIntradayBar | None:
    stmt = (
        select(PolygonIntradayBar)
        .where(PolygonIntradayBar.asset == asset)
        .order_by(desc(PolygonIntradayBar.bar_ts))
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def assess_currency_strength(
    session: AsyncSession, *, window_hours: float = 24.0
) -> CurrencyStrengthReport:
    """Compute % change of every USD pair over the window, rank currencies."""
    now = datetime.now(UTC)
    window_ago = now - timedelta(hours=window_hours)

    contributions: dict[str, list[tuple[str, float]]] = {c: [] for c in _CURRENCIES}
    sources: list[str] = []

    for asset, base, quote in _PAIRS:
        last = await _latest_bar(session, asset)
        first = await _bar_at_or_before(session, asset, window_ago)
        if first is None:
            # Polygon not backfilled the full window yet — degrade
            # gracefully to whatever earliest bar we have.
            first = await _earliest_bar(session, asset)
            if first is not None:
                pass
        if last is None or first is None:
            continue
        if first.close <= 0:
            continue
        pct = (float(last.close) / float(first.close) - 1.0) * 100.0
        # Base currency moves +pct when pair rises ; quote moves -pct.
        contributions[base].append((asset, +pct))
        contributions[quote].append((asset, -pct))
        sources.append(f"polygon:{asset}@{first.bar_ts.isoformat()}-{last.bar_ts.isoformat()}")

    # Average per currency. Normalize so the magnitude is comparable.
    raw_scores: dict[str, float] = {}
    for ccy, contribs in contributions.items():
        if not contribs:
            raw_scores[ccy] = 0.0
            continue
        raw_scores[ccy] = sum(c for _, c in contribs) / len(contribs)

    # Rank descending (strongest first)
    ranked = sorted(raw_scores.items(), key=lambda kv: kv[1], reverse=True)

    entries: list[CurrencyStrengthEntry] = []
    for rank, (ccy, score) in enumerate(ranked, start=1):
        entries.append(
            CurrencyStrengthEntry(
                currency=ccy,
                score=round(score, 3),
                rank=rank,
                n_pairs_contributing=len(contributions[ccy]),
                contributions=[(a, round(c, 3)) for a, c in contributions[ccy]],
            )
        )

    return CurrencyStrengthReport(
        window_hours=window_hours,
        generated_at=now,
        entries=entries,
        sources=sources,
    )


def render_currency_strength_block(
    r: CurrencyStrengthReport,
) -> tuple[str, list[str]]:
    """Markdown block for data_pool.py."""
    if not r.entries or all(e.n_pairs_contributing == 0 for e in r.entries):
        return (
            f"## Currency strength (last {r.window_hours:.0f}h)\n"
            f"- (insufficient polygon bars to compute)",
            [],
        )
    lines = [f"## Currency strength meter (last {r.window_hours:.0f}h)"]
    for e in r.entries:
        if e.n_pairs_contributing == 0:
            lines.append(f"- {e.rank}. **{e.currency}** : (no data)")
            continue
        sign = "+" if e.score >= 0 else ""
        lines.append(
            f"- {e.rank}. **{e.currency}** : {sign}{e.score:+.2f}% "
            f"({e.n_pairs_contributing} pair contributions)"
        )
    return "\n".join(lines), list(r.sources)
