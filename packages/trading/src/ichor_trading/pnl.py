"""P&L helpers — equity curve from trade audit log, unrealized PnL."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .types import Position, Trade


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    cash: float
    realized_cumulative: float
    n_trades_to_date: int


def equity_curve_from_trades(
    trades: Sequence[Trade], initial_cash: float
) -> list[EquityPoint]:
    """Reconstruct (cash, cumulative realized PnL) over time from a trade
    log. Useful for offline analysis + dashboard rendering.

    Cash impact per fill :
      buy  → cash -= qty * fill_price + fee
      sell → cash += qty * fill_price - fee
    """
    cash = initial_cash
    realized = 0.0
    out: list[EquityPoint] = []
    for i, t in enumerate(sorted(trades, key=lambda x: x.filled_at)):
        notional = t.quantity * t.fill_price
        if t.side == "buy":
            cash -= notional
        else:
            cash += notional
        cash -= t.fee_paid
        realized += t.realized_pnl_at_fill
        out.append(
            EquityPoint(
                timestamp=t.filled_at,
                cash=cash,
                realized_cumulative=realized,
                n_trades_to_date=i + 1,
            )
        )
    return out


def compute_unrealized_pnl(
    positions: dict[str, Position],
    marks: dict[str, float],
) -> float:
    """Mark-to-market unrealized PnL across all open positions."""
    total = 0.0
    for asset, pos in positions.items():
        if pos.is_flat():
            continue
        mark = marks.get(asset)
        if mark is None:
            continue
        total += pos.quantity * (mark - pos.avg_entry)
    return total
