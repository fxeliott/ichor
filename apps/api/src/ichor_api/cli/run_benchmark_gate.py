"""run_benchmark_gate.py — Chantier A slice-2 (ADR-116).

The CLI that turns the pure-core benchmark gate (ADR-114) into a **real**
reproducible report: it joins historical session verdicts
(``session_card_audit``) with their realised NY-window outcomes and feeds them
to ``services.benchmark_gate`` (``evaluate`` / ``evaluate_walk_forward`` /
``format_report_markdown``).

Gate semantics (PLAN_DIRECTEUR §5 gate A, verbatim): the gate is that **the
report exists and is reproducible, NOT that Ichor wins.** This CLI fabricates
no win and surfaces thin-history / unreconciled-data honestly.

Realised-return source (design decision, ADR-116): the realised NY-window
open/close is read from the **already-reconciled** ``realized_open_session`` /
``realized_close_session`` columns on ``session_card_audit`` (written by
``cli/reconcile_outcomes.py`` from Polygon intraday bars over the card's timing
window). This is preferred over re-querying ``polygon_intraday`` here because
the reconciled snapshot is persisted permanently (immune to 1-min bar
retention), is the **same** realised outcome the Brier calibration already
uses, and removes all timezone/missing-bar handling from this slice. Rows whose
window is not yet reconciled (NULL realised prices) are skipped and counted —
never imputed.

Verdict source: ``bias_direction`` (post ``card_coherence``, i.e. the read Ichor
actually emitted) on the ``pre_ny`` card — the verdict that anticipates the NY
session Eliot trades. ``bias_direction`` is the DB enum ``long``/``short``/
``neutral``; it is mapped to the pure-core ``up``/``down``/``neutral``.

ADR-009 (Voie D): zero LLM, zero spend — pure DB read + arithmetic.
ADR-017: the report prose comes from ``format_report_markdown`` (regex-guarded);
this CLI adds only descriptive headers (no trade tokens).
ADR-022: ``conviction_pct`` is clamped to ``0..95`` before the pure-core
boundary (prod never exceeds 95, but the CLI defends the boundary).

Usage :
  python -m ichor_api.cli.run_benchmark_gate [--asset CODE] [--since YYYY-MM-DD]
      [--session-type pre_ny] [--cost-pct 0.0] [--dead-band-pct 0.0]
      [--train-size 20] [--test-size 5] [--step 5] [--output report.md]

A live run needs the production database (``ICHOR_API_DATABASE_URL``); the
pure-core (ADR-114) and every helper here are unit-tested without a DB.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_engine, get_sessionmaker
from ..models import SessionCardAudit
from ..services.benchmark_gate import (
    Direction,
    VerdictOutcomeSample,
    evaluate,
    evaluate_walk_forward,
    format_report_markdown,
)
from ..services.market_session import PARIS

# bias_direction (DB enum) -> pure-core Direction. The only mapping; kept here
# because neither the pure-core nor any existing helper carries it.
_BIAS_TO_DIRECTION: dict[str, Direction] = {
    "long": "up",
    "short": "down",
    "neutral": "neutral",
}
_CONVICTION_CAP = 95.0  # ADR-022 (mirror of CAP_95 * 100)
_DEFAULT_SESSION_TYPE = "pre_ny"


def bias_to_direction(bias_direction: str) -> Direction:
    """Map the DB ``long``/``short``/``neutral`` to the pure-core
    ``up``/``down``/``neutral``. Fail-closed on an unknown value (the DB CHECK
    guarantees the three, so an unknown is a data-integrity bug, not a verdict)."""
    try:
        return _BIAS_TO_DIRECTION[bias_direction]
    except KeyError as exc:
        raise ValueError(
            f"unknown bias_direction {bias_direction!r} (expected long/short/neutral)"
        ) from exc


def clamp_conviction(conviction_pct: float) -> float:
    """Clamp to the ADR-022 0..95 band before the pure-core boundary."""
    return min(max(conviction_pct, 0.0), _CONVICTION_CAP)


def realized_return_pct(open_px: float, close_px: float) -> float:
    """Signed NY-window return in percent: ``(close/open - 1) * 100``."""
    if open_px == 0.0:
        raise ValueError("realized_open_session is zero — cannot compute a return")
    return (close_px / open_px - 1.0) * 100.0


@dataclass(frozen=True, slots=True)
class VerdictRow:
    """A raw ``session_card_audit`` projection — decouples the DB read from the
    pure transform so the join logic is unit-testable without a database."""

    asset: str
    generated_at: datetime
    bias_direction: str
    conviction_pct: float
    realized_open_session: float | None
    realized_close_session: float | None


def _session_date(generated_at: datetime) -> date:
    """The Paris calendar date the verdict belongs to (a pre-NY card is
    generated the morning of its session, Paris time)."""
    return generated_at.astimezone(PARIS).date()


def rows_to_samples(
    rows: Iterable[VerdictRow],
) -> tuple[list[VerdictOutcomeSample], int]:
    """Pure transform: dedup to the latest card per ``(asset, session_date)``,
    drop rows whose NY window is not reconciled yet (NULL/zero realised prices),
    and build sorted :class:`VerdictOutcomeSample`s.

    Returns ``(samples, n_skipped_unreconciled)`` — the skip count is reported
    honestly rather than the rows being imputed.
    """
    latest: dict[tuple[str, date], VerdictRow] = {}
    for row in rows:
        key = (row.asset, _session_date(row.generated_at))
        current = latest.get(key)
        if current is None or row.generated_at > current.generated_at:
            latest[key] = row

    samples: list[VerdictOutcomeSample] = []
    skipped = 0
    for (asset, session_date), row in latest.items():
        open_px = row.realized_open_session
        close_px = row.realized_close_session
        if open_px is None or close_px is None or open_px == 0.0:
            skipped += 1
            continue
        samples.append(
            VerdictOutcomeSample(
                asset=asset,
                session_date=session_date,
                predicted_direction=bias_to_direction(row.bias_direction),
                conviction_pct=clamp_conviction(row.conviction_pct),
                realized_return_pct=realized_return_pct(open_px, close_px),
            )
        )
    samples.sort(key=lambda s: (s.asset, s.session_date))
    return samples, skipped


def render_report(
    samples: list[VerdictOutcomeSample],
    *,
    n_skipped: int,
    cost_pct: float,
    dead_band_pct: float,
    train_size: int,
    test_size: int,
    step: int,
) -> str:
    """Render the in-sample report plus the walk-forward OOS report (or an
    honest "insufficient history" note when no asset has enough sessions)."""
    in_sample = evaluate(samples, cost_pct=cost_pct, dead_band_pct=dead_band_pct)
    oos = evaluate_walk_forward(
        samples,
        train_size=train_size,
        test_size=test_size,
        step=step,
        cost_pct=cost_pct,
        dead_band_pct=dead_band_pct,
    )
    parts = [
        f"_Source : {len(samples)} verdict(s) `{_DEFAULT_SESSION_TYPE}` réconcilié(s)"
        + (f", {n_skipped} non réconcilié(s) ignoré(s)._" if n_skipped else "._"),
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


async def _load_verdict_rows(
    session: AsyncSession,
    *,
    session_type: str,
    asset_filter: str | None,
    since: datetime | None,
) -> list[VerdictRow]:
    stmt = select(
        SessionCardAudit.asset,
        SessionCardAudit.generated_at,
        SessionCardAudit.bias_direction,
        SessionCardAudit.conviction_pct,
        SessionCardAudit.realized_open_session,
        SessionCardAudit.realized_close_session,
    ).where(SessionCardAudit.session_type == session_type)
    if asset_filter is not None:
        stmt = stmt.where(SessionCardAudit.asset == asset_filter)
    if since is not None:
        stmt = stmt.where(SessionCardAudit.generated_at >= since)
    stmt = stmt.order_by(SessionCardAudit.asset, SessionCardAudit.generated_at)
    result = await session.execute(stmt)
    return [
        VerdictRow(
            asset=asset,
            generated_at=generated_at,
            bias_direction=bias_direction,
            conviction_pct=conviction_pct,
            realized_open_session=realized_open_session,
            realized_close_session=realized_close_session,
        )
        for (
            asset,
            generated_at,
            bias_direction,
            conviction_pct,
            realized_open_session,
            realized_close_session,
        ) in result.all()
    ]


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
        rows = await _load_verdict_rows(
            session,
            session_type=session_type,
            asset_filter=asset_filter,
            since=since,
        )
    samples, skipped = rows_to_samples(rows)
    if not samples:
        print(
            "Aucun verdict réconcilié sur la fenêtre demandée — rien à "
            "benchmarker. (Honnête : pas de données, pas de rapport fabriqué. "
            f"{skipped} verdict(s) en attente de réconciliation.)"
        )
        return 0
    report = render_report(
        samples,
        n_skipped=skipped,
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
            "of Ichor's session verdict vs passive/naive baselines, from "
            "reconciled session_card_audit history."
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
