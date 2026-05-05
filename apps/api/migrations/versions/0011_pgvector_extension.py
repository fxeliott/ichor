"""pgvector — install the `vector` extension.

Pre-requisite for `0012_rag_chunks_index` (RAG storage with HNSW index).

The Postgres role used by Alembic must have CREATE privilege on the database.
On Hetzner the `ichor` role is database owner, so this is implicit. Locally,
make sure `pgvector` is installed at the OS level (Postgres 16+ via apt:
`postgresql-16-pgvector`, or build from source for older distros).

This migration is split from the table creation so a `downgrade()` of the
table doesn't drop the extension (which may be in use by other schemas).

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Intentionally do NOT drop the extension on downgrade: it may be in use
    # by other tables (created in later migrations) and dropping it cascades.
    # If a full uninstall is needed, do it manually after dropping all
    # dependent tables.
    pass
