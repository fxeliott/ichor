"""Risk engine configuration.

All bounds are HARD bounds — sizing never exceeds these no matter what
the upstream model thinks. ADR-015 documents the choice of defaults.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """Conservative defaults — paper trading.

    Real-money escalation MUST tighten these (smaller Kelly cap,
    tighter daily DD), per ADR-016.
    """

    # ---------- Sizing ----------
    kelly_fraction_cap: float = 0.10
    """Per-trade Kelly fraction cap. Hard maximum on (sized notional /
    equity). Default 10 % — moderate sizing for paper backtests."""

    full_kelly_multiplier: float = 0.25
    """We compute full Kelly from (p, win/loss) but only stake
    `full_kelly_multiplier * full_kelly` (Kelly criterion is famously
    too aggressive in practice ; quarter-Kelly is the industry standard)."""

    min_position_size: float = 0.0
    """Below this absolute size, treat as no-trade. Avoids dust trades."""

    # ---------- Stops ----------
    per_trade_stop_pct: float = 0.02
    """Per-position max loss as fraction of entry notional. 2 % default."""

    daily_drawdown_stop_pct: float = 0.05
    """Halt new orders when realized daily DD exceeds 5 %."""

    # ---------- Trade frequency ----------
    max_trades_per_day: int = 50
    """Refuse new orders past this count per UTC day. Default 50 — well
    above what daily-bar models can plausibly need."""

    # ---------- Kill switch ----------
    require_kill_switch_check: bool = True
    """When True, RiskEngine refuses to evaluate orders if KillSwitch is
    not provided. Set False ONLY for unit tests that don't need it."""
