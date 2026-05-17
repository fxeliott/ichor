# ADR-101: GBP-specific section — UK-US rate-differential + sterling risk-premium (GAP-A continuation, GBP_USD)

**Status**: **Accepted** (round-90, 2026-05-17) — thin per-asset continuation of the
already-**Accepted** [ADR-092](ADR-092-gap-d-asian-pacific-daily-proxy-upstreams.md) under
Eliot's standing full-autonomy delegation ("autonomie totale ; décide et annonce, ne demande
pas") and the per-round default-Option contract (doctrine #10). Mirrors the ADR-093 thin
per-asset-child precedent (AUD). Implementation shipped same round (`_section_gbp_specific`
in `apps/api/src/ichor_api/services/data_pool.py` + `test_data_pool_gbp_specific.py`).

**Date**: 2026-05-17

**Supersedes**: none

**Extends**: [ADR-083](ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md) D1
(GBP_USD listed in the priority universe), [ADR-090](ADR-090-eur-usd-data-pool-extension.md)
(per-asset specific-section pattern, BTP-via-FRED inline precedent for monthly OECD
cadence-mismatch), [ADR-092](ADR-092-gap-d-asian-pacific-daily-proxy-upstreams.md) §Tier 1
(inline-FRED ship pattern — JPY r45 / AUD r46 proven), [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md)
§Tier 2 (analytical-depth roadmap — `_section_gbp_specific` is the explicitly-enumerated
Tier 2 item "GBP structurally thinnest"), [ADR-009](ADR-009-voie-d-no-api-consumption.md)
(Voie D — zero paid feeds, zero new ingestion), [ADR-017](ADR-017-reset-phase1-living-macro-entity.md)
(no BUY/SELL boundary — symmetric interpretive language).

**Related**: future ADR for the deferred Driver 3 (BoE-vs-Fed reaction-function divergence —
requires `IR3TIB01GBM156N` UK 3M interbank ingestion + R53 liveness verification).

## Context

ADR-092 Tier 1 scoped the per-asset inline-FRED sections for JPY (r45) and AUD (r46) only.
After r41-r46, **GBP*USD is the only one of the 5 ADR-083 priority assets
(EUR/USD, GBP/USD, XAU/USD, S&P 500, Nasdaq) WITHOUT a dedicated `\_section*<asset>\_specific`
module** — r40 only fixed a generic GBP path bug (a `list(eur_usd)` copy bug + USD_CAD
CAD-bid branch), it did NOT add a GBP-specific analytical section. EUR (r32+r34), XAU (r41),
NAS (r42), SPX (r43), JPY (r45), AUD (r46) all have one. This is the most concrete
"ce qui manque" gap for the mandated 5-asset × 8-layer coverage and is explicitly listed in
ADR-099 §Tier 2 as "`_section_gbp_specific` (GBP structurally thinnest — backend)".

**Empirical FX-literature finding** (round-90 web-research audit, DOI-verified Crossref):
GBP/USD is a **rate-differential + risk-premium currency, NOT a commodity currency**. The UK
is a net energy importer with a structural current-account deficit and no robust
terms-of-trade beta — the AUD iron-ore/copper pattern does NOT transfer. The literature
identifies a **sterling external-imbalance / fiscal risk-premium** channel layered on top of
the canonical interest-rate channel (the 2022 LDI/gilt-crisis configuration). Sterling is
also **not a USD safe-haven** (USD is the risk-off leg of GBP/USD).

**Empirical FRED-liveness finding** (round-90 prod-DB ground-truth query, R53 discipline —
NOT web-cache, the r88 China-M1 hallucination lesson):

```
psql -d ichor : SELECT series_id, MAX(observation_date), COUNT(*), latest value
 DGS10           | 2026-05-14 | (fresh, ≪14d) | 4.47
 IRLTLT01GBM156N | 2026-04-01 | (46d < 120d registry max-age) | 4.8207
```

Both Driver-1 inputs are **empirically LIVE** (UK 10Y is a monthly OECD MEI series with a
1-month publication lag — 46-day-old latest obs is normal and well within the registered
120d max-age at `data_pool.py:243`; it is **NOT** dead like the China IMF-IFS M1/M2 series
that were stuck at 2019). `IRLTLT01GBM156N` is already polled (`fred_extended.py:106`),
already in the max-age registry, and GBP is already in `_RATE_DIFF_PAIRS` (`data_pool.py:153`).
**Zero new FRED ingestion is required** — strictly lower blast-radius than the AUD r46 ship
(which added 4 new series).

## Decision

Ship `_section_gbp_specific` as a **2-driver inline-FRED section** mirroring the proven
JPY r45 structure (the closest analogue — clean 2-driver rate-differential), with **zero new
FRED ingestion** and the synthesis SSOT (`verdict.ts`) and every existing section untouched
(purely additive, asset-gated, no shared-state mutation):

- **Driver 1 — UK-US 10Y rate differential.** Primary anchor `IRLTLT01GBM156N` (UK 10Y,
  OECD MEI monthly, registry max-age 120d) paired with `DGS10` (US 10Y daily) for the
  differential `dgs10 - uk10y` (US − foreign, the `_RATE_DIFF_PAIRS` sign convention).
  Framework: **Engel & West 2005, "Exchange Rates and Fundamentals", J.Political Economy
  113(3):485-517, DOI:10.1086/429137** (Crossref-verified; currency-agnostic — applies to
  GBP exactly as to JPY: under a near-unity discount factor the spot rate is
  quasi-martingale yet rate fundamentals still determine its level).
  **SIGN-CONVENTION DISCIPLINE (R44; the r40 GBP bug class):** GBP/USD quotes USD per GBP,
  so USD is the QUOTE currency (same polarity as EUR/USD `IRLTLT01DEM156N`, OPPOSITE to
  USD/JPY & USD/CAD where USD is the base). A WIDER US-UK differential (`dgs10 - uk10y`
  more positive) ⟹ USD carry advantage ⟹ **GBP/USD DOWNSIDE (GBP-soft / USD-bid)** — the
  inverse of the JPY template's "wider differential → USD/JPY upside". The section text
  states this polarity explicitly.

- **Driver 2 — Sterling external-imbalance risk-premium (an INDEPENDENT additive lens,
  no new series).** Framework: **Della Corte, Sarno & Sestieri 2012, "The Predictive
  Information Content of External Imbalances for Exchange Rate Returns", Review of
  Economics and Statistics 94(1):100-115, DOI:10.1162/REST_a_00157** (Crossref-verified
  primary-source r90 — title + page range confirmed verbatim). DCS 2012 is an
  _external-imbalance_ predictor: a country's net-foreign-asset / current-account
  position carries a time-varying currency risk premium. It does **NOT** reinterpret the
  Driver-1 rate differential — it is an _independent_ structural signal. For sterling
  (a structural current-account-deficit currency) it implies an ADDITIVE GBP-soft risk
  premium under UK funding stress (the 2022 LDI/gilt-crisis configuration), layered on —
  not derived from — the Engel-West rate-differential read. Surfaced as an interpretive
  overlay (no new series needed); a dedicated external-balance dataset is a future
  enrichment. (ichor-trader r90 YELLOW-1 corrected the original "regime-conditional lens
  on the same differential" over-claim — framework-attribution honesty.)

- **Safe-haven caveat (a one-line NOTE, NOT a driver).** Ranaldo & Söderlind 2010,
  Review of Finance 14(3):385-407, DOI:10.1093/rof/rfq007 (Crossref-verified): sterling is
  not a USD safe-haven; in acute risk-off USD is the bid leg of GBP/USD.

The section MUST also: emit the **frequency-mismatch warning** (DGS10 daily vs UK 10Y
monthly — BTP r34 cadence-mismatch precedent, treat the differential as a REGIME indicator
NOT an intraday signal); apply **symmetric interpretive language** (both GBP-soft and
GBP-bid regime-conditional branches — r32/r41/r42/r43 carry-forward); emit **Tetlock
invalidation thresholds** with VIX cross-confirmation (asymmetric magnitudes, JPY r45
precedent); be **ADR-017-clean** (`is_adr017_clean(rendered)` True empirically); and document
the **R24 SUBSET-not-SUPERSET** cadence reasoning inline citing BTP r34.

### Deferred: Driver 3 — BoE-vs-Fed reaction-function divergence

Clarida, Galí & Gertler 1998, European Economic Review 42(6):1033-1067,
DOI:10.1016/S0014-2921(98)00016-6 (RePEc + ScienceDirect open-archive confirmed; Crossref
returned a rate-limit 429, not a resolution failure — DOI is real) is the front-end
(policy-rate) complement. It requires `IR3TIB01GBM156N` (UK 3M interbank, OECD monthly) —
**NOT currently polled**, and its liveness has **NOT** been prod-DB-verified this round.
Per scope discipline + the r88 lesson (no new unverified-liveness series in the same round
as the increment) Driver 3 is **deferred** to a future round (add to `fred_extended.py`
SERIES_TO_POLL + `_FRED_SERIES_MAX_AGE_DAYS` + R53 liveness verify, then a Driver-3
paragraph). `IRSTCB01GBM156N` does NOT exist (do not use). The legacy UK CPI series
`GBRCPALTT01IXNBM` is DISCONTINUED — its successor `GBRCPIALLMINMEI` would be the input if
a CPI-conditioned refinement is later added.

## Acceptance criteria

1. `_section_gbp_specific(session, asset)` exists in `data_pool.py`, asset-gated to
   `GBP_USD`, silent-skip when `IRLTLT01GBM156N` absent (zero DB I/O on the gate-miss path).
2. Section text contains `ADR-101`, the polarity statement (USD is the GBP/USD quote
   currency), `Engel-West`, `Della Corte`, and the `Frequency mismatch` /
   `R24 SUBSET-not-SUPERSET` annotations (greppable by future audit reviewers).
3. Empirical 3-witness (rule 18):
   - Witness 1: ≥12 unit tests pass (mirror `test_data_pool_jpy_specific.py`).
   - Witness 2: `is_adr017_clean(rendered_text)` returns True on the full render.
   - Witness 3: post-deploy, `build_data_pool(asset="GBP_USD")` includes the
     `gbp_specific` section with the real US-UK differential (DGS10 minus UK10Y) computed
     from live FRED rows.
4. **No new collector / migration / ORM / cron / FRED series** — pure Tier 1 inline ship
   reusing already-polled `IRLTLT01GBM156N` + `DGS10`. Revert = single-commit `git revert`.

## Reversibility

Pure additions to `data_pool.py` (one new `_section_gbp_specific` function before
`_section_rate_diff` + one wiring triplet after the AUD triplet in `build_data_pool`) + one
new test file + this ADR. No `fred_extended.py` change (both series already polled). No
Hetzner deploy gate — the section graceful-skips when rows are absent. `git revert <commit>`
fully reverses it; `redeploy-api.sh rollback` reverses the deploy in <30s.

## Consequences

### Positive

- **GAP closed**: all 5 ADR-083 priority assets now have a dedicated per-asset analytical
  section (EUR/XAU/NAS/SPX/JPY/AUD + **GBP**). The mandated 5-asset × 8-layer coverage no
  longer has GBP as the structurally-thinnest hole.
- **Lowest-risk pattern**: zero new ingestion, both series empirically LIVE-verified this
  round, blast-radius nil (asset-gated, additive, SSOT untouched), proven JPY r45 template.
- **Voie D + DOI honesty**: zero paid feeds; 3 shipped frameworks all Crossref-verified;
  the unverified-Crossref Driver-3 framework is explicitly labelled deferred, not shipped
  as an active claim (r88 anti-over-claim discipline).

### Negative

- **2/2 mixed cadence** (DGS10 daily + UK 10Y monthly): the differential is a REGIME
  indicator, surfaced honestly via the frequency-mismatch + R24 annotations. Pass-2 must
  not extrapolate it to intraday entries (Critic should verify).
- **Driver 3 absent until a future round**: the front-end BoE-vs-Fed leg is not yet
  surfaced; the section is a long-rate + risk-premium read only (documented in §Deferred).

### Neutral

- No regression risk on r41-r46 sections — purely additive, asset-gated, no shared state.

## Sources (round-90 audit trail, all DOI-verified Crossref unless noted)

- [Engel & West 2005, JPE — DOI 10.1086/429137](https://www.journals.uchicago.edu/doi/abs/10.1086/429137)
- [Della Corte, Sarno & Sestieri 2012, REStat — DOI 10.1162/REST_a_00157](https://direct.mit.edu/rest/article-abstract/94/1/100/57987/)
- [Ranaldo & Söderlind 2010, Review of Finance — DOI 10.1093/rof/rfq007](https://academic.oup.com/rof/article-abstract/14/3/385/1592162)
- Clarida, Galí & Gertler 1998, EER — DOI 10.1016/S0014-2921(98)00016-6 (deferred Driver 3; RePEc + ScienceDirect open-archive confirmed, Crossref 429 rate-limit only)
- [FRED IRLTLT01GBM156N (UK 10Y, monthly, LIVE 2026-04-01 prod-DB verified)](https://fred.stlouisfed.org/series/IRLTLT01GBM156N)
- [FRED DGS10 (US 10Y, daily, LIVE 2026-05-14 prod-DB verified)](https://fred.stlouisfed.org/series/DGS10)

## Implementation (r101, 2026-05-17) — Driver-3 ingestion plumbing (step 1 of the §Deferred unblock)

This dated note records r101. **No new ADR** (doctrine #9 — the
ADR-104 §Implementation(r96) / ADR-105 §Implementation(r99,r100)
immutable-append precedent) : this ADR's **§Deferred section IS the
spec** for Driver-3. The §Related line's "future ADR for the deferred
Driver 3" anticipation is **superseded by this dated §Implementation** —
a redundant child ADR is not authored when the parent already specs the
work (doctrine #9). One focused read-only R59 sub-agent mapped the real
FRED-ingestion surface (file:line) and the design was re-verified
against the real code before any edit (doctrine #3).

**Scope = ONLY the first two of the three §Deferred steps.** §Deferred
states verbatim: _"add to `fred_extended.py` SERIES_TO_POLL +
`_FRED_SERIES_MAX_AGE_DAYS` + R53 liveness verify, then a Driver-3
paragraph"_. r101 ships **step 1 (poller add) + step 2 (max-age
registry)**. **Step 3 (R53 prod-DB liveness verify) + the Driver-3
paragraph in `_section_gbp_specific` remain explicitly deferred to a
LATER round** — this is the documented chicken-egg: `IR3TIB01GBM156N`
liveness can only be prod-DB-verified _after_ a scheduled FRED collector
cron cycle has ingested it (r88 lesson #1 forecast≠preuve, lesson #2
SHIPPED≠FUNCTIONAL — r101 deliberately makes **no** liveness claim).

**§Acceptance criteria #4 reconciliation (calibrated honesty).**
§Acceptance #4 reads "No new collector / migration / ORM / cron / FRED
series" — that criterion governed the **r90 Drivers-1+2 inline ship**
(which reused already-polled `IRLTLT01GBM156N` + `DGS10`). The **r101
FRED-series add is the §Deferred-sanctioned exception** that §Deferred
itself prescribes ("add to `fred_extended.py` SERIES_TO_POLL"). r101
is therefore **outside the scope of** §Acceptance #4 (which governed
the r90 Drivers-1+2 inline ship) — it executes the §Deferred unblock
§Acceptance #4 was explicitly scoped to exclude. (A future reviewer
grepping §Acceptance #4 must read it as r90-Driver-1+2 scoped ;
§Deferred is the authorizing spec for the r101 series add — this is a
staged-ADR boundary, not a contradiction.)

**What r101 shipped (2 code + 3 test touch-points ; ZERO migration).**

- **`collectors/fred_extended.py`** — `"IR3TIB01GBM156N"` added to
  `EXTENDED_SERIES_TO_POLL` adjacent to the existing
  `"IRLTLT01GBM156N"` (UK 10Y) GBP-grouping line (the proven r45/r46
  add-point — `fred.py` base `SERIES_TO_POLL` is correctly NOT
  touched). `merged_series()` dedup-merges it into the polled tuple ;
  the next FRED collector cron fire fetches it into the existing
  generic `fred_observations` table.
- **`services/fred_age_registry.py`** — `"IR3TIB01GBM156N": 120`
  added to `FRED_SERIES_MAX_AGE_DAYS` adjacent to the OECD-MEI
  monthly-120 family (`IRLTLT01{DE,IT,JP,GB,AU}M156N` are all 120).
  `IR3TIB01GBM156N` is the **same OECD-MEI monthly family** as
  `IRLTLT01GBM156N` (identical `…01GBM156N` suffix, 1-month
  publication lag ; only the indicator differs: 3-month interbank vs
  10Y long-term). The cadence value **120 is mirrored from the
  established sibling precedent, not invented** — a missing entry
  would fall back to the 14-day DAILY default and be silently
  always-stale (the r35 bug class). `data_pool.py` re-exports the same
  object under `_FRED_SERIES_MAX_AGE_DAYS` (zero-diff backward-compat,
  auto-inherited).
- **`tests/test_fred_frequency_registry.py`** — a **dedicated** new
  test `test_uk_3m_interbank_monthly_120_days` (NOT folded into the
  existing `…_10y_monthly_all_120_days` test, whose name/docstring is
  semantically 10Y-only — folding a 3M series in would make that
  test's contract lie ; semantic honesty + anti-accumulation) +
  `"IR3TIB01GBM156N"` added to the generic `monthly_series ≥30`
  sanity tuple (semantically a monthly series, correctly extends
  that loop). `test_registry_size_lower_bound` (`≥20`, non-tight)
  stays green.
- **`tests/test_fred_liveness_check.py`** — added
  `assert "IR3TIB01GBM156N" in series` (the merged-poller membership
  pin — the only safety net against forgetting the poller add, as no
  exhaustive `EXTENDED_SERIES_TO_POLL` completeness test exists) +
  `assert registry["IR3TIB01GBM156N"] == 120` in
  `test_import_canonical_sources_resolves_from_dep_free_registry`.

**ZERO migration (definitive).** All FRED series write to the single
generic `fred_observations` table (`models/fred_observation.py` —
`series_id` is an indexed column, not a per-series table). Adding a
series to the poller + max-age registry is a pure config/registry
change ; new rows land on the next cron fire. ADR-101 §Acceptance #4
and ADR-092 §Reversibility both state "NO new migration / ORM / cron".
Revert = single-commit `git revert` + `redeploy-api.sh rollback`.

**Deploy is the §Deferred unblock.** The additive `redeploy-api.sh`
ships the new poller config to prod so the **next scheduled FRED
collector cron cycle ingests `IR3TIB01GBM156N`** — which is precisely
what makes the _later_ round's step-3 R53 prod-DB liveness verify
possible (resolving the chicken-egg ADR-101:117 deliberately left at
r90). Voie D untouched (FRED is a free public API, key already in env —
zero new paid feed, zero Anthropic). ADR-017 untouched (pure ingestion
plumbing, no signal, no BUY/SELL).

**Still explicitly DEFERRED (NOT done — calibrated honesty).**

- Step 3: `IR3TIB01GBM156N` R53 prod-DB liveness verification (a
  LATER round, post-cron-cycle — r101 makes no liveness claim).
- The Driver-3 paragraph in `_section_gbp_specific` (post-liveness).
- The US-side leg for the eventual BoE-vs-Fed _3-month policy-rate_
  differential is **unresolved and not pinned by this ADR**: the
  existing GBP/JPY/AUD rate-differential drivers all use `DGS10` (US
  10Y) ; a true front-end policy-rate differential (Clarida-Galí-Gertler
  is a _reaction-function_ lens) would conceptually want a 3M-vs-3M
  pair (`IR3TIB01USM156N`, US 3M interbank — **not** in the codebase,
  **not** ingested by r101). Whether Driver-3 reuses the established
  `DGS10` 10Y anchor or also ingests `IR3TIB01USM156N` is a
  **Driver-3-wiring-round decision, out of r101 scope** — flagged
  here so the future round R59s it explicitly rather than inheriting
  an unstated assumption. **Future-round RED (ichor-trader r101 R28
  Axis-5 desk note) :** if the Driver-3 wiring round reuses the
  established `DGS10` (US 10Y long-rate) anchor _while keeping the
  Clarida-Galí-Gertler label_, that is a framework-attribution
  mis-stamp — a 10Y long-rate differential is NOT a front-end
  reaction-function proxy (Clarida-Galí-Gertler 1998 is explicitly a
  _policy-rate_ reaction-function paper) ; it would be a Driver-1
  duplicate under a wrong label (the "regime-conditional lens
  over-claim" class ichor-trader caught at r90 YELLOW-1). The wiring
  round MUST treat "reuse `DGS10` 10Y ⟹ keep the Clarida-Galí-Gertler
  attribution" as a RED to resolve then (either ingest a true
  `IR3TIB01USM156N` 3M-vs-3M pair, or relabel the framework).
  `IRSTCB01GBM156N` does NOT exist (do not use, per §Deferred).
