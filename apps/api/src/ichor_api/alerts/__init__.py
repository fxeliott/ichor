"""Alerts engine — 33 alert types + Crisis Mode composite trigger."""

from .catalog import (
    ALL_ALERTS,
    AUDIT_V2_ALERTS,
    BY_CODE,
    CRISIS_TRIGGERS,
    AlertDef,
    PLAN_ALERTS,
    assert_catalog_complete,
    get_alert_def,
)
from .crisis_mode import CrisisAssessment, assess_crisis
from .evaluator import AlertHit, evaluate_metric

__all__ = [
    "ALL_ALERTS",
    "AUDIT_V2_ALERTS",
    "BY_CODE",
    "CRISIS_TRIGGERS",
    "AlertDef",
    "AlertHit",
    "CrisisAssessment",
    "PLAN_ALERTS",
    "assert_catalog_complete",
    "assess_crisis",
    "evaluate_metric",
    "get_alert_def",
]
