"""Historical analogues via DTW on Stooq daily bars.

Phase 2 fix for SPEC.md §2.2 #11 (`market_data` Stooq daily peuplé mais
inexploité par le brain). Wraps `packages/ml/.../analogues/dtw.py` and
exposes a data_pool block + a structured result.

Approach: for each query asset we compare its last N daily returns to
every historical N-day window of the same asset (and optionally cross-
asset windows). The K closest windows by DTW distance are returned with
their forward outcome (return over the next M days), as a "what
happened next" prior for Pass 1 / Pass 3.

This is **not** a price predictor (ADR-017 forbids those). It surfaces
historical pattern matches for the LLM to incorporate as context.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import MarketDataBar


@dataclass(frozen=True)
class Analogue:
    asset: str
    window_start: datetime
    window_end: datetime
    distance: float
    forward_return_pct: float | None  # pct over `forward_days` after window end


def _dtw_distance(a: list[float], b: list[float]) -> float:
    """Classic DTW with O(n*m) time, O(min(n,m)) space.

    We keep this inline (no scipy/dtaidistance) to avoid a new heavy dep
    on the API; the ML package owns the optimized path. For window
    lengths 20-60 the perf cost is fine even in pure Python.

    Note on the (0,0) initial condition: `prev[0] = 0` introduces a
    constant additive bias on every cumulative cost. The bias is
    identical across all candidate windows of the same length, so the
    *ranking* of candidates is preserved — which is all
    `find_analogues` needs (top-K cheapest).
    """
    if not a or not b:
        return float("inf")
    n, m = len(a), len(b)
    prev = [float("inf")] * (m + 1)
    prev[0] = 0.0
    for i in range(1, n + 1):
        curr = [float("inf")] * (m + 1)
        for j in range(1, m + 1):
            cost = abs(a[i - 1] - b[j - 1])
            curr[j] = cost + min(prev[j], curr[j - 1], prev[j - 1])
        prev = curr
    return prev[m]


def _percent_returns(closes: list[float]) -> list[float]:
    if len(closes) < 2:
        return []
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1] * 100.0
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]


async def find_analogues(
    session: AsyncSession,
    asset: str,
    *,
    window_days: int = 20,
    forward_days: int = 5,
    history_years: int = 10,
    top_k: int = 3,
) -> list[Analogue]:
    """Find the top-K historical windows that best match the most recent
    `window_days` of `asset` daily returns.

    Lookback is bounded by `history_years` to keep memory manageable. We
    operate on percent returns (not raw prices) so the matcher is
    scale-invariant.
    """
    now = datetime.now(UTC)
    earliest = now - timedelta(days=history_years * 365 + 30)

    rows = (
        (
            await session.execute(
                select(MarketDataBar)
                .where(
                    MarketDataBar.asset == asset,
                    MarketDataBar.bar_date >= earliest.date(),
                )
                .order_by(MarketDataBar.bar_date.asc())
            )
        )
        .scalars()
        .all()
    )

    if len(rows) < window_days * 2:
        return []  # not enough history

    closes = [float(r.close) for r in rows]
    times = [r.bar_date for r in rows]
    rets = _percent_returns(closes)
    if len(rets) < window_days * 2:
        return []

    # Most recent N returns are the query.
    query = rets[-window_days:]
    candidates: list[tuple[float, int]] = []  # (distance, end_index_in_rets)
    # Slide windows over historical part, leaving:
    #   - `forward_days + 1` cells after the window for the forward outcome lookup
    #   - `window_days` margin from the tail so the candidate window does NOT
    #     overlap the trailing query window (anti-leakage).
    upper_bound = len(rets) - forward_days - window_days
    for end_idx in range(window_days, max(window_days, upper_bound)):
        window = rets[end_idx - window_days : end_idx]
        d = _dtw_distance(query, window)
        candidates.append((d, end_idx))

    candidates.sort(key=lambda t: t[0])
    out: list[Analogue] = []
    for d, end_idx in candidates[:top_k]:
        # rets[i] derives from closes[i]→closes[i+1]; map back to closes
        # index range.
        # `times` is aligned with `closes`; `rets` is len(closes) - 1.
        # window covers closes[end_idx - window_days .. end_idx]
        ws = times[end_idx - window_days]
        we = times[end_idx]
        # forward return = (close[end+forward] / close[end]) - 1
        forward_pct: float | None
        if end_idx + forward_days < len(closes) and closes[end_idx] > 0:
            forward_pct = (
                (closes[end_idx + forward_days] - closes[end_idx]) / closes[end_idx] * 100.0
            )
        else:
            forward_pct = None
        out.append(
            Analogue(
                asset=asset,
                window_start=ws,
                window_end=we,
                distance=round(d, 4),
                forward_return_pct=(round(forward_pct, 3) if forward_pct is not None else None),
            )
        )
    return out


async def render_analogues_block(
    session: AsyncSession,
    asset: str,
    *,
    window_days: int = 20,
    forward_days: int = 5,
    top_k: int = 3,
) -> tuple[str, list[str]]:
    analogues = await find_analogues(
        session,
        asset,
        window_days=window_days,
        forward_days=forward_days,
        top_k=top_k,
    )
    if not analogues:
        return (
            f"## Historical analogues ({asset}, DTW {window_days}d)\n"
            "- (insufficient daily history — Stooq lookup empty or too short)",
            [],
        )
    lines = [
        f"## Historical analogues ({asset}, DTW window={window_days}d, forward={forward_days}d)"
    ]
    for a in analogues:
        fwd = (
            f"+{a.forward_return_pct:.2f}%"
            if (a.forward_return_pct or 0) >= 0
            else f"{a.forward_return_pct:.2f}%"
        )
        lines.append(
            f"- {a.window_start:%Y-%m-%d} → {a.window_end:%Y-%m-%d} · "
            f"DTW {a.distance:.2f} · "
            f"forward {forward_days}d outcome: {fwd if a.forward_return_pct is not None else 'n/a'}"
        )
    return "\n".join(lines), [f"market_data:{asset}@stooq_daily"]
