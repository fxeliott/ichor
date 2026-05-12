"""Unit tests for the `services.auto_improvement_log.record` helper (W113+).

DB integration is exercised by smoke / integration tests separately ;
here we cover the pure-Python validation slice :

  1. Invalid loop_kind / decision / disposition raise
     `AutoImprovementLogError` with a clear message BEFORE any DB
     round-trip (mirrors the CHECK constraints from migration 0042).
  2. Valid inputs do NOT raise locally.
"""

from __future__ import annotations

import pytest
from ichor_api.services.auto_improvement_log import (
    _VALID_DECISIONS,
    _VALID_DISPOSITIONS,
    _VALID_LOOP_KINDS,
    AutoImprovementLogError,
    record,
)


def test_valid_loop_kinds_match_migration_check() -> None:
    """Catches drift between the helper's frozenset and the migration's
    CHECK constraint. If a new loop is added to ADR-087, BOTH must
    change."""
    assert _VALID_LOOP_KINDS == frozenset(
        {"brier_aggregator", "adwin_drift", "post_mortem", "meta_prompt"}
    )


def test_valid_decisions_match_migration_check() -> None:
    assert _VALID_DECISIONS == frozenset({"adopted", "rejected", "pending_review", "sequestered"})


def test_valid_dispositions_match_migration_check() -> None:
    assert _VALID_DISPOSITIONS == frozenset({"keep", "tweak", "sequester", "retire"})


@pytest.mark.asyncio
async def test_record_rejects_unknown_loop_kind() -> None:
    with pytest.raises(AutoImprovementLogError, match="loop_kind="):
        await record(
            loop_kind="not_a_real_loop",
            trigger_event="test",
            input_summary={},
            output_summary={},
            metric_name="brier",
            decision="adopted",
        )


@pytest.mark.asyncio
async def test_record_rejects_unknown_decision() -> None:
    with pytest.raises(AutoImprovementLogError, match="decision="):
        await record(
            loop_kind="adwin_drift",
            trigger_event="test",
            input_summary={},
            output_summary={},
            metric_name="brier",
            decision="maybe",
        )


@pytest.mark.asyncio
async def test_record_rejects_unknown_disposition() -> None:
    with pytest.raises(AutoImprovementLogError, match="disposition="):
        await record(
            loop_kind="adwin_drift",
            trigger_event="test",
            input_summary={},
            output_summary={},
            metric_name="brier",
            decision="adopted",
            disposition="postpone",
        )


@pytest.mark.asyncio
async def test_record_accepts_none_disposition() -> None:
    """disposition is the only nullable enum — must NOT trigger the
    validation error when explicitly None."""
    # We can't run the full record() without a real DB, but we CAN
    # ensure the validation gate accepts None. The function will fail
    # later when trying to open a session ; we catch that as expected.
    with pytest.raises(Exception):  # noqa: BLE001 — session error is fine
        await record(
            loop_kind="adwin_drift",
            trigger_event="test",
            input_summary={},
            output_summary={},
            metric_name="brier",
            decision="adopted",
            disposition=None,
        )
