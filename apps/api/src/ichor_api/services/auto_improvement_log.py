"""Phase D auto-improvement log writer (ADR-087, W113 + W114).

Single canonical INSERT path for the 4 Phase D loops (W114 ADWIN drift /
W115 Vovk Brier aggregator / W116 Penalized Brier post-mortem / W117
DSPy GEPA meta-prompt). Every step writes ONE append-only row to
`auto_improvement_log` (migration 0042).

The table is BEFORE-UPDATE-OR-DELETE triggered (ADR-029-class
immutability), so callers must NOT try to mutate a prior row — always
INSERT a new row, referencing the prior row's `id` via `parent_id`
when modelling Pareto-front lineage (W117 GEPA).

API design :

* `record(...)` — async helper, takes typed kwargs aligned with the
  table CHECK constraints + indexed columns. Returns the new row's
  UUID so callers can use it as `parent_id` on a follow-up.
* The helper INSERTs in a freshly-acquired session (its own
  transaction) so a failure inside the calling loop's transaction
  doesn't silently drop the audit row.
* `loop_kind`, `decision`, `disposition` are enum-constrained at
  the DB layer (CHECK constraints) — we re-validate in Python to
  fail fast with a clearer error message before round-trip.

Usage example (W114 ADWIN tier-1 alert) :
    new_id = await auto_improvement_log.record(
        loop_kind="adwin_drift",
        trigger_event="adwin:drift_eurusd_target",
        asset="EUR_USD",
        regime=None,
        input_summary={"detector": "target", "n_obs": 120, "estimation": 0.27},
        output_summary={"tier": 1, "action": "structlog_alert"},
        metric_before=0.21,
        metric_after=0.27,
        metric_name="brier_residual_mean",
        decision="pending_review",
        disposition=None,
        model_version="brier_optimizer_v2",
        parent_id=None,
    )
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import insert

from ..db import get_sessionmaker
from ..models import AutoImprovementLog

log = structlog.get_logger(__name__)


# Mirror of the migration's CHECK constraints. Catches bad inputs
# locally before the DB round-trip — clearer error than the Postgres
# `ck_auto_improvement_log_*` violation messages.
_VALID_LOOP_KINDS = frozenset({"brier_aggregator", "adwin_drift", "post_mortem", "meta_prompt"})
_VALID_DECISIONS = frozenset({"adopted", "rejected", "pending_review", "sequestered"})
_VALID_DISPOSITIONS = frozenset({"keep", "tweak", "sequester", "retire"})


class AutoImprovementLogError(ValueError):
    """Raised when caller passes invalid enum value before DB hit."""


async def record(
    *,
    loop_kind: str,
    trigger_event: str,
    input_summary: dict[str, Any],
    output_summary: dict[str, Any],
    metric_name: str,
    decision: str,
    asset: str | None = None,
    regime: str | None = None,
    metric_before: float | None = None,
    metric_after: float | None = None,
    disposition: str | None = None,
    model_version: str | None = None,
    parent_id: UUID | None = None,
) -> UUID:
    """Insert one auto-improvement row. Returns the new row's UUID.

    Validates the 3 CHECK-constrained enums (`loop_kind`, `decision`,
    `disposition`) locally before round-trip. Other fields are passed
    through to the table.

    Opens its own session+transaction — independent of any calling
    loop's transaction so the audit row survives a parent rollback.
    """
    if loop_kind not in _VALID_LOOP_KINDS:
        raise AutoImprovementLogError(f"loop_kind={loop_kind!r} not in {sorted(_VALID_LOOP_KINDS)}")
    if decision not in _VALID_DECISIONS:
        raise AutoImprovementLogError(f"decision={decision!r} not in {sorted(_VALID_DECISIONS)}")
    if disposition is not None and disposition not in _VALID_DISPOSITIONS:
        raise AutoImprovementLogError(
            f"disposition={disposition!r} not in {sorted(_VALID_DISPOSITIONS)}"
        )

    sm = get_sessionmaker()
    async with sm() as session:
        async with session.begin():
            result = await session.execute(
                insert(AutoImprovementLog)
                .values(
                    loop_kind=loop_kind,
                    trigger_event=trigger_event,
                    asset=asset,
                    regime=regime,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    metric_before=metric_before,
                    metric_after=metric_after,
                    metric_name=metric_name,
                    decision=decision,
                    disposition=disposition,
                    model_version=model_version,
                    parent_id=parent_id,
                )
                .returning(AutoImprovementLog.id)
            )
            new_id = result.scalar_one()
    log.info(
        "auto_improvement_log.record",
        id=str(new_id),
        loop_kind=loop_kind,
        trigger_event=trigger_event,
        asset=asset,
        decision=decision,
    )
    return new_id
