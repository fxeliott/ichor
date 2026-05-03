"""backtest_runs table — persisted backtest history."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    model_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    n_folds: Mapped[int] = mapped_column(Integer, nullable=False)
    n_signals: Mapped[int] = mapped_column(Integer, nullable=False)
    n_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    equity_curve_summary: Mapped[list | None] = mapped_column(JSONB)
    notes: Mapped[list | None] = mapped_column(JSONB)
    paper_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
