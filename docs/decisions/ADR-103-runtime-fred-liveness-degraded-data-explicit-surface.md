# ADR-103: Runtime FRED-liveness degraded-data explicit surface (ADR-099 §T3.2)

**Status**: **Accepted** (round-93, 2026-05-17) — thin child **implementing**
[ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md) §T3.2 ("Human-visible
degraded-data alert — break the silent-skip chain") under Eliot's standing full-autonomy
delegation ("autonomie totale ; décide et annonce, ne demande pas") and the per-round
default-Option contract (doctrine #10). Generalizes the **Accepted/immutable**
[ADR-093](ADR-093-aud-commodity-surface-degraded-explicit.md) _static_ "degraded explicit"
prose primitive into a _dynamic per-card runtime_ liveness audit. Implementation shipped
same round (`_fred_liveness` + `_section_data_integrity` in
`apps/api/src/ichor_api/services/data_pool.py` + `DataPoolOut` projection +
`test_data_pool_data_integrity.py`).

**Date**: 2026-05-17

**Supersedes**: none

**Extends**: [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md) §T3.2
(the explicitly-enumerated Tier-3 item) + §D-2 (the coverage contract: every layer is
COVERED **or explicitly DEGRADED — never silently absent**),
[ADR-093](ADR-093-aud-commodity-surface-degraded-explicit.md) (the "degraded explicit"
doctrinal primitive — generalized from static-prose-AUD-only to dynamic-runtime-all-assets),
[ADR-097](ADR-097-fred-liveness-nightly-ci-guard.md) (the _nightly CI_ FRED-liveness guard —
ADR-103 is its _per-card runtime_ counterpart: the same r92 `fred_age_registry` SSOT,
exercised inside `build_data_pool` instead of a GitHub Action),
[ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D — zero paid feeds, zero new
ingestion), [ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (no BUY/SELL boundary —
data-provenance vocabulary only, explicit boundary note).

**Related**: future r94 ADR for the end-user `/briefing` degraded-data badge (the
`session_card_audit` ORM→`SessionCardOut`→`api.ts`→component Pydantic-projection chain +
alembic migration — deliberately a separate round per the proven r76→r77 / r80→r81
backend-then-frontend split).

## Context

R59 inspection (round-93, file:line-verified — not the stale prompt hypothesis) mapped the
**silent-skip chain** exactly:

- `data_pool._latest_fred` (`data_pool.py:258-290`) folds `observation_date >= cutoff` into
  the SQL `WHERE`, so a series that exists but is **stale** beyond its registry max-age
  returns `row is None` — **byte-identical to a series that was never ingested**. Both
  collapse to `return None` (`data_pool.py:285-286`). The stale-vs-absent distinction is
  destroyed at the query layer.
- Each per-asset `_section_*` returns the `("", [])` sentinel when its primary FRED anchor
  is `None` (`data_pool.py:827/998/1252/1492/1676/2037`, etc.). `build_data_pool` only
  appends asset-gated sections behind `if <src>:` (`data_pool.py:4364-4428`) — **no
  else-branch, no log, no accumulation**. The skipped section never enters
  `sections_emitted`; the header (`data_pool.py:4532-4536`) still looks complete.
- The session-card path discards `pool.sections_emitted` / `pool.sources` at
  `run_session_card.py:98` (only `pool.markdown` reaches the LLM; only `source_pool_hash`
  survives into `session_card_audit`). The ADR-093 "degraded explicit" prose is **static
  markdown inside `_section_aud_specific`, emitted only when that section renders** — it is
  not a data structure, not dynamic per-driver, and is never projected.
- Concrete live instance (ADR-093 §r49 amendment, prod-DB ground-truth): **China M1
  `MYAGM1CNM189N` is DEAD since 2019-08-01**; the AUD composite driver silently drops every
  card. This is the exact failure class hand-caught for 10+ rounds.

ADR-099 §D-2 mandates "never silently absent". The gap = there is **no runtime manifest of
"what critical input was attempted but degraded"** anywhere — `DataPool` carries only the
render-positive `sections_emitted`.

## Decision

Break the silent-skip chain with a **purely additive, reversible, ADR-093-faithful**
runtime liveness surface. `_latest_fred` and every `_section_*` gate stay **byte-identical**
(no contract weakening — anti-regression; r71/r91 extract-to-SSOT discipline):

1. **`_fred_liveness(session, series_id, *, override=None) -> FredLiveness`** — a dep-light
   helper that runs the **cutoff-free** latest-observation query (the information
   `_latest_fred` destroys) and classifies `fresh | stale | absent`, judged against the r92
   `fred_age_registry` SSOT via the existing `_max_age_days_for`. Its fresh⇔not-fresh
   boundary is provably identical to `_latest_fred`'s `>= cutoff` predicate
   (`age <= max_age` ⟺ `observation_date >= today - max_age`), so "fresh" in the audit
   means exactly "the consuming section got its data". One extra cheap PK-ordered
   `LIMIT 1` query, invoked only by the always-on integrity audit.

2. **A per-asset critical-anchor SSOT registry** (`_MACRO_CORE_ANCHORS` +
   `_ASSET_CRITICAL_ANCHORS`) — the FRED series whose `None` causes a silent section-skip
   or silent sub-driver drop, derived from the **verified** `_section_*` reads (not
   guessed): macro-core régime-classifier inputs (`VIXCLS`@7 / `BAMLH0A0HYM2`@14 /
   `NFCI`@14 / `USALOLITOAASTSAM`@90 / `EXPINF1YR`@45 / `THREEFYTP10`@30 — the exact
   overrides `_section_executive_summary` passes, `data_pool.py:324-329`, audited for
   **every** asset because Pass-1 régime is universal) + per-asset anchors
   (`XAU_USD`→`DFII10`, `NAS100_USD`→`DGS10`, `SPX500_USD`→`VIXCLS`@7,
   `USD_JPY`→`IRLTLT01JPM156N`, `AUD_USD`→`IRLTLT01AUM156N` + the ADR-093 composite
   sub-drivers `MYAGM1CNM189N`/`PIORECRUSDM`/`PCOPPUSDM`, `GBP_USD`→`IRLTLT01GBM156N`).
   The audit judges liveness against the **registry** SSOT (with the well-known `VIXCLS`=7
   operative override that both the régime classifier and the SPX section use); a
   section's bespoke internal cutoff is **not** individually mirrored — an intentional,
   documented simplification (the registry is the project's canonical "too old"), not a
   silent gap.

3. **`_section_data_integrity(session, asset)` — ALWAYS rendered** (never the `("", [])`
   sentinel; appended unconditionally in `build_data_pool`, mirroring the
   `_section_key_levels` "always-rendered explicit state instead of missing data"
   doctrine, `data_pool.py:4260-4261`), **inserted at index 1** (right after
   `executive_summary`, before `macro_trinity`) so Pass-1 régime + Pass-2 are **primed**
   with data-health context first. Renders either `✅ Toutes les ancres FRED critiques
sont fraîches` (full per-series freshness list — explicit "all fresh" state, never
   missing) or `## ⚠️ Intégrité des données — DÉGRADÉ` with a per-series breakdown
   (ABSENTE/PÉRIMÉE, last obs, age vs registry threshold, impacted section/driver) + an
   ADR-017-clean boundary note ("contexte d'intégrité — lecture à fiabilité réduite sur
   les axes impactés ; pas un signal").

4. **A deterministic header line** in `build_data_pool` (`Intégrité : N entrée(s) FRED
critique(s) dégradée(s) — <ids>`) — machine-truth, LLM-independent.

5. **`DataPool.degraded_inputs: list[DegradedInput]`** (additive frozen-dataclass field,
   default `[]`) projected into `DataPoolOut` (`GET /v1/data-pool/{asset}`, operator
   transparency tool, r90-live) → **immediately operator-visible deterministically** and a
   **zero-rework foundation** for the r94 end-user badge.

### Scope boundary (explicit, calibrated-honest — lesson #2 "shipped ≠ functional")

r93 ships the **backend deterministic foundation**: degradation is now (a) deterministic &
explicit in the data-pool the LLM reasons over (primed top-of-pool + deterministic header),
and (b) operator-visible deterministically via the live `/v1/data-pool/{asset}` projection.
The **dedicated end-user `/briefing` badge** (an `EventSurpriseGauge`-style panel + the full
`session_card_audit` ORM column → `to_audit_row` → `SessionCardOut` → `api.ts` → component
chain + an alembic migration) is the **announced r94 follow-up** — bundling it here would be
the migration-blast-radius + accumulation Eliot forbids ("n'accumule pas / 1 incrément
vérifié"). ADR-099 §D-2 "never silently absent" is satisfied this round for the LLM input +
the operator surface; the end-user-UI satisfaction is r94.

## Acceptance criteria

1. `_fred_liveness` classifies `fresh`/`stale`/`absent` correctly via the cutoff-free
   query; its `fresh` boundary is unit-proven identical to `_latest_fred` returning a row
   on the same fixture (byte-consistency invariant).
2. `_section_data_integrity` is in `sections_emitted` for **every** asset (always-rendered,
   never the `("", [])` sentinel) — including an asset with no per-asset anchor map
   (e.g. `USD_CAD`).
3. Class-A asset-gating skips (`asset != "X"`) are **never** reported as degraded (the
   audit inspects FRED anchors, not section asset-gates).
4. `is_adr017_clean(rendered_text)` returns True on both the all-fresh and the DÉGRADÉ
   render.
5. `_latest_fred` semantics + every `_section_*` gate are byte-identical (regression:
   existing `test_fred_frequency_registry` + per-asset section tests pass unchanged).
6. Empirical 3-witness (rule 18): ≥10 unit tests pass; ADR-017 canary True; post-deploy
   `GET /v1/data-pool/{asset}` includes the `data_integrity` section + `degraded_inputs`
   computed from live prod FRED rows.
7. **No new collector / migration / ORM / cron / FRED series** — pure runtime audit over
   already-ingested `fred_observations`. `git revert <commit>` + `redeploy-api.sh rollback`
   fully reverse it.

## Reversibility

Pure additions to `data_pool.py` (`FredLiveness`/`DegradedInput` dataclasses + `_fred_liveness`

- the 2 anchor registries + `_section_data_integrity` + 3 lines in `build_data_pool` + the
  `DataPool.degraded_inputs` defaulted field) + `routers/data_pool.py` (`DegradedInputOut` +
  one projection line) + one new test file + this ADR. The new `DataPool` field defaults `[]`
  → no consumer breaks. `git revert <commit>` fully reverses; `redeploy-api.sh rollback`
  reverses the deploy in <30 s. No Hetzner schema/migration/cron touched.

## Consequences

### Positive

- **The silent-skip chain is broken.** A dead/stale critical FRED anchor (the China-M1
  class hand-caught 10+ rounds) is now **deterministically and explicitly surfaced every
  card** — primed into the LLM's pool, machine-truth in the header, operator-visible via
  `/v1/data-pool`. ADR-099 §D-2 "never silently absent" honored for the LLM + operator
  surface.
- **ADR-093 generalized correctly**: its static AUD-only prose primitive becomes a dynamic
  all-asset runtime audit, without amending the immutable ADR-093 (new child ADR — the
  doctrinally correct vehicle, ADR-101/102 precedent).
- **Zero blast radius**: no ingestion/migration/cron; `_latest_fred` byte-identical;
  asset-gated sections untouched; additive defaulted field. `redeploy-api.sh` (vetted).

### Negative

- **End-user `/briefing` badge deferred to r94** (honestly stated, not silently dropped) —
  the r93 human-visibility is LLM-mediated + operator-surface, not yet a dedicated
  end-user panel.
- **Non-FRED EUR-Bund anchor not audited** (`_section_eur_specific` reads
  `BundYieldObservation`, a separate table with no max-age cutoff — "absent-only", not
  stale-collapsed). Documented future extension; out of FRED-liveness scope this round.
- Section-internal bespoke cutoffs are judged against the registry SSOT, not individually
  mirrored (intentional simplification, §Decision-2).

### Neutral

- No Voie D / ADR-017 risk (data-provenance vocabulary only, boundary note present);
  existing prod untouched (additive); all existing Accepted ADRs remain valid.

## Sources (round-93 R59 audit trail — file:line, tool-verified)

- `data_pool.py:258-290` `_latest_fred` absent/stale SQL collapse; `:285-286` the `None`
  fold; `:324-329` exec-summary régime-classifier anchor overrides; `:4260-4261`
  key_levels always-rendered precedent; `:4364-4428` `if <src>:` conditional-append;
  `:4532-4536` deterministic header; `:210-224` frozen `DataPool`.
- `run_session_card.py:98` `data_pool = pool.markdown` (sections_emitted discarded).
- `routers/data_pool.py:25-32,108-116` `DataPoolOut` projection (r90-live operator tool).
- [ADR-093](ADR-093-aud-commodity-surface-degraded-explicit.md) §r49 amendment (China-M1
  DEAD 2019-08-01, prod-DB ground-truth) + §"degraded explicit" pattern (static prose).
- [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md) §D-2 (`:105-111` never
  silently absent) + §T3.2 (`:154`).
- [ADR-097](ADR-097-fred-liveness-nightly-ci-guard.md) §Amendment (r92 — the
  `fred_age_registry` dep-free SSOT this ADR reuses at runtime).
