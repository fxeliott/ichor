"""HTTP routers grouped by domain."""

from .briefings import router as briefings_router
from .alerts import router as alerts_router
from .bias_signals import router as bias_signals_router
from .ws import router as ws_router

__all__ = [
    "briefings_router",
    "alerts_router",
    "bias_signals_router",
    "ws_router",
]
