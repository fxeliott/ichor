"""HTTP routers grouped by domain."""

from .alerts import router as alerts_router
from .backtests import router as backtests_router
from .bias_signals import router as bias_signals_router
from .briefings import router as briefings_router
from .market import router as market_router
from .news import router as news_router
from .predictions import router as predictions_router
from .ws import router as ws_router

__all__ = [
    "alerts_router",
    "backtests_router",
    "bias_signals_router",
    "briefings_router",
    "market_router",
    "news_router",
    "predictions_router",
    "ws_router",
]
