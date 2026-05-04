"""SQLAlchemy ORM models. Mirrors the Postgres schema.

Naming: tables snake_case plural, columns snake_case, FKs `<table>_id`.
All timestamps are TIMESTAMPTZ (UTC).

Note : `BacktestRun` was archived in commit ADR-017 reset (2026-05-03).
See `archive/2026-05-03-pre-reset/backtest_run_model.py`.

Phase 1 Living Macro Entity tables (migration 0005, 2026-05-03) :
FredObservation, GdeltEvent, GprObservation, CotPosition, CbSpeech,
KalshiMarket, ManifoldMarket, SessionCardAudit.
"""

from .base import Base
from .briefing import Briefing
from .alert import Alert
from .prediction import Prediction
from .bias_signal import BiasSignal
from .news_item import NewsItem
from .polymarket_snapshot import PolymarketSnapshot
from .market_data import MarketDataBar

# Phase 1 Living Macro Entity collectors
from .fred_observation import FredObservation
from .gdelt_event import GdeltEvent
from .gpr_observation import GprObservation
from .cot_position import CotPosition
from .cb_speech import CbSpeech
from .kalshi_market import KalshiMarket
from .manifold_market import ManifoldMarket
from .session_card_audit import SessionCardAudit
from .polygon_intraday import PolygonIntradayBar
from .confluence_history import ConfluenceHistory

__all__ = [
    "Base",
    "Briefing",
    "Alert",
    "Prediction",
    "BiasSignal",
    "NewsItem",
    "PolymarketSnapshot",
    "MarketDataBar",
    # Phase 1
    "FredObservation",
    "GdeltEvent",
    "GprObservation",
    "CotPosition",
    "CbSpeech",
    "KalshiMarket",
    "ManifoldMarket",
    "SessionCardAudit",
    "PolygonIntradayBar",
    "ConfluenceHistory",
]
