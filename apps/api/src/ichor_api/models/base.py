"""SQLAlchemy 2.0 declarative base + common columns."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Naming convention: improves Alembic autogenerate diffs
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    # server_default mirrors migration 0001 (created_at/updated_at
    # server_default=sa.func.now()) on every consumer — briefings (0001:29-33),
    # alerts (0001:56-60), predictions_audit (0001:95-99), bias_signals
    # (0001:130-134). Without it, env.py compare_server_default=True makes
    # alembic autogenerate emit a spurious "drop server default" diff. The
    # Python `default`/`onupdate` still win at INSERT/UPDATE — this is
    # metadata-only (same discipline as the per-model created_at alignments).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
