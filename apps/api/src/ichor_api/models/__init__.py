"""SQLAlchemy ORM models. Mirrors the Postgres schema.

Naming: tables snake_case plural, columns snake_case, FKs `<table>_id`.
All timestamps are TIMESTAMPTZ (UTC).

Note : `BacktestRun` was archived in commit ADR-017 reset (2026-05-03).
See `archive/2026-05-03-pre-reset/backtest_run_model.py`.

Phase 1 Living Macro Entity tables (migration 0005, 2026-05-03) :
FredObservation, GdeltEvent, GprObservation, CotPosition, CbSpeech,
KalshiMarket, ManifoldMarket, SessionCardAudit.
"""

from .alert import Alert
from .base import Base
from .bias_signal import BiasSignal
from .briefing import Briefing
from .cb_speech import CbSpeech

# Phase II Layer 1 — CBOE SKEW Index daily (Wave 24)
from .cboe_skew_observation import CboeSkewObservation

# Phase II Layer 1 — CFTC TFF weekly positioning (Wave 25)
from .cftc_tff_observation import CftcTffObservation
from .confluence_history import ConfluenceHistory
from .cot_position import CotPosition

# Phase 2
from .couche2_output import Couche2Output
from .economic_event import EconomicEvent
from .finra_short_volume import FinraShortVolume

# Phase 1 Living Macro Entity collectors
from .fred_observation import FredObservation

# Phase 2 — VPIN microstructure (migration 0020)
from .fx_tick import FxTick
from .gdelt_event import GdeltEvent
from .gpr_observation import GprObservation
from .kalshi_market import KalshiMarket
from .manifold_market import ManifoldMarket
from .market_data import MarketDataBar
from .news_item import NewsItem
from .polygon_gex_snapshot import PolygonGexSnapshot
from .polygon_intraday import PolygonIntradayBar
from .polymarket_snapshot import PolymarketSnapshot
from .post_mortem import PostMortem
from .prediction import Prediction
from .session_card_audit import SessionCardAudit
from .session_card_counterfactual import SessionCardCounterfactual

# Phase B.5d v2 — trader's private journal (out of ADR-017 boundary)
from .trader_note import TraderNote

__all__ = [
    "Alert",
    "Base",
    "BiasSignal",
    "Briefing",
    "CbSpeech",
    "CboeSkewObservation",
    "CftcTffObservation",
    "ConfluenceHistory",
    "CotPosition",
    # Phase 2
    "Couche2Output",
    "EconomicEvent",
    # Phase 2 — FINRA Reg SHO daily short volume
    "FinraShortVolume",
    # Phase 1
    "FredObservation",
    # Phase 2 — VPIN microstructure
    "FxTick",
    "GdeltEvent",
    "GprObservation",
    "KalshiMarket",
    "ManifoldMarket",
    "MarketDataBar",
    "NewsItem",
    "PolygonGexSnapshot",
    "PolygonIntradayBar",
    "PolymarketSnapshot",
    "PostMortem",
    "Prediction",
    "SessionCardAudit",
    "SessionCardCounterfactual",
    "TraderNote",
]
