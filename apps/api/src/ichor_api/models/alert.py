"""alerts table — 33 alert types per AUDIT_V3 §4.2."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Alert(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "alerts"

    alert_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    """e.g. SOFR_SPIKE, FX_PEG_BREAK, DEALER_GAMMA_FLIP, HY_OAS_WIDEN, ..."""

    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    """info | warning | critical"""

    asset: Mapped[str | None] = mapped_column(String(16), index=True)
    """Specific asset if applicable, else NULL for cross-asset alerts."""

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Trigger details
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    """above | below | cross_up | cross_down"""

    # Source data snapshot
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Description rendered for UI
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # State
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
