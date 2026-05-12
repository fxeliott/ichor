"""Re-export Pass-6 scenario_decompose schemas from `ichor_brain.scenarios`.

The canonical home of the Pass-6 contract surface is
`packages/ichor_brain/src/ichor_brain/scenarios.py` (architectural
cleanup 2026-05-12 — closing the ichor-trader audit JAUNE flag
documented during the same-day code-line-by-line audit).

This module re-exports the schemas verbatim so :

  * Existing CI guards in `apps/api/tests/test_invariants_ichor.py`
    (`test_pass6_bucket_labels_exactly_seven_canonical`,
    `test_pass6_cap_95_constant_unchanged`,
    `test_pass6_scenario_mechanism_rejects_trade_tokens`) keep
    importing from `ichor_api.services.scenarios.{BUCKET_LABELS,
    CAP_95, Scenario}` byte-equivalently.
  * Existing tests in `apps/api/tests/test_scenarios.py` keep
    importing `BucketLabel`, `ScenarioDecomposition`,
    `cap_and_normalize`, `bucket_for_zscore`, `SUM_TOLERANCE`.
  * The `apps/api/models/session_card_audit.py` JSONB column docstring
    that points at the canonical Pydantic enum stays valid.

ADR-085 ratifies the schema ; this file is the boundary-side re-export.
"""

from __future__ import annotations

from ichor_brain.scenarios import (
    BUCKET_LABELS,
    BUCKET_Z_THRESHOLDS,
    CAP_95,
    SUM_TOLERANCE,
    BucketLabel,
    Scenario,
    ScenarioDecomposition,
    bucket_for_zscore,
    cap_and_normalize,
)

__all__ = [
    "BUCKET_LABELS",
    "BUCKET_Z_THRESHOLDS",
    "CAP_95",
    "SUM_TOLERANCE",
    "BucketLabel",
    "Scenario",
    "ScenarioDecomposition",
    "bucket_for_zscore",
    "cap_and_normalize",
]
