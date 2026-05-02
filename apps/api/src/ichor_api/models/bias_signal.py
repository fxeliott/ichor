"""bias_signals table — output of the Bias Aggregator ensemble."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BiasSignal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bias_signals"

    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    credible_interval_low: Mapped[float] = mapped_column(Float, nullable=False)
    credible_interval_high: Mapped[float] = mapped_column(Float, nullable=False)

    contributing_predictions: Mapped[list] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False
    )
    """FK array into predictions_audit.id."""

    weights_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    """{model_family: normalized_weight} at this run."""

    notes: Mapped[str | None] = mapped_column(Text)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
