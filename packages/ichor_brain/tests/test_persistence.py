"""SessionCard → SessionCardAudit row mapping.

Skipped automatically when `ichor_api` isn't installed (the brain
package can be exercised standalone).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ichor_brain.persistence import to_audit_row
from ichor_brain.types import (
    AssetSpecialization,
    CriticDecision,
    InvalidationConditions,
    RegimeReading,
    SessionCard,
    StressTest,
)

from .fixtures import (
    ASSET_OK_JSON,
    INVALIDATION_OK_JSON,
    REGIME_OK_JSON,
    STRESS_OK_JSON,
)

pytest.importorskip("ichor_api")


def _make_card() -> SessionCard:
    return SessionCard(
        session_type="pre_londres",
        asset="EUR_USD",
        generated_at=datetime(2026, 5, 4, 5, 0, tzinfo=timezone.utc),
        regime=RegimeReading.model_validate(REGIME_OK_JSON),
        specialization=AssetSpecialization.model_validate(ASSET_OK_JSON),
        stress=StressTest.model_validate(STRESS_OK_JSON),
        invalidation=InvalidationConditions.model_validate(INVALIDATION_OK_JSON),
        critic=CriticDecision(verdict="approved", confidence=0.92),
        source_pool_hash="a" * 64,
        claude_duration_ms=42_000,
    )


def test_to_audit_row_uses_revised_conviction_not_pass2() -> None:
    """Persisted conviction is the post-stress one — that's the
    calibration-honest number."""
    card = _make_card()
    row = to_audit_row(card)
    assert row.conviction_pct == card.stress.revised_conviction_pct
    assert row.conviction_pct != card.specialization.conviction_pct


def test_to_audit_row_carries_session_metadata() -> None:
    card = _make_card()
    row = to_audit_row(card)
    assert row.session_type == "pre_londres"
    assert row.asset == "EUR_USD"
    assert row.regime_quadrant == "haven_bid"
    assert row.bias_direction == "short"
    assert row.source_pool_hash == card.source_pool_hash
    assert row.critic_verdict == "approved"


def test_to_audit_row_jsonb_columns_are_lists_or_dicts() -> None:
    card = _make_card()
    row = to_audit_row(card)
    assert isinstance(row.mechanisms, list)
    assert isinstance(row.invalidations, list)
    assert isinstance(row.catalysts, list)
    assert isinstance(row.correlations_snapshot, dict)
    assert isinstance(row.polymarket_overlay, list)
    assert isinstance(row.critic_findings, list)
    # Defensive copy : mutating the row must not affect the source
    row.mechanisms.append({"injected": True})
    assert all("injected" not in m for m in card.specialization.mechanisms)


def test_to_audit_row_realized_columns_blank() -> None:
    """Outcome reconciler fills these later."""
    row = to_audit_row(_make_card())
    assert row.realized_close_session is None
    assert row.realized_at is None
    assert row.brier_contribution is None
