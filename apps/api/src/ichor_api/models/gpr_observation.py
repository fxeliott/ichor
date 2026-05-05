"""gpr_observations table — daily AI-GPR Index readings."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GprObservation(Base):
    """One daily reading of the AI-GPR Index (Caldara & Iacoviello).

    Composite PK (id, observation_date) for TimescaleDB hypertable.
    """

    __tablename__ = "gpr_observations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ai_gpr: Mapped[float] = mapped_column(Float, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
