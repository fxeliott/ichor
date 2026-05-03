"""Ichor risk engine — sizing, stops, kill switch.

Public surface :
  - `RiskEngine`             : the orchestrator
  - `RiskConfig`             : knobs (Kelly cap, per-trade stop, daily DD)
  - `KillSwitch`             : file-flag + env-var trip detection
  - `RiskDecision`           : `(allowed, sized_qty, reason)`
  - `KillSwitchTripped`      : exception when a guard fires
"""

from .config import RiskConfig
from .engine import RiskDecision, RiskEngine, RiskSnapshot
from .kill_switch import (
    DEFAULT_KILL_SWITCH_PATH,
    KillSwitch,
    KillSwitchTripped,
)

__all__ = [
    "RiskConfig",
    "RiskDecision",
    "RiskEngine",
    "RiskSnapshot",
    "KillSwitch",
    "KillSwitchTripped",
    "DEFAULT_KILL_SWITCH_PATH",
]
