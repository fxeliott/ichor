"""Kill switch — instantly halt all new order generation.

Two trip mechanisms (OR'd) :

  1. **File flag** : presence of `/etc/ichor/KILL_SWITCH` (or
     `DEFAULT_KILL_SWITCH_PATH` override) trips the switch. Operator can
     `touch` this file from any shell to halt the system without code
     deploy.

  2. **Env var** : `ICHOR_KILL_SWITCH` set to a truthy value
     (`1`/`true`/`yes`/`on`) trips the switch. Useful for systemd units
     and emergency containment.

Tripping is one-way per process — once tripped, calls to `assert_clear()`
raise `KillSwitchTripped`. Operator must :
  1. Investigate the cause (see RUNBOOK-012)
  2. Remove the file flag AND/OR unset the env var
  3. RESTART the process (we deliberately make trip non-clearable in-process)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

DEFAULT_KILL_SWITCH_PATH = Path("/etc/ichor/KILL_SWITCH")
ENV_VAR = "ICHOR_KILL_SWITCH"
TRUTHY = {"1", "true", "yes", "on"}


class KillSwitchTripped(RuntimeError):
    """Raised when a guarded operation is attempted under a tripped switch."""


@dataclass
class KillSwitch:
    """Detect + raise on tripped kill switch.

    Cheap : checks os.path.exists + env once per call. Cache TTL is 0 by
    default ; for hot paths set `cache_ttl_sec` to debounce.
    """

    flag_path: Path = field(default=DEFAULT_KILL_SWITCH_PATH)
    cache_ttl_sec: float = 0.0

    _cache_value: bool = field(default=False, init=False)
    _cache_expires_at: float = field(default=0.0, init=False)
    _trip_locked: bool = field(default=False, init=False)
    """Once tripped, stays tripped for the life of this process."""

    def is_tripped(self) -> bool:
        if self._trip_locked:
            return True
        now = time.monotonic()
        if self.cache_ttl_sec > 0 and now < self._cache_expires_at:
            return self._cache_value

        env_val = os.environ.get(ENV_VAR, "").lower().strip()
        env_tripped = env_val in TRUTHY

        try:
            file_tripped = self.flag_path.exists()
        except OSError as e:
            log.warning("kill_switch.file_check_error", error=str(e))
            file_tripped = False

        tripped = env_tripped or file_tripped
        if tripped and not self._trip_locked:
            self._trip_locked = True
            log.error(
                "kill_switch.tripped",
                env_tripped=env_tripped,
                file_tripped=file_tripped,
                flag_path=str(self.flag_path),
            )

        self._cache_value = tripped
        self._cache_expires_at = now + self.cache_ttl_sec
        return tripped

    def assert_clear(self) -> None:
        """Raise KillSwitchTripped if the switch is on."""
        if self.is_tripped():
            raise KillSwitchTripped(
                f"Kill switch tripped (file={self.flag_path}, env={ENV_VAR}). "
                "All order generation halted. See RUNBOOK-012."
            )

    @property
    def trip_locked(self) -> bool:
        """Test helper : has this process seen the switch trip at least once?"""
        return self._trip_locked
