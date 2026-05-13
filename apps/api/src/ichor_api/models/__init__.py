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

# Phase II — NFIB Small Business Economic Trends monthly (Wave 74)
# Phase D cross-cutting — auto-improvement loop audit (ADR-087, W113)
from .auto_improvement_log import AutoImprovementLog
from .base import Base
from .bias_signal import BiasSignal
from .briefing import Briefing

# Phase D W115 — Vovk-Zhdanov AA Brier aggregator pockets (ADR-087)
from .brier_aggregator_weights import BrierAggregatorWeight

# Phase D ADR-090 P0 step-1 — Bundesbank Bund 10Y daily (round 29)
from .bund_10y_observation import BundYieldObservation
from .cb_speech import CbSpeech

# Phase II Layer 1 — CBOE SKEW Index daily (Wave 24)
from .cboe_skew_observation import CboeSkewObservation

# Phase II Layer 1 — CBOE VVIX (vol of VIX) daily (Wave 29)
from .cboe_vvix_observation import CboeVvixObservation

# Phase II Layer 1 — CFTC TFF weekly positioning (Wave 25)
from .cftc_tff_observation import CftcTffObservation

# Phase II — Cleveland Fed daily inflation nowcast (Wave 72)
from .cleveland_fed_nowcast import ClevelandFedNowcast
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

# Phase II — MyFXBook Community Outlook retail FX positioning (Wave 77)
from .myfxbook_outlook import MyfxbookOutlook
from .news_item import NewsItem
from .nfib_sbet_observation import NfibSbetObservation

# Phase II — NY Fed Multivariate Core Trend monthly (Wave 71)
from .nyfed_mct_observation import NyfedMctObservation

# Phase D W116 — post-mortem PBS addenda for Pass-3 (ADR-087)
from .pass3_addendum import Pass3Addendum
from .polygon_gex_snapshot import PolygonGexSnapshot
from .polygon_intraday import PolygonIntradayBar
from .polymarket_snapshot import PolymarketSnapshot
from .post_mortem import PostMortem
from .prediction import Prediction

# W105a — Pass-6 scenario_decompose 7-bucket calibration bins (ADR-085)
from .scenario_calibration_bins import ScenarioCalibrationBins
from .session_card_audit import SessionCardAudit
from .session_card_counterfactual import SessionCardCounterfactual

# Capability 5 PRE-2 — append-only tool-call audit (ADR-071, W73+)
from .tool_call_audit import ToolCallAudit

# Phase B.5d v2 — trader's private journal (out of ADR-017 boundary)
from .trader_note import TraderNote

# Phase II Layer 1 — Treasury TIC monthly foreign holdings (Wave 32)
from .treasury_tic_holding import TreasuryTicHolding

__all__ = [
    "Alert",
    # Phase D — auto-improvement loops audit (ADR-087)
    "AutoImprovementLog",
    "Base",
    "BiasSignal",
    "Briefing",
    # Phase D W115 — Vovk-AA Brier aggregator pockets
    "BrierAggregatorWeight",
    # Phase D ADR-090 P0 step-1 — Bund 10Y daily
    "BundYieldObservation",
    "CbSpeech",
    "CboeSkewObservation",
    "CboeVvixObservation",
    "CftcTffObservation",
    "ClevelandFedNowcast",
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
    "MyfxbookOutlook",
    "NewsItem",
    "NfibSbetObservation",
    "NyfedMctObservation",
    # Phase D W116 — post-mortem PBS addenda for Pass-3
    "Pass3Addendum",
    "PolygonGexSnapshot",
    "PolygonIntradayBar",
    "PolymarketSnapshot",
    "PostMortem",
    "Prediction",
    "ScenarioCalibrationBins",
    "SessionCardAudit",
    "SessionCardCounterfactual",
    "ToolCallAudit",
    "TraderNote",
    "TreasuryTicHolding",
]
