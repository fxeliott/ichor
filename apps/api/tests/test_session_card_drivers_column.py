"""Verify the drivers column was added to session_card_audit (migration 0026)."""

from __future__ import annotations

from ichor_api.models import SessionCardAudit


def test_drivers_column_present() -> None:
    cols = {c.name for c in SessionCardAudit.__table__.columns}
    assert "drivers" in cols, "migration 0026 should have added the drivers column"


def test_drivers_column_nullable() -> None:
    """Existing rows must stay valid — drivers is back-fill optional."""
    col = SessionCardAudit.__table__.columns["drivers"]
    assert col.nullable is True


def test_drivers_uses_jsonb_type() -> None:
    from sqlalchemy.dialects.postgresql import JSONB

    col = SessionCardAudit.__table__.columns["drivers"]
    assert isinstance(col.type, JSONB)
