"""ScenarioCalibrationBins ORM — per (asset, session_type) z-score calibration.

Written by `services/scenario_calibration.py` (W105b) every Sunday
00:00 UTC from `polygon_intraday` realized session-window returns
(252 trading-days rolling). Read by `passes/scenarios.py` (W105c) to
translate canonical z-score thresholds [-2.5, -1.0, -0.25, 0.25, 1.0,
2.5] into per-asset pip/point thresholds the LLM can cite as
realized-magnitude ranges.

The PK includes `computed_at` so the table is append-only by design —
the most recent row per (asset, session_type) is selected via the
`ix_scenario_calibration_bins_latest` index (DESC on computed_at).
ADR-085 acceptance criterion #2 : 6 assets × 5 sessions = 30 rows
minimum, refreshed weekly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScenarioCalibrationBins(Base):
    """One snapshot of z-score → pip-threshold calibration."""

    __tablename__ = "scenario_calibration_bins"
    __table_args__ = (
        CheckConstraint(
            "sample_n >= 0",
            name="ck_scenario_calibration_bins_sample_n_nonneg",
        ),
        CheckConstraint(
            ("session_type IN ('pre_londres','pre_ny','ny_mid','ny_close','event_driven')"),
            name="ck_scenario_calibration_bins_session_type",
        ),
    )

    asset: Mapped[str] = mapped_column(Text, primary_key=True)
    session_type: Mapped[str] = mapped_column(Text, primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    bins_z_thresholds: Mapped[Any] = mapped_column(JSONB, nullable=False)
    """Six z-score boundaries that partition the realized-return space
    into the 7 canonical buckets. Default = `[-2.5, -1.0, -0.25, 0.25,
    1.0, 2.5]` mirrored from `services/scenarios.py:BUCKET_Z_THRESHOLDS`."""

    bins_pip_thresholds: Mapped[Any] = mapped_column(JSONB, nullable=False)
    """Same six boundaries translated into the asset's pip/point unit
    on the rolling 252d realized-return distribution. FX majors store
    pips ; XAU_USD stores price-points ; NAS100/SPX500 store index
    points. Documented per-asset in `services/scenario_calibration.py`."""

    sample_n: Mapped[int] = mapped_column(Integer, nullable=False)
    """Number of historical session-window returns the bins were fit on.
    Reconciler skips a calibration row when sample_n is below the
    confidence floor (default 60, configurable per asset)."""
