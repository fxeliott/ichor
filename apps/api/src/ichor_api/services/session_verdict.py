"""Re-export ``SessionVerdict`` + supporting types from ``ichor_brain.session_verdict``.

Mirror of ``apps/api/src/ichor_api/services/scenarios.py`` re-export pattern
(W105d 2026-05-12 architectural cleanup). The canonical home of the verdict
contract is ``packages/ichor_brain/src/ichor_brain/session_verdict.py`` so
that :

  * ``packages/ichor_brain/passes/`` (any future Pass-7 verdict-aggregator)
    can import directly without a lazy-import indirection
  * ``apps/api`` consumers (routers, services, tests) re-export verbatim,
    byte-equivalent at the public surface
  * The frontend type-generator (future r161+ Strand G) can target a
    single Pydantic module for OpenAPI schema export

ADR-106 ratifies the contract ; this file is the boundary-side re-export.
"""

from __future__ import annotations

from ichor_brain.session_verdict import (
    LiveTrigger,
    LiveTriggerImpact,
    LiveTriggerType,
    PriorityAsset,
    ScenarioInvalidationState,
    SessionVerdict,
    VerdictDirection,
    VerdictNature,
)

__all__ = [
    "LiveTrigger",
    "LiveTriggerImpact",
    "LiveTriggerType",
    "PriorityAsset",
    "ScenarioInvalidationState",
    "SessionVerdict",
    "VerdictDirection",
    "VerdictNature",
]
