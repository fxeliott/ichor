"""audit_log immutable trigger — block UPDATE + DELETE except via the
sanctioned purge path.

Rationale (ADR-029 §AMF + EU AI Act Art. 12 / MiFID Art. 16) :
the audit_log is the source of truth for "what happened, when, by
whom" on every state-changing API call. If rows can be silently
amended or deleted, the audit trail is worthless for any
compliance-grade question.

Mechanism : a BEFORE UPDATE OR DELETE trigger raises an exception
unless the connection's `ichor.audit_purge_mode` GUC is set to
`'on'`. The nightly retention job (`services.audit_log.purge_older_than`)
sets this GUC via `SET LOCAL` so its single DELETE statement is
authorised, and only for the duration of the transaction.

Any other path (rogue admin SQL, application bug, wedged migration)
trying to mutate or delete rows will fail with a clear error :

    ERROR: audit_log is append-only — UPDATE/DELETE are reserved for
    the sanctioned purge path (set `ichor.audit_purge_mode=on` in the
    same transaction). HINT : if you really need this, see
    services/audit_log.purge_older_than.

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FUNCTION_BODY = """
CREATE OR REPLACE FUNCTION audit_log_block_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    purge_mode text;
BEGIN
    -- current_setting(name, missing_ok) returns NULL when the GUC isn't set,
    -- so we default to 'off' for safety.
    purge_mode := COALESCE(current_setting('ichor.audit_purge_mode', true), 'off');
    IF purge_mode = 'on' THEN
        -- Sanctioned purge path. Allow the row through.
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION
      'audit_log is append-only — UPDATE/DELETE are reserved for the sanctioned purge path (set `ichor.audit_purge_mode=on` in the same transaction). HINT: see services/audit_log.purge_older_than.'
      USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""


def upgrade() -> None:
    op.execute(_FUNCTION_BODY)
    op.execute(
        """
        CREATE TRIGGER audit_log_immutable_trigger
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW
        EXECUTE FUNCTION audit_log_block_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutable_trigger ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_mutation();")
