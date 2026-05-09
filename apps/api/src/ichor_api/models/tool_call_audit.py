"""tool_call_audit table — Capability 5 client-tool invocation log.

Append-only via Postgres trigger (migration 0038, ADR-029 MiFID
compliance pattern mirrored from audit_log 0028). Captures every
Capability 5 tool call (`query_db`, `calc`, `rag_historical`) made
by the 4-pass orchestrator + Pass 5 counterfactual.

Until Capability 5 wiring lands (ADR-071 Phase D.0), this table is
empty by design — its mere presence enforces the audit-trail-first
invariant (no "we'll add audit later" regression possible).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ToolCallAudit(Base):
    """One Capability 5 tool invocation, immutable post-insert."""

    __tablename__ = "tool_call_audit"
    __table_args__ = (
        CheckConstraint("pass_index BETWEEN 1 AND 5", name="ck_tool_call_audit_pass_index"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_tool_call_audit_duration",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)

    agent_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    """Which 4-pass agent invoked the tool (e.g. 'pass1_regime',
    'pass5_counterfactual')."""

    pass_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    """1..5 — supports Pass 5 counterfactual scope."""

    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    """MCP-qualified name (e.g. `mcp__ichor_db__query_db`)."""

    tool_input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """Args sent to the tool handler."""

    tool_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """Result of the tool handler. NULL when error is set."""

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Wall-time the tool handler took (ms)."""

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Exception class + message on failure. NULL on success."""

    session_card_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    """FK to session_card_audit when made inside a 4-pass run."""
