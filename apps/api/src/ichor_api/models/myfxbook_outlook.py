"""myfxbook_outlooks — retail FX retail-trader long/short ratios.

Captures the MyFXBook Community Outlook — a snapshot of the long vs
short percentage of MyFXBook's retail trader population per FX pair.
Used by Ichor as a contrarian sentiment indicator (extreme retail
positioning often precedes a turn).

Source: MyFXBook Community Outlook API
(https://www.myfxbook.com/api/get-community-outlook.json).
License: free tier, "any software developed using the API should be
free" (research-internal use OK with attribution).
Bias: sample = traders who have voluntarily linked accounts to
MyFXBook. Self-selected — not representative of all retail.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MyfxbookOutlook(Base):
    """One MyFXBook Community Outlook snapshot per pair."""

    __tablename__ = "myfxbook_outlooks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )

    pair: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    """Canonical pair label (e.g. EURUSD, XAUUSD)."""

    long_pct: Mapped[float] = mapped_column(Float, nullable=False)
    """Percent of population currently long (0-100)."""

    short_pct: Mapped[float] = mapped_column(Float, nullable=False)
    """Percent of population currently short (0-100)."""

    long_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Aggregate long volume (lots, MyFXBook unit)."""

    short_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Aggregate short volume."""

    avg_long_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Average entry price across long population."""

    avg_short_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Average entry price across short population."""

    long_positions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Number of distinct long positions across the population."""

    short_positions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Number of distinct short positions."""
