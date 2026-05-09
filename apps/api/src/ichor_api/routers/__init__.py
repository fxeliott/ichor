"""HTTP routers grouped by domain.

Note : `backtests_router` was archived in commit ADR-017 reset (2026-05-03).
See `archive/2026-05-03-pre-reset/backtests_router.py`.
"""

from .admin import router as admin_router
from .alerts import router as alerts_router
from .bias_signals import router as bias_signals_router
from .briefings import router as briefings_router
from .brier_feedback import router as brier_feedback_router
from .calendar import router as calendar_router
from .calibration import router as calibration_router
from .confluence import router as confluence_router
from .correlations import router as correlations_router
from .counterfactual import router as counterfactual_router
from .currency_strength import router as currency_strength_router
from .data_pool import router as data_pool_router
from .divergence import router as divergence_router
from .economic_events import router as economic_events_router
from .geopolitics import router as geopolitics_router
from .graph import router as graph_router
from .hourly_volatility import router as hourly_volatility_router
from .journal import router as journal_router
from .macro_pulse import router as macro_pulse_router
from .market import router as market_router
from .narratives import router as narratives_router
from .news import router as news_router
from .polymarket_impact import router as polymarket_impact_router
from .portfolio_exposure import router as portfolio_exposure_router
from .post_mortems import router as post_mortems_router
from .predictions import router as predictions_router
from .push import router as push_router
from .scenarios import router as scenarios_router
from .sessions import router as sessions_router
from .sources import router as sources_router
from .today import router as today_router
from .tools import router as tools_router
from .trade_plan import router as trade_plan_router
from .ws import router as ws_router
from .yield_curve import router as yield_curve_router

__all__ = [
    "admin_router",
    "alerts_router",
    "bias_signals_router",
    "briefings_router",
    "brier_feedback_router",
    "calendar_router",
    "calibration_router",
    "confluence_router",
    "correlations_router",
    "counterfactual_router",
    "currency_strength_router",
    "data_pool_router",
    "divergence_router",
    "economic_events_router",
    "geopolitics_router",
    "graph_router",
    "hourly_volatility_router",
    "journal_router",
    "macro_pulse_router",
    "market_router",
    "narratives_router",
    "news_router",
    "polymarket_impact_router",
    "portfolio_exposure_router",
    "post_mortems_router",
    "predictions_router",
    "push_router",
    "scenarios_router",
    "sessions_router",
    "sources_router",
    "today_router",
    "tools_router",
    "trade_plan_router",
    "ws_router",
    "yield_curve_router",
]
