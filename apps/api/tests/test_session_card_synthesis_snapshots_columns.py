"""Verify the S04 synthesis-snapshot columns were added to session_card_audit
(migration 0055, « kill the 50/50 »).

confluence_snapshot / theme_snapshot / dollar_snapshot freeze the synthesis
reads at card generation so the apex verdict conviction fusion is reproducible
at read-time. They mirror the 0050 degraded_inputs tri-state honesty pin:
NULLABLE with NO server_default, so a pre-0055 card (or a capture failure)
reads NULL = "synthesis not captured at generation" — and the verdict fuser
degrades to the bucket-only conviction — rather than a backfilled "{}" that
would falsely assert "synthesis computed and neutral" (doctrine #11).
"""

from __future__ import annotations

import pytest
from ichor_api.models import SessionCardAudit
from sqlalchemy.dialects.postgresql import JSONB

_S04_SNAPSHOT_COLUMNS = ("confluence_snapshot", "theme_snapshot", "dollar_snapshot")


@pytest.mark.parametrize("name", _S04_SNAPSHOT_COLUMNS)
def test_synthesis_snapshot_column_present(name: str) -> None:
    cols = {c.name for c in SessionCardAudit.__table__.columns}
    assert name in cols, f"migration 0055 should have added {name}"


@pytest.mark.parametrize("name", _S04_SNAPSHOT_COLUMNS)
def test_synthesis_snapshot_column_nullable(name: str) -> None:
    """Legacy / pre-0055 rows stay valid as NULL — the honest 'not captured
    at generation' state the fuser degrades on."""
    assert SessionCardAudit.__table__.columns[name].nullable is True


@pytest.mark.parametrize("name", _S04_SNAPSHOT_COLUMNS)
def test_synthesis_snapshot_column_has_no_server_default(name: str) -> None:
    """The honesty pin (mirror of degraded_inputs 0050). NO server_default:
    NULL must mean 'not captured', never a falsely-clean backfilled default."""
    assert SessionCardAudit.__table__.columns[name].server_default is None


@pytest.mark.parametrize("name", _S04_SNAPSHOT_COLUMNS)
def test_synthesis_snapshot_column_uses_jsonb_type(name: str) -> None:
    assert isinstance(SessionCardAudit.__table__.columns[name].type, JSONB)
