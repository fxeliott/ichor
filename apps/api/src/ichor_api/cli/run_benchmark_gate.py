"""run_benchmark_gate.py — Chantier A slice-2 (ADR-116).

The CLI that turns the pure-core benchmark gate (ADR-114) into a **real**
reproducible report: it scores, over historical sessions, the **apex
``SessionVerdict``** Ichor actually surfaced to the user against passive and
naive baselines, on Eliot's own NY trading window.

Gate semantics (PLAN_DIRECTEUR §5 gate A, verbatim): the gate is that **the
report exists and is reproducible, NOT that Ichor wins.** This CLI fabricates
no win and surfaces thin-history / missing-data honestly.

Two faithfulness decisions (ADR-116), both fixing a "benchmark that lies by
construction" trap caught by adversarial review:

1. **Verdict = the apex direction + conviction the user sees**, NOT the per-card
   ``bias_direction`` column. The apex `/v1/verdict` derives direction from the
   7 Pass-6 scenario buckets fused with the synthesis snapshots frozen on the
   card (ADR-106 D2 + S04). This CLI reproduces that EXACT derivation per
   historical card by reusing the canonical
   ``session_verdict_builder._extract_synthesis_primitives`` +
   ``_derive_direction_and_conviction`` (so the benchmark cannot drift from the
   verdict). Malformed/dormant scenarios → ``neutral``/0 (the builder fallback).

2. **Realised return = the exact NY window Eliot trades** (14:00→20:00 Paris,
   DST-correct), recomputed from ``polygon_intraday`` 1-min bars — NOT the
   ``reconcile_outcomes`` snapshot whose window is ``[generated_at,
   timing_window_end OR generated_at+8h]`` (≈13:30→21:30 for a pre-NY card, a
   different window than the one the report names). ``realized_return_pct =
   (close/open − 1) × 100`` over the bars in [14:00, 20:00) Paris.

ADR-009 (Voie D): zero LLM, zero spend — DB read + arithmetic.
ADR-017: report prose comes from ``format_report_markdown`` (regex-guarded);
this CLI adds only descriptive headers (no trade tokens).
ADR-022: conviction is the 0..95 apex value (clamped defensively).

Usage :
  python -m ichor_api.cli.run_benchmark_gate [--asset CODE] [--since YYYY-MM-DD]
      [--session-type pre_ny] [--cost-pct 0.0] [--dead-band-pct 0.0]
      [--train-size 20] [--test-size 5] [--step 5] [--output report.md]

A live run needs the production database (``ICHOR_API_DATABASE_URL``); the
pure-core (ADR-114) and every pure helper here are unit-tested without a DB.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_engine, get_sessionmaker
from ..models import PolygonIntradayBar, SessionCardAudit
from ..services.benchmark_gate import (
    Direction,
    VerdictOutcomeSample,
    evaluate,
    evaluate_walk_forward,
    format_report_markdown,
)
from ..services.market_session import PARIS

# Canonical apex-verdict derivation — reused (not re-implemented) so the
# benchmark scores BYTE-IDENTICALLY what `/v1/verdict` surfaces to the user.
# These are module-private but are the single source of truth for the
# verdict; importing them keeps the benchmark from silently drifting from the
# apex it claims to measure.
from ..services.session_verdict_builder import (  # noqa: PLC2701
    _derive_direction_and_conviction,
    _extract_synthesis_primitives,
)

# Eliot's NY trading window (verbatim r161 directive): enters 14h–16h Paris,
# cuts at 20h. The realised move benchmarked = open→close of [14:00, 20:00) Paris.
_NY_WINDOW_OPEN = time(14, 0)
_NY_WINDOW_CLOSE = time(20, 0)
# Min 1-min bars in the 6h window for an honest open/close (mirror of
# london_session._MIN_BARS). A short window (e.g. SPY RTH opening late) → skip.
_MIN_BARS = 30
_CONVICTION_CAP = 95.0  # ADR-022
_DEFAULT_SESSION_TYPE = "pre_ny"


def clamp_conviction(conviction_pct: float) -> float:
    """Defensive ADR-022 clamp (the apex value is already 0..95)."""
    return min(max(conviction_pct, 0.0), _CONVICTION_CAP)


def _session_date(generated_at: datetime) -> date:
    """The Paris calendar date the verdict belongs to (a pre-NY card is
    generated the morning of its session, Paris time)."""
    return generated_at.astimezone(PARIS).date()


def ny_window_utc(session_date: date) -> tuple[datetime, datetime]:
    """UTC bounds of Eliot's NY window (14:00–20:00 Paris) for ``session_date``.
    DST-correct via ZoneInfo (Europe/Paris)."""
    start = datetime.combine(session_date, _NY_WINDOW_OPEN, tzinfo=PARIS).astimezone(UTC)
    end = datetime.combine(session_date, _NY_WINDOW_CLOSE, tzinfo=PARIS).astimezone(UTC)
    return start, end


@dataclass(frozen=True, slots=True)
class _Bar:
    ts: datetime
    open: float
    close: float


def window_return_pct(bars: Sequence[_Bar]) -> float | None:
    """Signed open→close return in percent over the window's bars (ascending),
    or ``None`` if fewer than ``_MIN_BARS`` or a non-positive open (honest
    absence rather than a fabricated number)."""
    if len(bars) < _MIN_BARS:
        return None
    open_px = bars[0].open
    close_px = bars[-1].close
    if open_px <= 0.0:
        return None
    return (close_px / open_px - 1.0) * 100.0


def card_verdict(card: SessionCardAudit) -> tuple[Direction, float]:
    """Reproduce the apex ``SessionVerdict`` (direction + conviction) the user
    sees — bucket-derived via the canonical conviction fusion with the synthesis
    snapshots frozen on the card. Malformed/dormant scenarios → ``neutral``/0
    (mirror of the ``build_session_verdict`` fallback guard)."""
    scenarios = list(card.scenarios or [])
    if len(scenarios) != 7 or not all(
        isinstance(s, dict) and "label" in s and "p" in s for s in scenarios
    ):
        return "neutral", 0.0
    confluence_lean, theme_present, dollar_consensus, dollar_strength = (
        _extract_synthesis_primitives(card)
    )
    direction, conviction_pct, _rationale = _derive_direction_and_conviction(
        scenarios,
        asset=card.asset,
        confluence_lean=confluence_lean,
        theme_present=theme_present,
        dollar_consensus=dollar_consensus,
        dollar_strength=dollar_strength,
    )
    return direction, clamp_conviction(conviction_pct)


def dedup_latest_per_session(cards: Sequence[SessionCardAudit]) -> list[SessionCardAudit]:
    """Keep the latest-generated card per ``(asset, session_date)`` — one verdict
    per asset per NY session."""
    latest: dict[tuple[str, date], SessionCardAudit] = {}
    for card in cards:
        key = (card.asset, _session_date(card.generated_at))
        current = latest.get(key)
        if current is None or card.generated_at > current.generated_at:
            latest[key] = card
    return list(latest.values())


def render_report(
    samples: list[VerdictOutcomeSample],
    *,
    n_cards: int,
    n_skipped_no_window: int,
    cost_pct: float,
    dead_band_pct: float,
    train_size: int,
    test_size: int,
    step: int,
) -> str:
    """Render the in-sample + walk-forward OOS reports (or an honest
    "insufficient history" note when no asset has enough sessions)."""
    in_sample = evaluate(samples, cost_pct=cost_pct, dead_band_pct=dead_band_pct)
    oos = evaluate_walk_forward(
        samples,
        train_size=train_size,
        test_size=test_size,
        step=step,
        cost_pct=cost_pct,
        dead_band_pct=dead_band_pct,
    )
    skip_note = (
        f", {n_skipped_no_window} sans fenêtre NY 14h-20h exploitable (barres manquantes) ignoré(s)"
        if n_skipped_no_window
        else ""
    )
    parts = [
        f"_Source : {len(samples)} verdict(s) apex `{_DEFAULT_SESSION_TYPE}` sur "
        f"{n_cards} séance(s){skip_note}. Verdict = direction/conviction apex "
        f"(7 buckets fusionnés) ; rendement = open→close 14h-20h Paris._",
        "",
        "## In-sample (diagnostic)",
        format_report_markdown(in_sample),
        "",
        "## Walk-forward out-of-sample",
    ]
    if oos is None:
        parts.append(
            f"_Historique insuffisant pour un split walk-forward "
            f"(train={train_size} + test={test_size}) — rapport in-sample seul. "
            f"Pas d'edge OOS fabriqué sur une fenêtre trop courte (ADR-114)._"
        )
    else:
        parts.append(format_report_markdown(oos))
    return "\n".join(parts)


def _parse_since(value: str) -> datetime:
    """``YYYY-MM-DD`` → tz-aware UTC lower bound (Paris midnight of that date)."""
    d = date.fromisoformat(value)
    return datetime.combine(d, time.min, tzinfo=PARIS).astimezone(UTC)


async def _load_cards(
    session: AsyncSession,
    *,
    session_type: str,
    asset_filter: str | None,
    since: datetime | None,
) -> list[SessionCardAudit]:
    stmt = select(SessionCardAudit).where(SessionCardAudit.session_type == session_type)
    if asset_filter is not None:
        stmt = stmt.where(SessionCardAudit.asset == asset_filter)
    if since is not None:
        stmt = stmt.where(SessionCardAudit.generated_at >= since)
    stmt = stmt.order_by(SessionCardAudit.asset, SessionCardAudit.generated_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _load_window_bars(
    session: AsyncSession, *, asset: str, start_utc: datetime, end_utc: datetime
) -> list[_Bar]:
    rows = (
        await session.execute(
            select(
                PolygonIntradayBar.bar_ts,
                PolygonIntradayBar.open,
                PolygonIntradayBar.close,
            )
            .where(PolygonIntradayBar.asset == asset)
            .where(PolygonIntradayBar.bar_ts >= start_utc)
            .where(PolygonIntradayBar.bar_ts < end_utc)
            .order_by(PolygonIntradayBar.bar_ts.asc())
        )
    ).all()
    return [
        _Bar(ts=ts, open=float(open_px), close=float(close_px))
        for (ts, open_px, close_px) in rows
        if open_px is not None and close_px is not None
    ]


async def _build_samples(
    session: AsyncSession, cards: Sequence[SessionCardAudit]
) -> tuple[list[VerdictOutcomeSample], int, int]:
    """Join each deduped card's apex verdict with its realised NY-window return.
    Returns ``(samples, n_cards, n_skipped_no_window)`` — skips (no usable bar
    window) are counted, never imputed."""
    deduped = dedup_latest_per_session(cards)
    samples: list[VerdictOutcomeSample] = []
    skipped_no_window = 0
    for card in deduped:
        session_date = _session_date(card.generated_at)
        start_utc, end_utc = ny_window_utc(session_date)
        bars = await _load_window_bars(
            session, asset=card.asset, start_utc=start_utc, end_utc=end_utc
        )
        realized = window_return_pct(bars)
        if realized is None:
            skipped_no_window += 1
            continue
        direction, conviction_pct = card_verdict(card)
        samples.append(
            VerdictOutcomeSample(
                asset=card.asset,
                session_date=session_date,
                predicted_direction=direction,
                conviction_pct=conviction_pct,
                realized_return_pct=realized,
            )
        )
    samples.sort(key=lambda s: (s.asset, s.session_date))
    return samples, len(deduped), skipped_no_window


async def _run(
    *,
    session_type: str,
    asset_filter: str | None,
    since: datetime | None,
    cost_pct: float,
    dead_band_pct: float,
    train_size: int,
    test_size: int,
    step: int,
    output: str | None,
) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        cards = await _load_cards(
            session,
            session_type=session_type,
            asset_filter=asset_filter,
            since=since,
        )
        samples, n_cards, skipped_no_window = await _build_samples(session, cards)
    if not samples:
        print(
            "Aucun verdict avec fenêtre NY 14h-20h exploitable sur la période "
            f"demandée ({n_cards} séance(s), {skipped_no_window} sans barres). "
            "Honnête : pas de données, pas de rapport fabriqué."
        )
        return 0
    report = render_report(
        samples,
        n_cards=n_cards,
        n_skipped_no_window=skipped_no_window,
        cost_pct=cost_pct,
        dead_band_pct=dead_band_pct,
        train_size=train_size,
        test_size=test_size,
        step=step,
    )
    print(report)
    if output is not None:
        # One-shot CLI write at the very end of the run — no concurrent event
        # loop work to block, so the ASYNC240 (no pathlib in async) concern
        # does not apply here.
        Path(output).write_text(report + "\n", encoding="utf-8")  # noqa: ASYNC240
        print(f"\n[écrit dans {output}]")
    return 0


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_benchmark_gate",
        description=(
            "Chantier A slice-2 (ADR-116) — reproducible out-of-sample benchmark "
            "of Ichor's apex session verdict vs passive/naive baselines, over the "
            "real NY 14h-20h window from session_card_audit + polygon_intraday."
        ),
    )
    parser.add_argument("--asset", default=None, help="restrict to one asset code")
    parser.add_argument(
        "--session-type",
        default=_DEFAULT_SESSION_TYPE,
        help="card session_type to benchmark (default: pre_ny — anticipates NY)",
    )
    parser.add_argument(
        "--since",
        type=_parse_since,
        default=None,
        help="lower bound on generated_at (ISO date YYYY-MM-DD, Paris)",
    )
    parser.add_argument("--cost-pct", type=float, default=0.0, help="round-trip cost %")
    parser.add_argument("--dead-band-pct", type=float, default=0.0, help="neutral dead-band %")
    parser.add_argument("--train-size", type=int, default=20, help="walk-forward train window")
    parser.add_argument("--test-size", type=int, default=5, help="walk-forward test window")
    parser.add_argument("--step", type=int, default=5, help="walk-forward roll step")
    parser.add_argument("--output", default=None, help="also write the markdown report here")
    args = parser.parse_args(argv)
    try:
        return await _run(
            session_type=args.session_type,
            asset_filter=args.asset,
            since=args.since,
            cost_pct=args.cost_pct,
            dead_band_pct=args.dead_band_pct,
            train_size=args.train_size,
            test_size=args.test_size,
            step=args.step,
            output=args.output,
        )
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
