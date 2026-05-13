"""gepa_candidate_prompts — Phase D W117b sub-wave .b (ADR-091).

ORM model for the GEPA optimizer candidate-prompt persistence table.
Schema in `migrations/0047_gepa_candidate_prompts.py`. See
`docs/decisions/ADR-091-w117b-gepa-prompt-optimization.md` §Invariant 6.

Append-only on insert ; the `status` column is the only mutable
surface via the W117b.g adoption admin endpoint (sets the sanctioned
`ichor.audit_purge_mode='on'` GUC in the same transaction).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GepaCandidatePrompt(Base):
    """One row per GEPA candidate prompt.

    Surrogate UUID PK on `id` ; the natural key (pocket coords +
    pass_kind + generation + gepa_run_id) is enforced by UNIQUE
    constraint at the DB level.

    `fitness_score` is NULLABLE on pre-evaluation rows (the GEPA
    optimizer inserts the candidate before computing fitness). Once
    fitness is computed, the value is HARD-ZERO contract per ADR-091
    amended round-32 §"Invariant 2" : any `adr017_violations > 0`
    forces `status = 'rejected'`, enforced by CHECK constraint
    `ck_gepa_candidate_adr017_hard_zero`.
    """

    __tablename__ = "gepa_candidate_prompts"
    __table_args__ = (
        UniqueConstraint(
            "pocket_asset",
            "pocket_regime",
            "pocket_session_type",
            "pass_kind",
            "generation",
            "gepa_run_id",
            name="uq_gepa_candidate_pocket_generation_run",
        ),
        CheckConstraint(
            "pass_kind IN ('regime', 'asset', 'stress', 'invalidation')",
            name="ck_gepa_candidate_pass_kind",
        ),
        CheckConstraint(
            "status IN ('candidate', 'adopted', 'rejected', 'archived')",
            name="ck_gepa_candidate_status",
        ),
        CheckConstraint(
            "generation >= 0",
            name="ck_gepa_candidate_generation_nonneg",
        ),
        CheckConstraint(
            "char_length(prompt_text) >= 8 AND char_length(prompt_text) <= 32768",
            name="ck_gepa_candidate_prompt_size",
        ),
        CheckConstraint(
            "adr017_violations >= 0",
            name="ck_gepa_candidate_adr017_violations_nonneg",
        ),
        CheckConstraint(
            "adr017_violations = 0 OR status = 'rejected'",
            name="ck_gepa_candidate_adr017_hard_zero",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    gepa_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    pocket_asset: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pocket_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pocket_session_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pass_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    fitness_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 5), nullable=True)
    adr017_violations: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'candidate'")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
