"""auto_improvement_log table — Phase D cross-cutting audit (ADR-087, W113).

Every Phase D auto-improvement loop (brier_aggregator W115, adwin_drift
W114, post_mortem W116, meta_prompt W117) writes one append-only row
per step. The table is `BEFORE UPDATE OR DELETE` triggered to enforce
ADR-029-class immutability (matches `audit_log` + `tool_call_audit`).

Schema docstring in `apps/api/migrations/versions/0042_auto_improvement_log.py`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AutoImprovementLog(Base):
    """One append-only Phase D auto-improvement step.

    Composite PK `(id, ran_at)` for TimescaleDB hypertable on `ran_at`.
    See migration 0042 for index list and trigger definition.
    """

    __tablename__ = "auto_improvement_log"
    __table_args__ = (
        CheckConstraint(
            "loop_kind IN ('brier_aggregator', 'adwin_drift', 'post_mortem', 'meta_prompt')",
            name="ck_auto_improvement_log_loop_kind",
        ),
        CheckConstraint(
            "decision IN ('adopted', 'rejected', 'pending_review', 'sequestered')",
            name="ck_auto_improvement_log_decision",
        ),
        CheckConstraint(
            "disposition IS NULL OR disposition IN ('keep', 'tweak', 'sequester', 'retire')",
            name="ck_auto_improvement_log_disposition",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    loop_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_event: Mapped[str] = mapped_column(Text, nullable=False)
    asset: Mapped[str | None] = mapped_column(String(16), nullable=True)
    regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metric_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_name: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    executor_user: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("current_user")
    )
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
