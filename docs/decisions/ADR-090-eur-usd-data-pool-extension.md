# ADR-090: EUR_USD data-pool extension (close structural anti-skill detected by Vovk W115)

**Status**: Accepted (round-32b ratify, 2026-05-13) — P0 step-1 (Bund 10Y collector + migration 0046 + ORM) shipped round-29 commit `e9ddcd6` ; P0 step-3 (`_section_eur_specific` symmetric render in `data_pool.py`) shipped round-32 commit `66bc3d8` (now `1660af4` post-rebase). 4 open questions answered in §"Open questions resolved (round-32b)" below. P0 step-2 (Hetzner deploy migration 0046) + step-4 (BTP/€STR/ECB-OIS collectors) deferred — step-2 awaits next Hetzner batch deploy ; step-4 backlog refined post-r32 subagent #3 web research (see §"Step-4 backlog refinement (round-32b)").

**Date**: 2026-05-13

**Supersedes**: none

**Extends**: [ADR-087](ADR-087-phase-d-auto-improvement-loops.md) (Phase D loops — measure side), [ADR-075](ADR-075-cross-asset-matrix-v2.md) (cross-asset matrix v2 — Pass-2 hints layer), [ADR-083](ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md) (D1 universe — EUR_USD included).

## Context

ADR-087 W115 Vovk-Zhdanov aggregator autonomously fired 2026-05-13 03:32:39 CEST and revealed a **structural anti-skill** on the `EUR_USD/usd_complacency` pocket :

| Pocket                  | n_observations | prod_predictor weight | equal_weight weight | skill_delta                               |
| ----------------------- | -------------- | --------------------- | ------------------- | ----------------------------------------- |
| NAS100/usd_complacency  | 12             | **0.464**             | 0.268               | **+0.196** (gaining skill)                |
| XAU/usd_complacency     | 9              | **0.457**             | 0.272               | **+0.185** (gaining skill)                |
| AUD/usd_complacency     | n/a            | 0.347                 | 0.326               | +0.021 (neutral)                          |
| JPY/usd_complacency     | n/a            | 0.334                 | 0.333               | +0.002 (neutral)                          |
| CAD/usd_complacency     | n/a            | 0.329                 | 0.335               | -0.006 (neutral)                          |
| GBP/goldilocks          | 1              | 0.304                 | 0.348               | -0.044 (low evidence)                     |
| **EUR/usd_complacency** | **13**         | **0.300**             | 0.350               | **-0.050 (anti-skill, stat-significant)** |
| GBP/usd_complacency     | n/a            | 0.294                 | 0.353               | -0.058 (low evidence)                     |

Round-27 researcher diagnostic established that the anti-skill is **structural, not statistical**. The data-pool layer is asymmetric : USD-side has 6-8 macro signals fresh per Pass-2 invocation, EUR-side has effectively one signal (`IRLTLT01DEM156N` — a monthly OECD MEI rate series, 30-day staleness in intraday).

**Verdict from researcher** : "Ne pas attendre plus de samples — c'est structurel, pas statistique. La pocket EUR_USD/usd_complacency sous-performe parce que l'asymétrie de couverture data-pool penche pro-USD."

## Decision — close 5 audit gaps (GAP-A → GAP-E)

### GAP-A : `data_pool.py` has NO `_section_eur_specific`

`apps/api/src/ichor_api/services/data_pool.py` defines per-section helpers : `_section_macro_trinity`, `_section_carry_skew`, `_section_realised_vol`, `_section_cross_asset_matrix`, `_section_calendar`, etc. **There is NO `_section_eur_specific`.** Grep on `ZEW|IFO|HICP|BTP|Bund|peripheral|ECB.*OIS|ESTR|german` returns zero matches.

**Action P0 (~1.5 dev-days)** : create `_section_eur_specific(asset, snapshot_dt)` emitting :

1. **Bund 10Y daily** : either Bundesbank `BBK01.WT3025` (daily series, free) or ECB SDW `BSI.M.DE.N.A.A20.A.1.U2.2300.Z01.E` (TBD verify daily vs monthly). Replace the monthly `IRLTLT01DEM156N`.
2. **BTP-Bund 10Y spread** : Bundesbank Bund 10Y minus Banca d'Italia BTP 10Y (`IRLTLT01ITM156N` is monthly ; need ECB SDW or scraping). Used as peripheral-risk + EU-fragmentation proxy.
3. **€STR** (Euro Short-Term Rate) : ECB SDW `EST.B.EU000A2X2A25.WT` daily. Front-end EUR funding rate.
4. **ECB OIS rate-path implied** : forward €STR overnight OIS curve. ECB SDW `MIR.B.EUOIS.*`. Implied ECB rate path next meeting + meeting+1. Used to cross-check Fed-ECB differential.

This section is included in the Pass-2 data-pool render for `EUR_USD`. It also feeds Pass-1 regime classification (see GAP-C).

### GAP-B : cross-asset matrix EUR_USD hints hard-coded USD-positive only

`data_pool.py:1383-1390` contains 3 hard-coded hints for `EUR_USD` and ALL THREE are USD-bullish :

```python
# Current (asymmetric) :
"USD-bid (NFCI tight)"
"USD-bid (vol regime)"
"Fed-on-hold supports USD"
```

In a `usd_complacency` régime (NFCI loose + VIX low + Fed cuts pricing), the EUR_USD tag empties to `["balanced"]` instead of emitting an EUR-bullish hint. The model has no prior directional support for EUR even when macro favors it.

**Action P1 (~0.5 dev-days)** : symmetrize the hints. Add EUR-bullish mirrors :

```python
# Proposed (symmetric) :
"USD-bid (NFCI tight)"           → mirror : "EUR-bid (NFCI loose + real yield diff narrowing)"
"USD-bid (vol regime)"            → mirror : "EUR-bid (VIX collapse + risk-on flows seek high-real-yield EZ)"
"Fed-on-hold supports USD"        → mirror : "Fed-cuts pricing supports EUR vs Fed-on-hold supports USD"
```

The cross-asset matrix produces a hint per asset per régime ; under `usd_complacency` the EUR_USD tag should include `EUR-bid (NFCI loose ...)`. Under `flight_to_quality` it should keep `USD-bid` hints.

### GAP-C : Pass-1 régime taxonomy has zero EZ input

`packages/ichor_brain/src/ichor_brain/passes/regime.py:23-26` defines `usd_complacency` as "DXY down, VIX low, risk assets bid" — purely US-centric. `macro_trinity_snapshot` (regime.py:38) only exposes `DXY/US10Y/VIX/DFII10/BAMLH0A0HYM2`.

**Action P1 (~0.5 dev-days)** : extend `macro_trinity_snapshot` schema to include `BUND_10Y` (daily, fresh) + `US_DE_10Y_DIFF` (Treasury 10Y minus Bund 10Y, the canonical EUR/USD long-end driver). Update Pass-1 prompt to acknowledge the differential when classifying `usd_complacency` vs `goldilocks` vs `risk_on`.

This is **NOT** a régime split — `usd_complacency` is still one bucket — but the rationale field becomes more accurate, and the régime classifier becomes less prone to mis-bucketing risk-on as usd_complacency (which currently penalizes EUR_USD because the bias-overlay direction is mechanically asymmetric).

### GAP-D : Vovk no small-sample Bayesian shrinkage

`services/vovk_aggregator.py:91-127` applies the canonical AA update without prior smoothing. At n=13, the weight delta -0.050 is statistically significant under classical hypothesis testing but interpretation suffers from no Dirichlet shrinkage toward uniform.

**Action P2 (~1 dev-day)** : add optional Dirichlet prior with `n_pseudo=10` (configurable per pocket). The math : effective weights `w_i = (w_i_raw + 1/N * n_pseudo / (n + n_pseudo)) * (n + n_pseudo) / (n + n_pseudo)`. This is a minimum-change Bayesian shrinkage that preserves Vovk-Zhdanov regret bound asymptotically (the prior contribution shrinks as 1/(n + n_pseudo)).

NOT bundled with P0 — the priority is data-pool, not aggregator math. Vovk is currently working as designed ; it's detecting real structural imbalance.

### GAP-E : `IRLTLT01DEM156N` monthly staleness

The only EZ signal in current Pass-2 EUR framework. Monthly = 30-day max staleness during intraday Pass-2 invocation. Effectively makes the "primary driver" inoperant on most fires.

**Resolution** : closed by GAP-A (replace with daily Bund 10Y + BTP-Bund spread + €STR + ECB OIS).

## Acceptance criteria

### P0 (data-pool extension, ~1.5 dev-days)

1. `services/data_pool.py:_section_eur_specific(asset, snapshot_dt)` exists.
2. New collectors / fred_extended additions for : Bund 10Y daily, BTP-Bund 10Y spread, €STR, ECB OIS rate-path.
3. Empirical 3-witness :
   - Witness 1 : unit test renders the section with 4 non-null fields.
   - Witness 2 : run `cli/run_session_card.py --asset EUR_USD --session london --dry-run` ; output contains `_section_eur_specific` block.
   - Witness 3 : after 14+ days of cards, re-run Vovk aggregator and compare `EUR_USD/usd_complacency` prod_weight ; expect rebound toward 0.45+ if hypothesis holds.

### P1 (symmetric cross-asset hints + macro_trinity_snapshot, ~1 dev-day)

1. `data_pool.py:_section_cross_asset_matrix` produces EUR-bullish hints in `usd_complacency` régime.
2. `macro_trinity_snapshot` schema includes `BUND_10Y` and `US_DE_10Y_DIFF`.
3. Pass-1 régime prompt acknowledges the differential.

### P2 (Vovk Bayesian shrinkage, ~1 dev-day, deferred)

1. Optional `n_pseudo` parameter on `VovkBrierAggregator` constructor.
2. CI guard test pins the asymptotic equivalence (shrinkage → 0 as n → ∞).

## Reversibility

- P0 = additive (new section, new collectors). Revert = remove section, revert collector adds. Easy.
- P1 = modifying existing helper. Revert = revert helper + macro_trinity_snapshot schema. Easy.
- P2 = constructor param defaults to `n_pseudo=0` (no shrinkage = current behaviour). Adoption is opt-in.

## Consequences

### Positive

- **EUR_USD pocket gains symmetric coverage** : Pass-2 receives daily fresh Bund/BTP/€STR/ECB-OIS context, no longer reasoning on a 30-day-stale monthly rate.
- **Pass-1 régime classification improves** : `usd_complacency` becomes more discriminative ; less mis-bucketing of risk-on as usd_complacency.
- **Cross-asset matrix is doctrinal** : if you trade USD-cross, BOTH sides of the cross need symmetric hint layers. Hard-coding USD-positive only is a structural bias.
- **Vovk small-sample interpretation improves** (P2) : n=13 pockets are less brittle.

### Negative

- **3 dev-days is a real chunk** : this is not a one-shot session. Spread across 2-3 PRs.
- **New collectors** add infrastructure surface : 4 new SDMX/FRED endpoints to query, persist, monitor.
- **GAP-C touches Pass-1 régime taxonomy** : risk of regime-shift in calibration scoreboard during the transition. Mitigation : ship behind a feature flag and run shadow régime classification for 7+ days before flipping.

### Neutral

- **AUD, CAD, JPY get GAP-A-like extensions for free later** : the pattern (per-asset specific section feeding daily rate + spread + curve signals) generalizes. Phase D loops will surface their anti-skill pockets if any.

## Open questions for Eliot

1. **Confirm SDW vs Bundesbank source** : Bundesbank Bund 10Y is daily, free, public. ECB SDW is also free but auth-light. Pick one for canonical source.
2. **Symmetric hints granularity** : per régime, or per (régime, asset class) ? Researcher recommendation = per régime (less surface, easier to maintain).
3. **Pass-1 régime split or not** : should `usd_complacency` be split into `usd_complacency_supported_by_diff` and `usd_complacency_despite_diff` ? Researcher recommendation = NO, keep one bucket but improve rationale field.
4. **Shipping pace** : ship P0 in one big PR, OR ship per-signal (Bund first, then BTP, then €STR, then ECB-OIS) ? Researcher recommendation = per-signal for rollback safety.

## Next session shipping plan

If Eliot ratifies, suggested round split :

- **Round 28** : ship P0 Bund 10Y daily collector + first section render + CI tests. (~1 day)
- **Round 29** : ship BTP + €STR + ECB-OIS additions. (~1 day)
- **Round 30** : ship P1 cross-asset matrix symmetry + Pass-1 macro_trinity_snapshot extension. (~1 day)
- **Round 31+** : observe Vovk pocket evolution for 14 days. Expect prod_weight rebound toward 0.45+.
- **Future** : P2 Vovk shrinkage if Vovk still shows anti-skill in n=30+ samples.

## Open questions resolved (round-32b ratify, 2026-05-13)

The 4 open questions in §"Open questions for Eliot" above are resolved as follows :

### Q1 — Source : Bundesbank confirmed

**Decision** : Bundesbank SDMX `BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A` confirmed as canonical Bund 10Y source.

**Justification** : (a) free + public + no API key + daily refresh ; (b) empirically validated 2026-05-13 = 3.13% PROZENT (round-29 collector test) ; (c) ECB SDW is also free but auth-light — Bundesbank is simpler. Round-32b subagent #3 web research re-validated the source is live and reachable.

### Q2 — Symmetric hints granularity : symmetric per signal (no regime split inside section)

**Decision** : `_section_eur_specific` emits SYMMETRIC interpretive language for any Bund yield move (both "rate-differential narrowing → EUR-positive in calm regime" AND "Bund/Treasury spread widening → EUR-negative under funding stress") and hands off to the Pass-2 LLM to pick the branch matching the Pass-1 regime label.

**Justification** : ichor-trader round-32 pre-implementation review flagged YELLOW on asymmetric "rise = EUR-positive" framing — it breaks under `funding_stress` / `usd_complacency` regimes where convertibility risk flips the mapping. The symmetric design lets the Pass-2 LLM contextualize without baking in a regime-specific bias inside the data-pool render. Code shipped round-32 commit `66bc3d8` (post-rebase `1660af4`).

### Q3 — Pass-1 régime split : NO, single bucket preserved

**Decision** : `usd_complacency` regime stays a single Pass-1 bucket. NO split into `usd_complacency_supported_by_diff` vs `usd_complacency_despite_diff`.

**Justification** : (a) researcher recommendation in original §"Open questions" ; (b) Pass-1 regime classifier surface stays simple (7 canonical regimes) ; (c) the rationale-field improvement happens via the data-pool extension itself — Pass-2 LLM contextualizes the regime via the rich EUR-side signals, not via additional regime granularity ; (d) Vovk pocket diagnostics work per-(asset, regime, session_type) tuple and adding regime variants would fragment the pocket sample sizes further (anti-skill pockets at n=13 → n=6 each on split is worse, not better).

### Q4 — Shipping pace : per-signal for rollback safety + ECB OIS re-scoped

**Decision** : per-signal shipping pace (Bund first ✓, then BTP, then €STR, then **ECB OIS re-scoped or removed**).

**Justification** : (a) researcher recommendation in original §"Open questions" ; (b) rule 19 reversibility favors single-signal commits over batch ; (c) round-32b subagent #3 web research established that **the assumed-shape multi-tenor ECB OIS curve dataflow does NOT exist on ECB public API** — MMSR is volume/rate-weighted by maintenance period (not tenor), YC dataflow is bond yield curve (not OIS). Re-scope ECB OIS to either : (i) derive implied path from €STR forwards via the verified `EST.B.EU000A2QQF32.CR` compounded rates dataflow, OR (ii) drop ECB OIS from ADR-090 step-4 scope and let a future ADR (`ADR-092 ECB OIS curve sourcing`) tackle it separately.

## Step-4 backlog refinement (round-32b)

Post-r32 subagent #3 web research (FX data sources for EUR-side signals) found :

| Signal            | Status                | Source                                                                                                                                                                              | 2026-05 sample value                                | Voie D fit                                                                                                              |
| ----------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Bund 10Y**      | ✅ SHIPPED r29        | Bundesbank SDMX `BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A`                                                                                                             | 3.13% PROZENT                                       | ✅ free + no auth + daily                                                                                               |
| **€STR**          | ⏳ VERIFIED, pending  | ECB Data Portal SDMX-CSV `data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT?lastNObservations=2&format=csvdata`                                                             | 1.929% on 2026-05-12                                | ✅ free + no key + daily ; note Eliot's expected band 3.0-3.5% was WRONG (ECB easing since 2024, actual range 1.5-2.5%) |
| **BTP-Italy 10Y** | ⏳ PARTIAL            | Primary : Banca d'Italia SDMX (returns HTTP 403 on WebFetch UA — needs real client headers in collector dev). Fallback : FRED `IRLTLT01ITM156N` (OECD monthly, free with FRED key). | 3.87% on 2026-05-12 (Trading Economics cross-check) | ✅ free ; primary needs probe in collector-dev round                                                                    |
| **ECB OIS curve** | 🚫 BLOCKED — re-scope | MMSR / YC dataflows confirmed NOT in expected shape via subagent #3 web research                                                                                                    | n/a                                                 | Defer to future ADR-092 OR derive from €STR forwards                                                                    |

**Next-round shipping order** : (i) €STR collector (1 day, source confirmed), (ii) BTP-Italy 10Y collector with primary Banca d'Italia SDMX probe + FRED fallback (1.5 days), (iii) ECB OIS deferred / re-scoped via separate ADR-092 once a viable public source is verified.
