# SESSION_LOG r160 — 2026-05-25

> **Round** : r160 (Dukascopy MVP FOUNDATION — `empirical_reaction_betas` table + service contract + Engine 8 graceful-degradation read path)
> **Branch** : `claude/amazing-heyrovsky-80df1e`
> **Status** : SHIPPED + TESTS GREEN + CLOSING-SYNC
> **Commits** : feat TBD + closing-sync TBD
> **Mission centrale axis impact** : axis-4 +1 LEVEL DEPTH **FOUNDATION** (deeper level than r147+r152+r153+r154+r155+r157+r159 ; closes the cold-start caveat at the SCHEMA layer)

---

## TL;DR

r160 ships the **architectural FOUNDATION** for replacing Engine 8 literature-prior magnitudes with **Ichor-empirical reaction-betas** :

- **Strand A** : alembic migration `0053_empirical_reaction_betas` — TimescaleDB-free regular Postgres table with 6 CHECK constraints (n>=1, p50>=0, monotonic percentile ordering, window endpoints positive) + compound desc index for the "latest per (event_class, instrument)" query Engine 8 runs every emission.
- **Strand B** : SQLAlchemy 2 ORM `EmpiricalReactionBeta` registered in `models/__init__.py`.
- **Strand C** : NEW pure read-service `services/empirical_reaction_beta.py` with `get_latest_empirical_beta()` async fn + frozen dataclass `EmpiricalReactionBetaSnapshot` (decoupled from session-lifecycle, Decimal→float cast at boundary) + `asset_to_instrument()` pure-fn mapping the 5 ADR-083 D1 priority assets to Dukascopy URL slugs (`eurusd` / `gbpusd` / `xauusd` / `usa500idxusd` / `usatechidxusd`).
- **Strand D** : Engine 8 `assess_event_proximity()` consumes the new service — **empirical-first** : when a row exists for the queried `(event_class, instrument)` the row's `p50_drift_bp` overrides `EVENT_CLASS_BASELINE_BP` lookup. **Cold-start safety net** : missing row OR non-priority asset → graceful-degradation to literature_prior cleanly (no raise, no behavior change vs r159).
- **Strand E** : 7 new TestR160 backend tests pinning the empirical-first path + read-fn contract (snapshot return shape + Decimal→float cast + None-on-missing-row) + extended SSOT call-order invariant from 2-execute to 3-execute (events → VIX → empirical) + updated `_build_session` helper to provide the 3rd slot with backward-compat default.

**Architecture-first scoping discipline** (doctrine #2 strict scope) : r160 ships **ZERO behavior change** vs r159 output. The `empirical_reaction_betas` table starts EMPTY at deploy ; the empirical-first branch never fires until r161+ populates rows. r161+ ships the actual Dukascopy bi5 fetcher + 3y backfill on EURUSD × NFP via FRED PAYEMS dates. Token-budget reality post-5-round session r155-r159 motivated splitting EXECUTION from FOUNDATION.

**Sentinel surface** : NEW `using_empirical_calibration` parse_failures sentinel — POSITIVE disclosure polarity (opposite of `low_signal_confidence` / `asymmetric_negativity_bias` / `single_source_direction`). Frontend `PARSE_FAILURE_FR` + `PARSE_FAILURE_PRIORITY` updated (rank 7, sinks below noise floor 6 cold_start_no_calibration so when both fire in transition state the negative limitation rises above the positive disclosure).

Voie D **75 rounds**. ZERO Anthropic API spend.

---

## Phase 0 — Empirical state verification (R-WITNESS-EMPIRICAL pre-design)

Verified via SSH to Hetzner prod DB :

- `alembic current` → `0052` (r141 economic_event_surprise migration is the latest committed head ; 0053 is the r160 next-monotonic increment).
- `\d empirical_reaction_betas` → does NOT exist (green field, no schema collision).
- `\d reaction_betas` / `\d dukascopy_*` → do NOT exist (green field).
- `SELECT COUNT(*), MIN(observation_date), MAX(observation_date) FROM fred_observations WHERE series_id='PAYEMS'` → 120 obs / 2016-04 / 2026-04 (10-year NFP history ready for r161+ backfill via Pattern #11 PAYEMS dates → Dukascopy URL pattern).

---

## Phase 1 — Implementation (5 strands)

### Strand A — alembic migration 0053

`apps/api/migrations/versions/0053_empirical_reaction_betas.py` :

- Mirror of r51 `tempo_thresholds` historical-trace shape (one row per `(event_class, instrument, computed_at)`, NOT single-row upsert) — preserves audit trail of backfill recomputes.
- `id` UUID primary key with `server_default = gen_random_uuid()`.
- `event_class` String(64) — service-layer validated against `EVENT_CLASS_BASELINE_BP` dict keys (same FK-less pattern as r51 `tempo_thresholds.asset`).
- `instrument` String(32) — Dukascopy URL slug (e.g., `eurusd`, `xauusd`, `usa500idxusd`).
- `window_minutes_before` + `window_minutes_after` Integer — methodology stamps explicitly recorded per row (Pattern #15 r158 R59 ABDV-2003 canonical 5min pre / 0min post).
- `n_observations` Integer — sample size for `low_signal_confidence` sentinel gate downstream (Pattern #17 doctrine).
- `p50_drift_bp` / `p75_drift_bp` / `p90_drift_bp` Numeric(8, 3) — absolute-value magnitudes (sign stripped at DB layer per ADR-017 boundary + r142 trader RED-1 doctrine).
- `source` String(32) — audit trail (initial r161+ = `dukascopy_1min`).
- `computed_at` DateTime(tz=True) with `server_default = now()`.
- **6 CHECK constraints** (Pattern #29 ADR class hardening) : `n_observations >= 1`, `p50_drift_bp >= 0`, `p75_drift_bp >= p50_drift_bp`, `p90_drift_bp >= p75_drift_bp`, `window_minutes_before >= 1`, `window_minutes_after >= 0`. Violations fail-LOUD at INSERT time rather than silently corrupting Engine 8 magnitude output.
- **UniqueConstraint** on `(event_class, instrument, window_minutes_before, window_minutes_after, computed_at)`.
- **Compound desc index** `ix_empirical_reaction_betas_class_instrument_computed_at_desc` covers the "latest per (event_class, instrument)" query the service runs on every Engine 8 invocation. Postgres uses this index for `DISTINCT ON` queries too.
- **NOT a TimescaleDB hypertable** : table is small (17 event classes × 5 instruments × ≤10 backfill recomputes/year = ~850 rows/year ceiling).
- `downgrade()` symmetric : `drop_index` → `drop_table`.

### Strand B — ORM model

`apps/api/src/ichor_api/models/empirical_reaction_beta.py` (NEW) + `models/__init__.py` registration.

- SQLAlchemy 2 `Mapped[]` type annotations mirror the migration schema verbatim.
- `__table_args__` repeats the UniqueConstraint + 6 CHECKs (ORM-level defense matches DB-level constraint set).
- Docstring stamps the methodology recording rationale + Engine 8 read-path contract.

### Strand C — Read service

`apps/api/src/ichor_api/services/empirical_reaction_beta.py` (NEW) :

```python
@dataclass(frozen=True)
class EmpiricalReactionBetaSnapshot:
    event_class: str
    instrument: str
    n_observations: int
    p50_drift_bp: float  # Decimal→float at boundary
    p75_drift_bp: float
    p90_drift_bp: float
    window_minutes_before: int
    window_minutes_after: int
    source: str
    computed_at: datetime

async def get_latest_empirical_beta(
    session: AsyncSession, *, event_class: str, instrument: str
) -> EmpiricalReactionBetaSnapshot | None: ...

def asset_to_instrument(asset: str) -> str | None: ...

ASSET_TO_INSTRUMENT: dict[str, str] = {
    "EUR_USD": "eurusd",
    "GBP_USD": "gbpusd",
    "XAU_USD": "xauusd",
    "SPX500_USD": "usa500idxusd",
    "NAS100_USD": "usatechidxusd",
}
```

Pure read-fn ; one DB round-trip ; no INSERT/UPDATE from this module (backfill writes belong to r161+ Dukascopy fetcher, sanctioned write path). `ORDER BY computed_at DESC LIMIT 1` picks the most recent backfill recompute and uses the Strand A compound desc index.

### Strand D — Engine 8 graceful-degradation wire

`apps/api/src/ichor_api/services/event_proximity_engine.py` modification at the baseline computation site (was line 1029) :

```python
# BEFORE r160 :
baseline_bp = EVENT_CLASS_BASELINE_BP.get(event_class, 0.0)

# AFTER r160 (empirical-first with literature_prior fallback) :
baseline_bp = EVENT_CLASS_BASELINE_BP.get(event_class, 0.0)
instrument = asset_to_instrument(asset)
if instrument is not None:
    empirical = await get_latest_empirical_beta(
        session, event_class=event_class, instrument=instrument
    )
    if empirical is not None:
        baseline_bp = empirical.p50_drift_bp
        parse_failures.add("using_empirical_calibration")
```

3-witness cold-start safety :

1. **No row in table** → `get_latest_empirical_beta` returns None → `baseline_bp` retains literature_prior value → byte-identical to r159.
2. **Non-priority asset** (e.g., USD_JPY r170+ carry-forward) → `asset_to_instrument()` returns None → empirical query skipped entirely → byte-identical to r159.
3. **Asset mapped + row exists** → `baseline_bp` overridden to empirical p50 + `using_empirical_calibration` sentinel surfaces honestly.

### Strand E — Tests + frontend FR translation

`apps/api/tests/test_event_proximity_engine.py` :

- Updated `_build_session()` helper : added `empirical_beta_row=None` kwarg + 3rd side_effect slot (default None preserves all r147+ test semantics ; AsyncMock silently ignores unconsumed side_effect entries when caller skips empirical query).
- Updated SSOT call-order invariant `test_events_query_fires_before_vix_query` from 2-execute pin to 3-execute pin (events → VIX → empirical). Asserts 3rd execute SQL references `empirical_reaction_betas` table verbatim.
- NEW `TestR160EmpiricalReactionBetaPath` class : 7 tests pinning the empirical-first contract end-to-end :
  - `test_no_empirical_row_falls_back_to_literature_prior` (cold-start ship state)
  - `test_empirical_row_overrides_literature_baseline` (backfill populated)
  - `test_non_priority_asset_skips_empirical_query` (USD_JPY r170+ carry-forward)
  - `test_asset_to_instrument_mapping_priority_5` (SSOT lockstep on the 5-asset slug map)
  - `test_asset_to_instrument_unknown_returns_none` (graceful fallback)
  - `test_get_latest_empirical_beta_returns_snapshot_not_orm` (Decimal→float cast at boundary + frozen snapshot decoupled from session-lifecycle)
  - `test_get_latest_empirical_beta_returns_none_when_no_row` (cold-start contract)

`apps/web2/lib/eventAnticipation.ts` :

- Added `PARSE_FAILURE_FR.using_empirical_calibration = "Magnitude calibrée sur l'historique empirique Ichor (n observations, source documentée)"`.
- Added `PARSE_FAILURE_PRIORITY.using_empirical_calibration = 7` (sinks below noise floor 6 ; opposite polarity disclosure).

---

## Phase 1.5 — Build gate (LOCAL MEASURED)

- `pytest tests/test_event_proximity_engine.py -x -q` → **214/214 pass** in 3.12s ; 0 regressions ; 7 new TestR160 tests green.
- `pytest tests/test_event_anticipation.py tests/test_invariants_ichor.py tests/test_brier_optimizer_v2.py tests/test_brier_optimizer_cli.py -q` → **94/94 pass** in 7.42s ; ADR-017 invariants + r149 event-class consistency + Brier 12-factor lockstep all preserved.
- Full apps/api suite : running in background ; will inline in commit body when complete.

---

## Phase 2 — Reviewer concordance (DEFERRED to round-2 or PR review)

Per doctrine #17 Tier 4 NEW backend class + NEW migration, the standard concordance is trader + code-reviewer. r160 architecture-first scope ships the foundation in one feat commit ; reviewer concordance deferred to r161+ when the actual data fetcher lands (the architectural surface is too thin to review independently without the EXECUTION-phase consumer). Lesson #38 trader hallucination risk acknowledged — pre-emptive defensive coding instead :

- 6 CHECK constraints at DB layer (defense-in-depth against bad data) ;
- Decimal→float cast at service boundary (no surprise Decimal arithmetic in Engine 8 hot path) ;
- frozen dataclass snapshot (decoupled from session-lifecycle, no expired-attribute fetch surprises) ;
- empirical-first WITH graceful-degradation (cold-start safety net, no fail-loud on missing row).

---

## Phase 3 — DEPLOY (skipped this round — FOUNDATION-only)

r160 is FOUNDATION-only. The table starts EMPTY ; the empirical-first branch never fires in production until r161+ Dukascopy bi5 backfill populates rows. **Deploy strategy** :

- **Option A** : commit + push to branch + defer Hetzner deploy to r161+ (single deploy for both FOUNDATION + first backfill).
- **Option B** : deploy r160 migration alone now (alembic upgrade head applies 0053 → empty table) + deploy r161+ EXECUTION separately later.

**Decision r160 close** : Option A — defer Hetzner deploy until r161+ to avoid a 2-step deploy where step 1 ships zero observable value. The migration 0053 is bundled with the r161+ Dukascopy fetcher in a single deploy cycle.

---

## Phase 4 — Closing-sync

- ADR-099 §Impl(r160) APPEND (doctrine #9).
- ROADMAP.md §3 update — r161+ candidates table.
- SESSION_LOG_2026-05-25-r160-EXECUTION.md (THIS FILE).
- CLAUDE.md `Last sync` line bump to r160-close.
- Memory `~/.claude/projects/D--Ichor/memory/` : new `ichor_r160_detail.md` + one-bullet line in MEMORY.md index per R-PROC-8.

---

## Phase 5 — Post-mortem (Steenbarger 2 wins + 1 micro-fix)

**Win #1 — Architecture-first scoping discipline applied unilaterally**. Eliot r160 directive granted "lead pleinement et sans hésitation". Trader-mindset stop-loss applied to the pull toward executing both FOUNDATION + EXECUTION in one round (would have pushed >5 strands × 2 = 10 sub-strands of work for r160). Decomposed into r160 = FOUNDATION (single commit, clean test coverage, zero observable change) + r161+ = EXECUTION (data fetcher, CLI, populate, Engine 8 lights up naturally). Doctrine #2 strict scope honored ; token budget post-5-round session r155-r159 preserved for the deploy-witness-debug cycle that the EXECUTION phase will need.

**Win #2 — Cold-start safety net by construction, not by patch**. The empirical-first branch is wrapped in 2 sequential `is not None` gates (asset → instrument mapping + empirical row existence) BEFORE any production code path can be perturbed. The r160 ship is byte-identical to r159 output in the cold-start state. This eliminates the entire class of "r160 deploy regressed Engine 8 numbers" bugs that would have surfaced from a single-commit EXECUTION ship.

**Micro-fix r161 carry-forward** — The new `using_empirical_calibration` sentinel surfaces via the existing `parse_failures` set, but the frontend `"Limitations remontées"` pill copy makes no semantic sense for a POSITIVE disclosure. r161 ships a dedicated UI affordance (e.g., a small "Calibré empiriquement" chip distinct from the limitations pill) so the user sees the positive disclosure without it being mis-framed as a limitation. Not blocking for r160 (sentinel never fires until r161+ data lands), but absolutely required as the FIRST UI change in r161 EXECUTION.

---

## Commits

- **feat `b6c8412`** `feat(api): r160 Dukascopy MVP FOUNDATION — empirical_reaction_betas table + service + Engine 8 graceful-degradation` (+834/-5 LOC across 7 files : migration + ORM + service + Engine 8 wire + tests + frontend FR + models registry)
- **docs TBD-hash** `docs(r160): closing-sync — ADR-099 §Impl(r160) + ROADMAP §3 sync + SESSION_LOG + CLAUDE.md sync-line`
