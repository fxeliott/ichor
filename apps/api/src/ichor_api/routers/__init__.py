"""HTTP routers grouped by domain.

Note : `backtests_router` was archived in commit ADR-017 reset (2026-05-03).
See `archive/2026-05-03-pre-reset/backtests_router.py`.
"""

from .alerts import router as alerts_router
from .bias_signals import router as bias_signals_router
from .briefings import router as briefings_router
from .calibration import router as calibration_router
from .market import router as market_router
from .news import router as news_router
from .predictions import router as predictions_router
from .sessions import router as sessions_router
from .ws import router as ws_router

__all__ = [
    "alerts_router",
    "bias_signals_router",
    "briefings_router",
    "calibration_router",
    "market_router",
    "news_router",
    "predictions_router",
    "sessions_router",
    "ws_router",
]
