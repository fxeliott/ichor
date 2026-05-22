"""Verify the degraded_inputs column was added to session_card_audit
(migration 0050, ADR-104 / ADR-099 §T3.2).

The DELIBERATE tri-state honesty divergence from key_levels/scenarios is
pinned here as a regression guard: degraded_inputs is NULLABLE with NO
server_default, so a pre-0050 card reads NULL ("liveness not tracked at
this card's generation" — honest "unknown") rather than a backfilled
"[]" that would falsely assert "all critical anchors fresh". That false
assertion is the exact silent-skip dishonesty ADR-103 exists to kill.
"""

from __future__ import annotations

from ichor_api.models import SessionCardAudit


def test_degraded_inputs_column_present() -> None:
    cols = {c.name for c in SessionCardAudit.__table__.columns}
    assert "degraded_inputs" in cols, "migration 0050 should have added degraded_inputs"


def test_degraded_inputs_column_nullable() -> None:
    """Legacy/pre-0050 rows stay valid as NULL — the honest 'not tracked
    at generation' state (ADR-104 tri-state)."""
    col = SessionCardAudit.__table__.columns["degraded_inputs"]
    assert col.nullable is True


def test_degraded_inputs_column_has_no_server_default() -> None:
    """The core ADR-104 honesty pin. UNLIKE key_levels (0049) /
    scenarios (0039) which are NOT NULL DEFAULT '[]'::jsonb,
    degraded_inputs has NO server_default: NULL must mean 'unknown',
    never the falsely-clean 'all fresh' a '[]' backfill would imply."""
    col = SessionCardAudit.__table__.columns["degraded_inputs"]
    assert col.server_default is None


def test_degraded_inputs_uses_jsonb_type() -> None:
    from sqlalchemy.dialects.postgresql import JSONB

    col = SessionCardAudit.__table__.columns["degraded_inputs"]
    assert isinstance(col.type, JSONB)
