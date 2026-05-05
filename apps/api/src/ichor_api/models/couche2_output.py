"""couche2_outputs table — output of the 4 Couche-2 agents.

Persists the JSON payload each Couche-2 agent emits per run, plus
provenance (model used, input window, sources consumed, cost). Consumed
by `data_pool` sections that feed Pass 1 (regime) and Pass 2 (asset).

Cadence (cf SPEC.md §3.2):
  - CB-NLP, News-NLP : every 4h (Sonnet 4.6)
  - Sentiment, Positioning : every 6h (Haiku 4.5)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Couche2Output(Base):
    """One run of one Couche-2 agent.

    Composite PK (id, ran_at) for TimescaleDB hypertable on `ran_at`.
    The migration is `0009_couche2_outputs.py`.
    """

    __tablename__ = "couche2_outputs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    agent_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    """One of: cb_nlp, news_nlp, sentiment, positioning."""

    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    input_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    input_sources: Mapped[list[str] | None] = mapped_column(JSONB)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    token_input: Mapped[int | None] = mapped_column(Integer)
    token_output: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(precision=10, scale=4))
    error: Mapped[str | None] = mapped_column(Text)
