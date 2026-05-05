"""fx_ticks table — Polygon Forex WebSocket quote ticks for VPIN.

One row per quote update (bid/ask refresh) streamed from
`wss://socket.polygon.io/forex`. Mid-price is precomputed for
downstream microstructure features. Composite PK (id, ts) is required
by TimescaleDB hypertable partitioning on `ts`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FxTick(Base):
    __tablename__ = "fx_ticks"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    bid: Mapped[float] = mapped_column(Float, nullable=False)
    ask: Mapped[float] = mapped_column(Float, nullable=False)
    mid: Mapped[float] = mapped_column(Float, nullable=False)
    bid_size: Mapped[float | None] = mapped_column(Float)
    ask_size: Mapped[float | None] = mapped_column(Float)
    exchange_id: Mapped[int | None] = mapped_column(Integer)
