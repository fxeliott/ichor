"""rag_align_adr086 — bring `rag_chunks_index` in line with ADR-086 contract.

Discovery 2026-05-12 (post-W110c smoke embed) : the production table
`rag_chunks_index` pre-existed Alembic and was created with a schema
that drifts from ADR-086 :

  * `id` column has NO `DEFAULT gen_random_uuid()` → every INSERT
    needed an explicit UUID. The W110c bulk-embed runner relied on
    the default → NotNullViolation on row 1.
  * CHECK constraint allows `'card','briefing','post_mortem',
    'critic_finding'` — but ADR-086 + W110c writers emit
    `'session_card'`. The constraint silently rejected every row.

The table is EMPTY on Hetzner at the time of this migration (verified
via `SELECT count(*) FROM rag_chunks_index;` returning 0). So we can
ALTER the contract without a data backfill.

Bringing the constraint to the ADR-086 canonical set :

    {'session_card','post_mortem','briefing','adr','runbook'}

`critic_finding` was speculative + never written ; replaced by `adr`
and `runbook` which match the ADR-086 §"Source types" list verbatim.
The `card` legacy literal is dropped because no caller writes it.

Idempotent : the up-migration uses DROP IF EXISTS / IF NOT EXISTS
patterns so re-running on a freshly migrated DB is a no-op.

Revision ID: 0041
Revises: 0040
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Default UUID generator on `id`. `gen_random_uuid()` is provided
    #    by the pgcrypto extension (already installed by migration 0040).
    op.execute("ALTER TABLE rag_chunks_index ALTER COLUMN id SET DEFAULT gen_random_uuid()")

    # 2. CHECK constraint realignment. The constraint name used by the
    #    pre-existing Hetzner table was the autogen-ed
    #    `rag_chunks_index_source_type_check` — we drop it AND any
    #    explicitly-named copy (`ck_rag_chunks_source_type`) to keep
    #    the up-migration idempotent across drift permutations.
    op.execute(
        "ALTER TABLE rag_chunks_index DROP CONSTRAINT IF EXISTS rag_chunks_index_source_type_check"
    )
    op.execute("ALTER TABLE rag_chunks_index DROP CONSTRAINT IF EXISTS ck_rag_chunks_source_type")
    op.execute(
        "ALTER TABLE rag_chunks_index "
        "ADD CONSTRAINT ck_rag_chunks_source_type "
        "CHECK (source_type IN "
        "('session_card','post_mortem','briefing','adr','runbook'))"
    )


def downgrade() -> None:
    # Restore the constraint to the pre-W110c shape so a 0040 rollback
    # stays consistent. The id DEFAULT is left in place because dropping
    # it on a populated table could break running INSERTs.
    op.execute("ALTER TABLE rag_chunks_index DROP CONSTRAINT IF EXISTS ck_rag_chunks_source_type")
    op.execute(
        "ALTER TABLE rag_chunks_index "
        "ADD CONSTRAINT rag_chunks_index_source_type_check "
        "CHECK (source_type IN "
        "('card','briefing','post_mortem','critic_finding'))"
    )
