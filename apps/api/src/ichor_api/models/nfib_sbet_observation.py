"""nfib_sbet_observations — monthly NFIB Small Business Economic Trends.

Captures the headline Small Business Optimism Index (SBOI) + Uncertainty
Index from the monthly NFIB SBET PDF report. SBOI is a 1986=100
composite of 10 forward-looking sub-components; it's a leading indicator
of US small business sentiment that tracks hiring and capex plans.

Source: PDF scraped from nfib.com/news/monthly_report/sbet/.
License: NFIB report, derive metrics + attribute "Source: NFIB SBET".
Do not rehost the PDF.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NfibSbetObservation(Base):
    """One monthly NFIB SBET headline observation."""

    __tablename__ = "nfib_sbet_observations"
    __table_args__ = (
        UniqueConstraint(
            "report_month",
            name="uq_nfib_sbet_report_month",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    report_month: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    """Survey month (first day). Survey month is month-1 vs publish month."""

    sboi: Mapped[float] = mapped_column(Float, nullable=False)
    """Small Business Optimism Index (1986=100 base)."""

    uncertainty_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Small Business Uncertainty Index sub-component."""

    source_pdf_url: Mapped[str] = mapped_column(String(512), nullable=False)
    """URL of the source PDF (for audit / re-fetch)."""

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
