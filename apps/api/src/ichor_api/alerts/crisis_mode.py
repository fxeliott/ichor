"""Crisis Mode composite — fires when N (default 2) or more crisis_mode-flagged
alerts are simultaneously active (un-acknowledged) within the lookback window.

When Crisis Mode triggers:
  1. Insert a synthetic alert with code='CRISIS_MODE_ACTIVE', severity='critical'
  2. Trigger an out-of-cycle briefing (briefing_type='crisis')
  3. Push to dashboard via Redis 'ichor:crisis:active'

Resolution: when active crisis_mode alerts drop below N (any acknowledged
or aged out), resolve with code='CRISIS_MODE_RESOLVED'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Alert
from .catalog import CRISIS_TRIGGERS


@dataclass
class CrisisAssessment:
    is_active: bool
    triggering_codes: list[str]
    """Subset of CRISIS_TRIGGERS that are currently un-acknowledged."""
    severity_score: float
    """Sum of severity weights (info=1, warning=2, critical=3) — for ranking."""


async def assess_crisis(
    session: AsyncSession,
    *,
    min_concurrent: int = 2,
    lookback_minutes: int = 60,
) -> CrisisAssessment:
    """Walk the alerts table for active crisis_mode alerts in the last hour."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

    stmt = select(Alert).where(
        Alert.alert_code.in_(CRISIS_TRIGGERS),
        Alert.acknowledged_at.is_(None),
        Alert.triggered_at >= cutoff,
    )
    rows = (await session.execute(stmt)).scalars().all()

    severity_weights = {"info": 1.0, "warning": 2.0, "critical": 3.0}
    score = sum(severity_weights.get(r.severity, 0) for r in rows)
    codes = [r.alert_code for r in rows]

    return CrisisAssessment(
        is_active=len(codes) >= min_concurrent,
        triggering_codes=codes,
        severity_score=score,
    )
