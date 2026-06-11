"""Alert primitive types — leaf module, imports NOTHING from this package.

Extracted from ``catalog.py`` (S03, 2026-06-11) to break the
``catalog ↔ scenario_invalidation`` import cycle: catalog mid-module
imports ``scenario_invalidation.SCENARIO_INVALIDATION_ALERTS`` to build
``ALL_ALERTS``, while scenario_invalidation needed ``AlertDef`` back from
catalog — a real py/unsafe-cyclic-import (CodeQL, PR #225): any import
order that reaches catalog through scenario_invalidation would hit a
partially-initialised module. Both now depend on THIS leaf instead;
``catalog`` re-exports the names so every existing
``from .catalog import AlertDef`` caller is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Severity = Literal["info", "warning", "critical"]
Direction = Literal["above", "below", "cross_up", "cross_down"]


@dataclass(frozen=True)
class AlertDef:
    code: str
    severity: Severity
    title_template: str
    metric_name: str
    default_threshold: float
    default_direction: Direction
    crisis_mode: bool = False
    description: str = ""


@dataclass
class AlertHit:
    """One fired alert occurrence — built by ``evaluator.evaluate_metric``
    or directly by the hit-building evaluators (scenario_invalidation,
    event_sentinel), persisted by ``services/alerts_runner``. Lives here
    (not in ``evaluator``) so hit-builders never need the
    catalog-importing evaluator module — the r165 lazy-import workaround
    is gone."""

    alert_def: AlertDef
    metric_value: float
    threshold: float
    direction_observed: Direction
    source_payload: dict[str, Any]
