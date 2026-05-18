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

## Implementation (r102, 2026-05-18) — `IR3TIB01GBM156N` max-age recalibration 120→180 (step 3 R53 of the §Deferred unblock)

This dated note records r102. **No new ADR** (doctrine #9 — the
ADR-104 §Implementation(r96) / ADR-105 §Implementation(r99,r100) /
ADR-101 §Implementation(r101) immutable-append precedent) : this ADR's
**§Deferred section + §Implementation(r101) ARE the spec** for the
Driver-3 unblock — the recalibration of `IR3TIB01GBM156N`'s own
max-age is a continuation of the §Deferred step list, not a new
decision. A redundant child ADR would itself violate doctrine #9.

**The chicken-egg resolved.** §Implementation(r101) shipped steps 1+2
(poller add + a conservative `120` mirror of the OECD-MEI monthly
family) and **explicitly deferred step 3** (R53 prod-DB liveness
verify) as a structural chicken-egg : liveness is only prod-DB-verifiable
_after_ a scheduled FRED collector cron cycle ingests the series. That
cron fired post-r101 (`ichor-collector-fred_extended.timer`) and
ingested `IR3TIB01GBM156N`. r102 executes **step 3** : the R53 prod-DB
liveness verify + the threshold recalibration that verification
surfaces. (The Driver-3 _paragraph_ — step 4 — remains deferred to
r103, see "Still explicitly DEFERRED" below.)

**R53 citation-gate ground-truth (primary-source, the r88 China-M1
anti-hallucination discipline — NOT web-cache).** Verified against the
FRED primary source (browser-rendered series page + `fredgraph.csv`
actual observation rows), every figure URL-cited, observed
2026-05-18 :

- `IR3TIB01GBM156N` _Interest Rates: 3-Month or 90-Day Rates and
  Yields: Interbank Rates: Total for the United Kingdom_ — Monthly,
  Percent NSA, **OECD Main Economic Indicators**. Observation end
  **2026-01-01 = 3.71**, Last Updated **2026-02-16**, **NO
  discontinued banner** (https://fred.stlouisfed.org/series/IR3TIB01GBM156N
  - https://fred.stlouisfed.org/graph/fredgraph.csv?id=IR3TIB01GBM156N).
    Latest obs ≈ **137 days** old at the verify date.
- It is **alive-but-slow, NOT discontinued** — categorically the
  r94 ADR-092 §Round-94 false-DEGRADE class (a healthy slow feed
  whose threshold was set too tight), **NOT** the China-M1
  (`MYAGM1CNM189N`, frozen 2019-08-01, intentionally kept at 60d to
  flag the dead series — ADR-093 §r49) dead-series class. The
  distinction was made on primary-source evidence, not assumed
  (R59 / never-act-on-a-guess / the r88 China-M1 lesson).
- Its OECD-MEI monthly siblings refresh ~47 days
  (`IRLTLT01GBM156N` UK 10Y obs end 2026-04-01 = 4.8207, Last
  Updated 2026-05-15 ; `IR3TIB01USM156N` US 3M obs end 2026-04-01
  = 3.77, same batch). `IR3TIB01GBM156N` is **empirically the slow
  member of its own family** (~137 d vs the family's ~47 d) — the
  family's 47-day figure must **not** be applied to it.

**Recalibration 120 → 180.** The r101 `120` was the correct
conservative mirror _in the absence of liveness data_ (a missing
entry falls back to the 14-day DAILY default = the r35 always-stale
bug class ; mirroring the family-120 was the safe no-data default).
Step-3 liveness data now **refutes 120 for this member specifically** :
137 d observed staleness > 120 d ⟹ the series would be classified
STALE/DEGRADED in normal operation — the exact r94 ADR-092 §Round-94
false-DEGRADE pathology (commit `17e3780`, where IMF PCPS
`PIORECRUSDM`/`PCOPPUSDM` were recalibrated 60→120 for the same
"healthy-but-slow tripped a too-tight threshold" reason). Applying the
**r94 margin discipline** — and being honest that this is NOT a
verbatim pre-existing "×1.33 rule" : ADR-092 §Round-94 used a **~30 d
absolute margin over the ~90 d worst-case (→ 120)** plus a qualitative
"still catches a death within ~4 months". For this member's ~137 d
worst-case the _proportionalized_ form of that same discipline is
≈ 1.33× / ~+43 d margin → 182, taken to a **clean 6-month ceiling
180 d** (the answer is robust under either the proportional or the
+30–45 d additive reading — both land at ~180). The independent FRED
citation-gate's evidence-floor was 170 d (137 + ~1 monthly bin) ;
**180** is chosen over 170 for (a) r94 margin-discipline parity (the
established in-repo precedent, coherence over an ad-hoc thinner
margin — stated as a proportionalized interpolation of r94's additive
margin, not a verbatim rule), (b) robustness against this member's
documented erraticness as the family laggard, (c) a clean auditable
"6-month ceiling for the OECD-MEI 3M laggard". 180 d still
catches a genuine China-M1-class discontinuation (a true freeze blows
past 180 d within ~6 months and correctly DEGRADES) — the safety
property r94 requires is preserved. This is the sole non-120 OECD-MEI
monthly entry in the registry **by design and on evidence**, not an
inconsistency.

**LATENT, not live (calibrated honesty — no over-claim).**
`_section_data_integrity` (ADR-103 runtime FRED-liveness audit) only
liveness-checks the curated `_ASSET_CRITICAL_ANCHORS` set ; `GBP_USD`'s
sole critical anchor is `IRLTLT01GBM156N` (UK 10Y). `IR3TIB01GBM156N`
is **not yet consumed by any rendered section** (the Driver-3
paragraph is still deferred ; `_section_gbp_specific` never calls
`_latest_fred(session, "IR3TIB01GBM156N")` today). Therefore the
120-d false-DEGRADE was **latent** — r102 removes the **precondition
that would otherwise have made the r103 Driver-3 paragraph
false-DEGRADE every GBP card** ; it does **not** change any
currently-rendered card. r102 claims exactly this and no more
(lessons #1 forecast≠preuve, #2 SHIPPED≠FUNCTIONAL, #11
calibrated-honesty).

**What r102 shipped (1 registry value + verbose evidenced comment + 2
registry-test touch-points + this ADR append ; ZERO migration).**

- **`services/fred_age_registry.py`** — `"IR3TIB01GBM156N"` value
  `120 → 180` with a verbose r94-style evidenced comment block
  (observed 137 d, primary-source-cited, NOT the China-M1 dead class,
  the r94 §Round-94 design-rule derivation, ADR-101 §Impl(r102)).
  `data_pool.py` re-exports the same object under
  `_FRED_SERIES_MAX_AGE_DAYS` → `_max_age_days_for` /
  `_latest_fred` auto-inherit the new ceiling, zero-diff.
- **`tests/test_fred_frequency_registry.py`** — the dedicated
  `test_uk_3m_interbank_monthly_120_days` is **renamed**
  `test_uk_3m_interbank_monthly_180_days` (semantic-honesty +
  anti-accumulation : the test name encodes the contract ; a
  120-named test asserting 180 would lie — the same discipline that
  kept it OUT of the 10Y-only test at r101). Docstring rewritten :
  no longer "same 120 d cadence as the UK 10Y sibling" (now false) —
  it is the **documented OECD-MEI family laggard**, R53-prod-verified
  r102, recalibrated to 180 d. Asserts `== 180` / `_max_age_days_for
== 180`. The `monthly_series ≥30` sanity-tuple membership is
  unchanged (still a monthly series).
- **`tests/test_fred_liveness_check.py`** — the byte-identical-extraction
  pin `registry["IR3TIB01GBM156N"] == 120 → == 180` (comment updated
  to cite ADR-101 §Impl(r102)). The generic `_classify_severity`
  parametrize (`(130, 120, "YELLOW")` etc.) is a pure-function
  boundary test of the classifier, **not** `IR3TIB01GBM156N`-specific
  → correctly unchanged. The merged-poller membership pin
  (`"IR3TIB01GBM156N" in series`) is unchanged.

**ZERO migration (definitive, evidenced — not assumed).** The max-age
registry is a pure dependency-free config literal ; no schema, no ORM,
no table. The KEYWORD-MIGRATION hook fired on the _word_ "migration"
in context, not on a schema change — `git diff` carries zero
`alembic/versions/*` and zero ORM edit (r101 §Impl precedent — same
no-schema-guess discipline, lesson #13). No DB backup needed. Revert =
single-commit `git revert` + `redeploy-api.sh rollback`.

**Deliberate scope boundary (calibrated honesty — what r102 did NOT
do, and why).** The Driver-3-paragraph preamble prose in
`data_pool.py` (the `_section_gbp_specific` docstring `:2278-2282`
and the rendered `lines.append` block `:2362-2367`) + the
`test_data_pool_gbp_specific.py:325` test docstring say
`IR3TIB01GBM156N` is "poller-configured since r101 but not yet
prod-ingested / R53-liveness-verified". r102's step-3 liveness verify
makes that _sub-clause_ partially obsolete, BUT r102 **intentionally
does not rewrite that region** : (i) the strings' **operative
conclusion** — "the Driver-3 paragraph stays DEFERRED" — remains
accurate post-r102 (the paragraph IS still deferred to r103) ;
(ii) r103 (the Driver-3-paragraph wiring round) **rewrites that
entire region** when the paragraph stops being deferred — that is
the atomic, churn-free place to update the rationale ; (iii) writing
"R53-prod-verified" into a runtime code string ahead of the
protocol-ordered post-deploy consolidated-SSH re-confirm would be a
forecast≠preuve violation (lesson #1) ; (iv) mixing
Driver-3-paragraph prose into a threshold-config round violates the
1-atomic-increment / do-not-mix discipline. This boundary was posed
**explicitly to ichor-trader R28 pre-merge** (the r101 YELLOW-1
cross-file-drift precedent + the r100 scope-adjudication precedent) ;
its verdict is recorded in `docs/SESSION_LOG_2026-05-18-r102-EXECUTION.md`.

**Still explicitly DEFERRED to r103 (NOT done — calibrated honesty).**

- **(c) The US-side leg of the BoE-vs-Fed _3-month_ reaction-function
  differential.** Primary-source-confirmed r102 : `IR3TIB01USM156N`
  (US 3M interbank) **EXISTS**, same OECD-MEI monthly family,
  ~47-day lag — the _faithful_ Clarida-Galí-Gertler 3M-vs-3M
  counterpart — but is **NOT polled** (ingesting it is an r101-class
  chicken-egg). `DGS3MO` (US 3-Month Treasury constant maturity,
  daily, ~4-day lag) is **already polled** (`fred_extended.py:26`)
  but is a T-bill/CMT instrument, not an interbank rate — the
  differential's economic interpretation and the framework label
  must change accordingly if it is used. Reusing `DGS10` 10Y under
  the Clarida-Galí-Gertler label remains the **FORBIDDEN
  framework-attribution mis-stamp** (ADR-101 §Impl(r101) Axis-5
  RED). The instrument/label choice (ingest `IR3TIB01USM156N`
  true-3M-vs-3M with the chicken-egg, vs. already-polled `DGS3MO`
  with an explicit relabel) is an **r103 ichor-trader-R28-reviewed
  decision, not pre-committed here** (never-act-on-a-guess).
- **(d) The Driver-3 paragraph** in `_section_gbp_specific`
  (post-(c) : sign-convention R44, symmetric language, Tetlock
  invalidation + VIX cross-confirm, source-stamp, frequency-mismatch
  - R24 annotations, ADR-017-clean ; adapt
    `test_data_pool_gbp_specific.py`).

**R53 prod-DB re-confirm.** The r102 consolidated-SSH 3-witness
re-confirms `SELECT MAX(observation_date), COUNT(*) FROM
fred_observations WHERE series_id='IR3TIB01GBM156N'` at verify-time
(anti-cache ; the prompt's post-r101 ground-truth is a failsafe input,
re-confirmed live per R53) via the **real `fred_observations` schema**
(`\d` first — lesson #13 no-schema-guess) + the real `_max_age_days_for`
prod code path + healthz 200 + deployed-file grep. Witnessed result
recorded in `docs/SESSION_LOG_2026-05-18-r102-EXECUTION.md` (r102
makes no liveness claim ahead of that witness — forecast≠preuve).
Voie D untouched (FRED free public API). ADR-017 untouched (pure
threshold config — no signal, no BUY/SELL).

## Implementation (r103, 2026-05-18) — Driver-3 WIRED as a front-end term-structure REFINEMENT of Driver-1 (closes §Deferred step 4 + the Axis-5 RED + the r102 scope boundary)

This dated note records r103. **No new ADR** (doctrine #9 — the
§Impl(r101)/(r102) immutable-append precedent ; §Deferred + §Impl(r101)
Axis-5 ARE the spec). r103 **closes** the three open GBP items in ONE
atomic verified increment : (i) §Deferred step 4 (the Driver-3
paragraph) ; (ii) the §Impl(r101) Axis-5 **US-side-leg RED** ;
(iii) the §Impl(r102) "Deliberate scope boundary" (the 3 deferral-prose
sites are now rewritten in the same commit — the r101-YELLOW-1
cross-file-drift class, discharged here not deferred again).

**Framework decision — Option B (`DGS3MO`), adjudicated by a proactive
ichor-trader R28 framework-attribution review (ranked B ≻ A ≻ C, every
finding applied pre-merge).** Candidates :

- **C — `DGS10` 10Y under the Clarida-Galí-Gertler label : REJECTED**
  (the §Impl(r101) Axis-5 RED, independently re-confirmed : a 10Y
  long-rate is NOT a front-end reaction-function proxy AND it is a
  literal byte-duplicate of Driver-1's anchor `dgs10` at
  `data_pool.py:2309`). Resolved by **not using it** — the Axis-5 RED
  is hereby closed by rejection, not by mis-stamp.
- **A — ingest `IR3TIB01USM156N`** (US 3M interbank, same OECD-MEI
  family, EXISTS, ~47 d, primary-source-confirmed r102, **NOT
  polled**) : the exact same-instrument 3M-vs-3M pair, but an r101-class
  chicken-egg (poller add → cron cycle → R53 verify) forcing a 3-round
  split. **Not chosen** : the instrument-symmetry gain is second-order
  versus the signal's nature (a Driver-1 refinement, see YELLOW-1), and
  it does not escape the independence concern either ; a 3-round split
  for a refinement is not justified.
- **B — reuse already-polled `DGS3MO`** (US 3-Month Treasury constant
  maturity, daily ~4 d, `fred_extended.py:26`, in prod ; absent from
  `FRED_SERIES_MAX_AGE_DAYS` → the 14 d DAILY default, correct for a
  daily series, NOT the r35 bug class) : **CHOSEN**. Zero new
  ingestion → the lowest-blast-radius pattern this ADR's §Reversibility
  - §Consequences explicitly prized ; no chicken-egg → **one atomic
    verified r103 increment, no split** ; the faithfulness gap is fully
    closeable in prose (the mandated caveats below).

**The five ichor-trader R28 findings, ALL applied pre-merge :**

- **YELLOW-1 (highest stakes — independence/over-claim) :** a US-UK 3M
  differential is **not analytically independent of Driver-1's US-UK
  10Y differential** — same nominal-rate channel, different curve
  point. It is wired as a **front-end term-structure REFINEMENT of
  Driver-1, NOT a co-equal standalone "Driver 3"** (its genuine
  marginal content = the front-end-vs-long-end / relative-curve-shape
  decomposition : 3M = current relative policy stance, 10Y = cumulative
  expected stance + term premium). An explicit **INDEPENDENCE CAVEAT**
  is rendered (contrast Driver-2 Della-Corte-Sarno-Sestieri 2012 which
  IS independent — the NFA/current-account state variable). This
  resolves the r90-YELLOW-1 "regime-conditional lens over-claim" class.
- **YELLOW-2 (framework-attribution honesty) :** neither `DGS3MO` nor
  `IR3TIB01USM156N` IS the CGG reaction function (CGG 1998 is a
  structural estimated _policy-rate rule_, not a rate spread). The
  label is **"Clarida-Galí-Gertler-1998-_motivated_ front-end
  policy-rate-_proxy_ differential"**, never "the CGG
  reaction-function divergence". An explicit **FRAMEWORK-ATTRIBUTION +
  INSTRUMENT-BASIS CAVEAT** is rendered (`DGS3MO` is a risk-free
  Treasury CMT, the UK leg is an interbank rate — a TED-spread-class
  interbank-credit/term-premium wedge separates them ; in the current
  regime the front-end T-bill tracks the policy rate closely so the
  basis is second-order vs the policy-stance signal, but the pair is
  NOT a pure same-instrument interbank pair ; the faithful
  `IR3TIB01USM156N` EXISTS but is deliberately NOT ingested —
  lowest-blast-radius per §Reversibility, recorded here).
- **YELLOW-3 (frequency-mismatch honesty, sharper than Driver-1) :**
  the UK 3M leg `IR3TIB01GBM156N` is the documented OECD-MEI **family
  laggard, ~137 d / max-age 180 d (r102 §Impl(r102))** — materially
  STALER than Driver-1's ~47 d UK 10Y leg. The block states it is
  **staler than Driver-1's already-monthly leg**, treats the front-end
  differential strictly as a SLOW REGIME indicator (BTP r34 precedent),
  and warns Pass-2 must NOT read it as fresher front-end information
  than the 10Y differential (a new requirement the JPY/Driver-1
  precedents do not cover).
- **YELLOW-4 (source-stamp / Critic-verifiability) :**
  `_section_gbp_specific` did not call `_latest_fred(session,
"IR3TIB01GBM156N")`. r103 adds the UK-3M + DGS3MO `_latest_fred`
  calls and stamps **`FRED:IR3TIB01GBM156N@<date>` +
  `FRED:DGS3MO@<date>`** (mirroring `data_pool.py:2296`/`:2312`).
- **YELLOW-5 (deferral-prose cross-file drift — the r101-YELLOW-1
  class) :** the three sites that asserted "Driver-3 DEFERRED to r103"
  — the `_section_gbp_specific` docstring, the rendered Tetlock-tail
  block, and the `test_data_pool_gbp_specific.py` test docstring — are
  **all rewritten in this same atomic commit** (the operative truth
  flipped : the refinement is now ACTIVE). Assertions retained where
  still true ; `"DEFERRED"` removed from the rendered text and the
  test. **Plus two further cross-file code-comment sites** the r103
  diff itself rendered inaccurate are **also rewritten in this same
  commit** so the "all deferral-prose discharged" claim is literally
  true (no r103-introduced contradiction survives a future
  `grep deferred`): the `fred_extended.py` `IR3TIB01GBM156N` poller
  comment ("no Driver-3 paragraph yet" → "WIRED r103 as the front-end
  refinement, NOT a standalone driver") and the `build_data_pool`
  `gbp_specific` wiring comment in `data_pool.py` ("Clarida-Gali-Gertler
  1998 deferred per ADR-101" → "WIRED r103 as a term-structure
  REFINEMENT of Driver-1, NOT a co-equal Driver-3"), plus the
  `test_data_pool_gbp_specific.py` section banner. The first of these
  was caught pre-review by an independent round-2 completeness grep,
  the wiring comment by the ichor-trader R28 diff re-review — both
  applied pre-merge (the r101/r102-YELLOW-1 cross-file-drift discipline,
  now extended to the ADR's own self-description so this enumeration is
  exhaustive). The ADR-101 immutable §Decision/§Deferred/§Related body
  - the SESSION_LOGs are dated history / archaeology and are
    deliberately NOT rewritten (doctrine #9 — the dated §Implementation
    appends are the living truth, the §Impl(r101):188-217 precedent).

**R44 sign convention (GREEN) :** the front-end differential is
computed **`dgs3mo − uk3m` (US minus UK**, the `_RATE_DIFF_PAIRS`
`data_pool.py:153` convention generalized to the 3M point) — SAME
polarity as Driver-1 : a WIDER US-UK 3M differential ⟹ relative US
front-end/policy carry advantage ⟹ USD-bid ⟹ GBP/USD DOWNSIDE
(GBP-soft) ; narrower/negative ⟹ sterling front-end advantage ⟹
GBP-bid. No sign-flip risk. Symmetric language (both branches) +
Tetlock invalidation with VIX cross-confirmation (asymmetric
magnitudes, JPY r45 precedent) are emitted, and the full render is
`is_adr017_clean` True (Witness 2, §Acceptance #3).

**Atomicity & blast radius.** Option B = **ONE atomic verified r103
increment** : `DGS3MO` already polled + `IR3TIB01GBM156N` already
registry-180 (r102) ⇒ ZERO new ingestion, ZERO migration, ZERO
collector/cron/ORM/schema change ; purely-additive Pass-2 prose inside
the existing `if dgs10_latest is not None:` branch, additionally
guarded `if uk3m_latest is not None and dgs3mo_latest is not None:` so
a pre-ingestion GBP_USD silently skips the refinement (Driver-1/2
unaffected). `git revert <commit>` + `redeploy-api.sh rollback`
reverses it. Voie D untouched (FRED free public API ; zero Anthropic).
ADR-017 untouched (regime-conditional context, no BUY/SELL — Critic
should still verify the rendered text).

**§Acceptance criteria #3 Witness 3** is satisfied by the r103
consolidated-SSH 3-witness recorded in
`docs/SESSION_LOG_2026-05-18-r103-EXECUTION.md` : live
`build_data_pool(asset="GBP_USD")` renders the front-end refinement
block from live FRED rows (`DGS3MO` daily + `IR3TIB01GBM156N` the
~137 d laggard, surfaced with the staleness caveat) + `is_adr017_clean`
True + the R53 prod-DB re-confirm of both series at verify-time
(anti-cache, real schema). The GBP arc (Driver-1 Engel-West + Driver-2
Della-Corte external-imbalance + the front-end term-structure
refinement + the safe-haven caveat) is now COMPLETE ; ADR-101
§Deferred has no remaining open step.
