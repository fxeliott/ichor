"""empirical_reaction_betas — Engine 8 axis-4 +1 LEVEL DEPTH r160 foundation.

Per-(event_class, instrument) empirical reaction-beta storage : the |drift|bp
magnitude observed in a fixed pre-event window over an N-event history. This
table is the **persistence layer that replaces literature priors** in Engine
8 magnitude computation — when a row exists for (event_class, instrument),
the engine reads p50_drift_bp from here instead of `EVENT_CLASS_BASELINE_BP`
literature_prior dict. Closes the cold-start caveat that has fired on every
Engine 8 emission since r147.

**Eliot r159 directive unlock context** : "déjà ichor est usage perso" →
Dukascopy ToU "personal non-commercial use only" license MATCHES Ichor pre-
trade research framing. Pattern #15 LICENSE blocker (r157 R59 rejected
Dukascopy backfill) is empirically RESOLVED — r160 ships the foundation
table + service contract + Engine 8 graceful-degradation. r161+ ships the
actual Dukascopy bi5 fetcher + 3y backfill EURUSD × NFP via PAYEMS dates.

**Architecture-first scoping rationale** (doctrine #2 strict scope + token-
budget reality post-5-round session r155-r159) :

  - r160 = FOUNDATION : alembic migration + service contract + Engine 8
    graceful-degradation + tests pinning the contract. NO actual data
    fetch yet — table starts EMPTY, Engine 8 falls back to literature
    prior 100% (zero behavior change vs r159 output).
  - r161+ = EXECUTION : Dukascopy bi5 fetcher service + CLI backfill +
    populate table + Engine 8 flips to empirical-first naturally as rows
    appear.

This sequencing mirrors W83-W87 Cap5 (PRE-1 / PRE-2 / STEP-1 / STEP-2 /
STEP-3 / STEP-4 / STEP-5 / STEP-6) — foundation first, then progressive
empirical population.

**Why historical-trace shape** : one row per `(event_class, instrument,
computed_at)` (NOT a single-row-per-(class, instrument) upsert). Preserves
audit trail of backfill recomputes (e.g., r161 initial 1y backfill →
r162+ 3y extension → r163+ 5y extension). Mirror r51 tempo_thresholds
historical-trace pattern.

**Methodology stamps in the table** : `window_minutes_before` +
`window_minutes_after` columns explicitly store the event-window choice
(per Pattern #15 r158 R59 ABDV-2003 5-min canonical methodology —
Andersen, Bollerslev, Diebold & Vega 2003, "Micro Effects of Macro
Announcements: Real-Time Price Discovery in Foreign Exchange",
*American Economic Review* 93(1):38-62, DOI 10.1257/000282803321455151
[r161 Pattern #13 citation completion : r160 docstring referenced
ABDV-2003 by name without primary-source journal/DOI ; Agent I r161
R59 Phase 0 caught the gap pre-emptively even though no false-journal
attribution was committed]). Future methodology evolution (e.g., r170+
1-min granular vs r160 5-min coarse) recorded directly in the row —
Engine 8 can pick the best-methodology match if multiple rows present.

**Schema invariants (defense-in-depth, ADR-029 class hardening)** :

  - `n_observations >= 1` — never store empty calibrations
  - `p50_drift_bp >= 0` — magnitude is always |abs| (sign stripped per
    r142 trader RED-1 doctrine, ADR-017 boundary preserved)
  - `p75_drift_bp >= p50_drift_bp >= 0` — monotonic percentile ordering
  - `p90_drift_bp >= p75_drift_bp` — same
  - `window_minutes_before >= 1` + `window_minutes_after >= 0` —
    methodologically defensible window endpoints
  - `event_class` FK-less reference to `EVENT_CLASS_BASELINE_BP` dict
    keys (validated service-layer side via `event_proximity_engine.py`
    constant ; no DB-level FK because the dict is Python code, not a
    table — same pattern as r51 tempo_thresholds.asset)

**NOT a TimescaleDB hypertable** — small table (17 event classes × 5
instruments × backfill recomputes ≤ ~10/year = ~850 rows/year ceiling).
Regular Postgres + compound `(event_class, instrument, computed_at DESC)`
index covers the "latest per (class, instrument)" query that the service
runs on every Engine 8 invocation.

**ADR-017 boundary preserved** : the table stores ABSOLUTE-value magnitudes
(p50/p75/p90 are |drift|bp, always >= 0). The Engine 8 caller applies
business_cycle_sign downstream — same architecture as literature_prior
path. No directional information leaks at the DB layer.

ADR refs : ADR-099 §Impl(r160) — Mission centrale Axis-4 +1 LEVEL DEPTH
foundation ; Pattern #17 formal DOCTRINE r159 graduates to empirical
calibration path here.

Revision ID: 0053
Revises: 0052
Create Date: 2026-05-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "empirical_reaction_betas",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # event_class must match an EVENT_CLASS_BASELINE_BP dict key in
        # event_proximity_engine.py. Service-layer validates ; no DB-level
        # FK because EVENT_CLASS_BASELINE_BP is Python code, not a table.
        # Same pattern as r51 tempo_thresholds.asset (validated app-side).
        sa.Column("event_class", sa.String(64), nullable=False),
        # instrument code — Dukascopy URL slug for empirical match (e.g.,
        # "eurusd", "gbpusd", "xauusd", "usa500idxusd", "usatechidxusd").
        # The bi5 collector uses this directly in the
        # `datafeed.dukascopy.com/datafeed/{INSTRUMENT}/...` URL pattern.
        sa.Column("instrument", sa.String(32), nullable=False),
        # methodology window endpoints (Pattern #15 r158 R59 ABDV-2003
        # canonical = 5min pre-event ; r160 stores explicitly per row
        # so r161+ methodology evolution (e.g., 1-min granular vs 5-min
        # coarse) is recorded directly without schema migration.
        sa.Column("window_minutes_before", sa.Integer(), nullable=False),
        sa.Column("window_minutes_after", sa.Integer(), nullable=False),
        # sample size — number of events in the backfill window. Used by
        # Engine 8 to apply `low_signal_confidence` sentinel when n < 30
        # (Pattern #17 doctrine ; trader r157 + r159 multi-application
        # discipline source-level requires honest sample-size disclosure).
        sa.Column("n_observations", sa.Integer(), nullable=False),
        # empirical percentile magnitudes — |drift|bp absolute value.
        # ADR-017 boundary preserved : sign stripped at this layer ;
        # business_cycle_sign applied downstream by caller (parity with
        # literature_prior path r147+).
        sa.Column("p50_drift_bp", sa.Numeric(8, 3), nullable=False),
        sa.Column("p75_drift_bp", sa.Numeric(8, 3), nullable=False),
        sa.Column("p90_drift_bp", sa.Numeric(8, 3), nullable=False),
        # source — for audit trail. Initial r161+ backfill = "dukascopy_1min" ;
        # future hybrid backfills may use other sources (e.g., polygon_intraday
        # if Ichor ever subscribes ; Stooq 5min for short windows).
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_empirical_reaction_betas"),
        sa.UniqueConstraint(
            "event_class",
            "instrument",
            "window_minutes_before",
            "window_minutes_after",
            "computed_at",
            name="uq_empirical_reaction_betas_full_key",
        ),
        # Schema invariants (Pattern #29 ADR class hardening) :
        sa.CheckConstraint(
            "n_observations >= 1",
            name="ck_empirical_reaction_betas_sample_positive",
        ),
        sa.CheckConstraint(
            "p50_drift_bp >= 0",
            name="ck_empirical_reaction_betas_p50_nonneg",
        ),
        sa.CheckConstraint(
            "p75_drift_bp >= p50_drift_bp",
            name="ck_empirical_reaction_betas_p75_monotonic",
        ),
        sa.CheckConstraint(
            "p90_drift_bp >= p75_drift_bp",
            name="ck_empirical_reaction_betas_p90_monotonic",
        ),
        sa.CheckConstraint(
            "window_minutes_before >= 1",
            name="ck_empirical_reaction_betas_window_before_min",
        ),
        sa.CheckConstraint(
            "window_minutes_after >= 0",
            name="ck_empirical_reaction_betas_window_after_nonneg",
        ),
    )
    # Compound desc index — supports the "latest per (event_class, instrument)"
    # query the service runs on every Engine 8 invocation. Postgres uses this
    # index for DISTINCT ON queries too.
    op.create_index(
        "ix_empirical_reaction_betas_class_instrument_computed_at_desc",
        "empirical_reaction_betas",
        ["event_class", "instrument", sa.text("computed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_empirical_reaction_betas_class_instrument_computed_at_desc",
        table_name="empirical_reaction_betas",
    )
    op.drop_table("empirical_reaction_betas")
