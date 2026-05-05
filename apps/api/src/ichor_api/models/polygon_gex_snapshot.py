"""gex_snapshots table — FlashAlpha dealer GEX persisted per asset.

Persists snapshots that `collectors/flashalpha.py` fetches but used to
throw away (cf SPEC.md §2.2 #9). Powers the `data_pool` `gex` section
consumed by Pass 2 (asset framework) on SPX/NDX options-bearing assets.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PolygonGexSnapshot(Base):
    """One dealer GEX snapshot from FlashAlpha (SPX or NDX).

    Composite PK (id, captured_at) for TimescaleDB hypertable on
    `captured_at`. The migration that creates the table is
    `0008_gex_snapshots.py`.
    """

    __tablename__ = "gex_snapshots"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    dealer_gex_total: Mapped[float | None] = mapped_column(Numeric(precision=20, scale=4))
    """Net dealer gamma in USD. Positive = vol-suppressing, negative =
    vol-amplifying."""

    gamma_flip: Mapped[float | None] = mapped_column(Numeric(precision=14, scale=4))
    call_wall: Mapped[float | None] = mapped_column(Numeric(precision=14, scale=4))
    put_wall: Mapped[float | None] = mapped_column(Numeric(precision=14, scale=4))
    vol_trigger: Mapped[float | None] = mapped_column(Numeric(precision=14, scale=4))
    spot_at_capture: Mapped[float | None] = mapped_column(Numeric(precision=14, scale=4))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="flashalpha")
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
