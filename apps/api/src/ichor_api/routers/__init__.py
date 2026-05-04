"""HTTP routers grouped by domain.

Note : `backtests_router` was archived in commit ADR-017 reset (2026-05-03).
See `archive/2026-05-03-pre-reset/backtests_router.py`.
"""

from .admin import router as admin_router
from .alerts import router as alerts_router
from .bias_signals import router as bias_signals_router
from .briefings import router as briefings_router
from .calendar import router as calendar_router
from .calibration import router as calibration_router
from .confluence import router as confluence_router
from .counterfactual import router as counterfactual_router
from .currency_strength import router as currency_strength_router
from .data_pool import router as data_pool_router
from .geopolitics import router as geopolitics_router
from .graph import router as graph_router
from .market import router as market_router
from .narratives import router as narratives_router
from .news import router as news_router
from .predictions import router as predictions_router
from .push import router as push_router
from .sessions import router as sessions_router
from .trade_plan import router as trade_plan_router
from .ws import router as ws_router

__all__ = [
    "admin_router",
    "alerts_router",
    "bias_signals_router",
    "briefings_router",
    "calendar_router",
    "calibration_router",
    "confluence_router",
    "counterfactual_router",
    "currency_strength_router",
    "data_pool_router",
    "geopolitics_router",
    "graph_router",
    "market_router",
    "narratives_router",
    "news_router",
    "predictions_router",
    "push_router",
    "sessions_router",
    "trade_plan_router",
    "ws_router",
]
