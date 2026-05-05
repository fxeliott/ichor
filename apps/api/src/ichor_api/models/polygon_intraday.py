"""polygon_intraday table — 1-min OHLCV from Polygon.io Starter."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PolygonIntradayBar(Base):
    """One 1-min OHLCV bar from Polygon.io for one asset.

    Composite PK (id, bar_ts) for TimescaleDB hypertable on `bar_ts`.
    Unique on (asset, bar_ts) so reruns are idempotent.
    """

    __tablename__ = "polygon_intraday"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    bar_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    vwap: Mapped[float | None] = mapped_column(Float)
    transactions: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
