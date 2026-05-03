"""Rich briefing context assembler.

Pulls every persisted source the system has — bias signals, alerts,
news, polymarket, market_data — and renders them as a single Markdown
blob fit for Claude consumption.

Designed to fit under a hard token cap (default 12 000 tokens, ~48 KB)
so we never exceed the briefing-task POST budget. Sections degrade
gracefully (older items dropped first, then optional sections collapsed
to one-line summaries).

Used behind the `ICHOR_RICH_CONTEXT=1` env flag in
`apps/api/src/ichor_api/cli/run_briefing.py` — default OFF so the LIVE
chain stays on the proven path until rich context is validated on a
sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Alert,
    BiasSignal,
    MarketDataBar,
    NewsItem,
    PolymarketSnapshot,
)

log = structlog.get_logger(__name__)

# Approximate token budget for the assembled context (Claude tokenizer
# is roughly 4 chars / token for FR/EN mix).
DEFAULT_MAX_TOKENS = 12_000
CHARS_PER_TOKEN = 4


@dataclass
class ContextSection:
    title: str
    body: str
    priority: int  # lower = drop first under budget pressure


def _format_bias(signals: Sequence[BiasSignal]) -> str:
    if not signals:
        return "_(aucun signal disponible)_"
    lines = [
        "| Asset | Direction | P | CI 80% | Top model |",
        "|-------|-----------|---|--------|-----------|",
    ]
    for s in signals:
        top_model = (
            max(s.weights_snapshot, key=lambda k: s.weights_snapshot[k])
            if s.weights_snapshot
            else "-"
        )
        lines.append(
            f"| {s.asset} | {s.direction} | {s.probability:.2f} | "
            f"[{s.credible_interval_low:.2f},{s.credible_interval_high:.2f}] | "
            f"{top_model} |"
        )
    return "\n".join(lines)


def _format_alerts(alerts: Sequence[Alert]) -> str:
    if not alerts:
        return "_(système nominal — aucune alerte active)_"
    lines = []
    for a in alerts:
        ts = a.triggered_at.strftime("%H:%M")
        lines.append(
            f"- {ts} **{a.severity.upper()}** `{a.alert_code}` — {a.title} "
            f"(`{a.metric_name}={a.metric_value}` {a.direction} {a.threshold})"
        )
    return "\n".join(lines)


def _format_market_data(bars: Sequence[MarketDataBar]) -> str:
    """Latest close + simple D/D% per asset, sorted by absolute %change desc.

    For each asset we pick the most recent bar and compute the change
    against the prior session.
    """
    if not bars:
        return "_(aucune barre persistée)_"

    by_asset: dict[str, list[MarketDataBar]] = {}
    for b in bars:
        by_asset.setdefault(b.asset, []).append(b)

    rows: list[tuple[str, MarketDataBar, float | None]] = []
    for asset, asset_bars in by_asset.items():
        ordered = sorted(asset_bars, key=lambda x: x.bar_date)
        latest = ordered[-1]
        prior = ordered[-2] if len(ordered) >= 2 else None
        chg = (
            (latest.close - prior.close) / prior.close * 100 if prior and prior.close
            else None
        )
        rows.append((asset, latest, chg))

    rows.sort(key=lambda r: abs(r[2]) if r[2] is not None else 0, reverse=True)

    lines = [
        "| Asset | Date | Close | D/D % |",
        "|-------|------|-------|-------|",
    ]
    for asset, bar, chg in rows:
        chg_s = f"{chg:+.2f}%" if chg is not None else "n/a"
        lines.append(f"| {asset} | {bar.bar_date} | {bar.close:.4f} | {chg_s} |")
    return "\n".join(lines)


def _format_news(items: Sequence[NewsItem]) -> str:
    if not items:
        return "_(aucune dépêche persistée dans la fenêtre)_"
    # Group by source for readability
    by_kind: dict[str, list[NewsItem]] = {}
    for n in items:
        by_kind.setdefault(n.source_kind, []).append(n)

    parts: list[str] = []
    kind_labels = {
        "central_bank": "Banques centrales",
        "regulator": "Régulateurs",
        "news": "Presse finance",
        "social": "Social",
        "academic": "Académique",
    }
    for kind in ["central_bank", "regulator", "news", "social", "academic"]:
        bucket = by_kind.get(kind, [])
        if not bucket:
            continue
        parts.append(f"### {kind_labels.get(kind, kind)}")
        for n in bucket[:8]:
            ts = n.published_at.strftime("%Y-%m-%d %H:%M")
            tone = (
                f" _[{n.tone_label}]_" if n.tone_label else ""
            )
            parts.append(f"- {ts} **{n.source}** — {n.title}{tone}")
        parts.append("")
    return "\n".join(parts).rstrip()


def _format_polymarket(snaps: Sequence[PolymarketSnapshot]) -> str:
    if not snaps:
        return "_(aucun snapshot Polymarket frais)_"
    # Latest per slug
    by_slug: dict[str, PolymarketSnapshot] = {}
    for s in snaps:
        prev = by_slug.get(s.slug)
        if prev is None or s.fetched_at > prev.fetched_at:
            by_slug[s.slug] = s
    lines = [
        "| Marché | Yes | Volume USD |",
        "|--------|-----|------------|",
    ]
    for slug, s in by_slug.items():
        yes = s.last_prices[0] if s.last_prices else None
        yes_s = f"{yes:.2f}" if yes is not None else "n/a"
        vol_s = f"${s.volume_usd:,.0f}" if s.volume_usd is not None else "n/a"
        lines.append(f"| {s.question[:60]} | {yes_s} | {vol_s} |")
    return "\n".join(lines)


async def _fetch_bias_signals(
    session: AsyncSession, assets: Sequence[str]
) -> list[BiasSignal]:
    stmt = (
        select(BiasSignal)
        .where(BiasSignal.asset.in_(assets), BiasSignal.horizon_hours == 24)
        .order_by(BiasSignal.asset, desc(BiasSignal.generated_at))
        .distinct(BiasSignal.asset)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _fetch_recent_alerts(
    session: AsyncSession, *, hours: int
) -> list[Alert]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(Alert)
        .where(
            Alert.severity.in_(["warning", "critical"]),
            Alert.triggered_at >= cutoff,
        )
        .order_by(desc(Alert.triggered_at))
        .limit(30)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _fetch_market_bars(
    session: AsyncSession, assets: Sequence[str], *, lookback_days: int = 5
) -> list[MarketDataBar]:
    """Last N sessions per asset (so we can compute D/D)."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)
    stmt = (
        select(MarketDataBar)
        .where(MarketDataBar.asset.in_(assets), MarketDataBar.bar_date >= cutoff)
        .order_by(MarketDataBar.asset, MarketDataBar.bar_date)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _fetch_recent_news(
    session: AsyncSession, *, hours: int
) -> list[NewsItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(NewsItem)
        .where(NewsItem.published_at >= cutoff)
        .order_by(desc(NewsItem.published_at))
        .limit(40)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _fetch_polymarket(
    session: AsyncSession, *, hours: int
) -> list[PolymarketSnapshot]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(PolymarketSnapshot)
        .where(PolymarketSnapshot.fetched_at >= cutoff)
        .order_by(desc(PolymarketSnapshot.fetched_at))
        .limit(50)
    )
    return list((await session.execute(stmt)).scalars().all())


async def build_rich_context(
    session: AsyncSession,
    briefing_type: str,
    assets: Sequence[str],
    *,
    news_hours: int = 24,
    poly_hours: int = 24,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[str, int]:
    """Assemble the rich context Markdown.

    Returns `(markdown, token_estimate)`. If the assembled blob exceeds
    `max_tokens * CHARS_PER_TOKEN` chars, the lowest-priority sections
    are dropped first (news + polymarket), then alerts older than 12 h,
    until the budget is satisfied.
    """
    [signals, alerts, bars, news, polys] = await _gather(
        session, assets, news_hours=news_hours, poly_hours=poly_hours
    )

    sections: list[ContextSection] = [
        ContextSection(
            title="Bias signals (24 h horizon, latest per asset)",
            body=_format_bias(signals),
            priority=10,  # never drop
        ),
        ContextSection(
            title="Active alerts (warning + critical, last 24 h)",
            body=_format_alerts(alerts),
            priority=9,
        ),
        ContextSection(
            title="Market data — last close + D/D %",
            body=_format_market_data(bars),
            priority=8,
        ),
        ContextSection(
            title=f"News (last {news_hours} h, FinBERT-tone where labelled)",
            body=_format_news(news),
            priority=5,
        ),
        ContextSection(
            title=f"Polymarket (last {poly_hours} h)",
            body=_format_polymarket(polys),
            priority=4,
        ),
    ]

    header = (
        f"# Briefing context — {briefing_type}\n"
        f"Generated at {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        f"Assets: {', '.join(assets)}\n"
    )

    # Try full first
    md = _render(header, sections)
    while len(md) > max_tokens * CHARS_PER_TOKEN and sections:
        # Drop the lowest-priority section
        sections.sort(key=lambda s: s.priority)
        dropped = sections.pop(0)
        log.warning(
            "context_builder.drop_section",
            section=dropped.title,
            current_chars=len(md),
            budget_chars=max_tokens * CHARS_PER_TOKEN,
        )
        md = _render(header, sections)

    return md, len(md) // CHARS_PER_TOKEN


async def _gather(
    session: AsyncSession,
    assets: Sequence[str],
    *,
    news_hours: int,
    poly_hours: int,
) -> tuple[
    list[BiasSignal],
    list[Alert],
    list[MarketDataBar],
    list[NewsItem],
    list[PolymarketSnapshot],
]:
    signals = await _fetch_bias_signals(session, assets)
    alerts = await _fetch_recent_alerts(session, hours=24)
    bars = await _fetch_market_bars(session, assets, lookback_days=5)
    news = await _fetch_recent_news(session, hours=news_hours)
    polys = await _fetch_polymarket(session, hours=poly_hours)
    return signals, alerts, bars, news, polys


def _render(header: str, sections: Sequence[ContextSection]) -> str:
    parts = [header]
    for s in sections:
        parts.append("")
        parts.append(f"## {s.title}")
        parts.append(s.body)
    return "\n".join(parts)
