# ADR-093: AUD commodity surface degraded explicit (GAP-A continuation 5/5)

**Status**: **Accepted** (round-47, 2026-05-15) — ratified by Eliot post-merge of PR #134 (commit `f764e35` on main). Implementation already shipped round-46 (`_section_aud_specific` in `apps/api/src/ichor_api/services/data_pool.py:1525-1900` + 58/58 tests + ADR-093 doctrinal primitive "degraded explicit surface annotation pattern" formalized).

**Original Status** (preserved for archeology) : PROPOSED (round-46, 2026-05-14) — awaiting Eliot ratification. Implements the
"degraded explicit" surface annotation pattern referenced in ADR-092 §Tier 1 §AUD acceptance
criterion 4 (R24 SUBSET-not-SUPERSET compliance via 3/3 monthly drivers + inline annotation).

**Round-2 audit amendment (2026-05-14 post-r46-ship)**: the originally-proposed China credit-
impulse proxy `MYAGM2CNM189N` (China M2 broad-money monthly via IMF IFS) was empirically
discovered to be **DISCONTINUED since August 2019** via the post-r46 researcher audit
(WebFetch FRED metadata returned latest observation 2019-08, ~6 years stale). The series
was swapped to `MYAGM1CNM189N` (China M1 = currency + demand deposits, same IMF IFS family,
verified LIVE through Dec 2025 via researcher web-cache lookup) before any post-merge code
shipped to production. M1 is a NARROWER aggregate than M2 but PRESERVES the canonical
Chen-Rogoff 2003 transmission proxy — M1 YoY surges historically lead CFETS commodity
demand by ~3-6 months per Barcelona-Cascaldi-Garcia-Hoek-Van Leemput 2022 Fed IFDP 1360
"What Happens in China Does Not Stay in China". This ADR retains the documented Chen-Rogoff
framing + adds Barcelona 2022 + Ferriani-Gazzani 2025 + RBA Bulletin Apr 2024 as
supplementary citations. The amendment trail is preserved in the r46-round-2 audit log.

**Date**: 2026-05-14

**Supersedes**: none

**Extends**: [ADR-083](ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md) D1 (8-card
universe — AUD_USD listed), [ADR-090](ADR-090-eur-usd-data-pool-extension.md) (per-asset
specific section pattern, BTP-via-FRED inline precedent for monthly OECD cadence-mismatch),
[ADR-092](ADR-092-gap-d-asian-pacific-daily-proxy-upstreams.md) §T1.AUD (Tier 1 inline FRED
ship scope — 4 new FRED series + 3-driver triangulation), [ADR-009](ADR-009-voie-d-no-api-consumption.md)
(Voie D spend discipline — zero paid commodity feeds), [ADR-017](ADR-017-reset-phase1-living-macro-entity.md)
(no BUY/SELL boundary — interpretive language symmetric).

**Related**: future ADR-094 (BoJ JGB daily) / ADR-095 (e-Stat MoF intervention) / ADR-096
(RBA F1.1 cash-rate-target CSV daily — would partially upgrade AUD signal quality from
"degraded" to "1-of-3 daily-clean" once shipped).

## Context

ADR-092 round-44 mapped the AUD upstream landscape exhaustively. **The empirical finding** :
zero free + ToS-clear + cron-safe **daily** commodity feed exists for iron-ore or copper. All
candidate sources fail Voie D cost-benefit :

| Candidate                      | Failing constraint                                                                   |
| ------------------------------ | ------------------------------------------------------------------------------------ |
| Yahoo `TIO=F` iron ore daily   | Yahoo Developer API ToS prohibits automated access (Voie D _spirit_ ≠ Voie D _safe_) |
| AKShare LME/iron-ore mirror    | Opaque ToS chain (Chinese-sourced redistribution risk)                               |
| LME 15-min delayed HTML scrape | No stable API, persistent parser maintenance, public-data ToS unclear                |
| SHFE / COMEX direct            | Paid feeds + auth complexity                                                         |
| Polygon Currencies `C:AUDCNH`  | Plan $29-49/mo, ticker existence unconfirmed                                         |

The R24 SUBSET-not-SUPERSET rule (codified round-40) requires either daily-clean drivers OR
explicit frequency-mismatch annotation. ADR-092 ruled **DEFER firmly** on all daily commodity
ambitions and ratified the **monthly composite via FRED** as the only Voie-D-safe path :

- `PIORECRUSDM` (Global Iron Ore Price Index, IMF World Bank pinkbook composite, monthly)
- `PCOPPUSDM` (Global Copper Price Index, same source family, monthly)

Combined with monthly Australia 10Y (`IRLTLT01AUM156N`) and monthly China M1
(`MYAGM1CNM189N` — see r46-round-2 audit amendment below for the swap from the
originally-proposed but DISCONTINUED `MYAGM2CNM189N`), the round-46 AUD section
presents **3/3 monthly drivers** with **zero daily-clean signal**. This is a strictly degraded signal-quality posture relative to the
r41 XAU (DFII10+DTWEXBGS both daily-clean), r42 NAS (DGS10+VVIX+SKEW all daily-clean) and
r43 SPX (VIX/VXV daily + NFCI weekly + SBOI monthly with explicit mismatch warning) ships.

**This ADR formalizes the "degraded explicit" surface pattern** so that Pass-2 LLM consumers
and Critic/audit reviewers cannot mistake the monthly-only AUD section for a daily-cadence
signal, and so that future ADRs (094/095/096 + commodity upgrades) have a clear baseline
against which to measure quality improvements.

## Decision

### Doctrinal surface pattern : "degraded explicit" annotation

`_section_aud_specific` MUST :

1. **Render only when the primary monthly anchor `IRLTLT01AUM156N` is fresh** (registry
   max-age 120d per r37 frequency-aware lookup) — silent skip otherwise.
2. **Surface inline a "degraded explicit" annotation line** in the section header AND in
   the composite triangle paragraph, citing ADR-093 by number. The annotation MUST mention :
   - all 3 drivers are monthly cadence (rate-diff via AU 10Y + China M2 + commodity ToT)
   - DGS10 daily is the only daily anchor in the section, used solely to compute the AU-Fed
     rate differential
   - the section is a REGIME indicator, NOT an intraday signal
   - the iron-ore daily feed gap is the empirical reason for the degraded posture (deferred
     per Voie D cost-benefit)
   - the future upgrade path : RBA F1.1 daily (ADR-096) would shift the daily-clean count
     to 1-of-3, AKShare/LME re-vetting would shift to 2-of-3.
3. **Apply symmetric interpretive language doctrine** (r32/r41/r42/r43 carry-forward) — each
   driver paragraph emits BOTH AUD-bid (e.g. carry-bid regime, commodity-reflation, China
   credit expansion) AND AUD-soft (carry-unwind, commodity-deflation, China credit contraction)
   regime-conditional branches. The Pass-2 LLM picks consistent with Pass-1 regime label.
4. **Tetlock invalidation thresholds on ALL 3 drivers** (r39 codified, r42+r43 carry-forward) :
   each interpretive paragraph MUST emit explicit invalidation conditions with cross-driver
   confirmation. Magnitudes pinned at the monthly cadence (n-month thresholds, NOT n-day).
5. **ADR-017 boundary regex-verified on full render** — no BUY/SELL/LONG NOW/SHORT NOW/etc.
   in any rendered branch. `is_adr017_clean(rendered_text)` MUST return True empirically.

### Iron-ore daily DEFER firmly — exit criteria

Re-evaluate the AKShare / LME / Polygon paths ONLY when at least ONE of the following triggers :

- **Trigger 1** : Vovk Sunday aggregator fires AUD_USD anti-skill stat-significance (n ≥ 13
  per pocket, mirror of EUR_USD round-29 trigger that motivated ADR-090). Until then, the
  Tier 1 monthly composite IS the best Voie-D-safe answer.
- **Trigger 2** : Anthropic Max-plan rate-cap doubles again OR Voie D budget envelope expands
  to include $29-49/mo Polygon Currencies subscription (highly unlikely per Eliot 2026-05-13
  Voie D paranoia).
- **Trigger 3** : ADR-096 RBA F1.1 CSV daily ships AND the section signal quality post-RBA
  add demonstrably improves the Brier score for AUD_USD relative to the Tier 1 baseline.
  At that point, the LME 15-min delayed evaluation becomes empirically motivated.

### Doctrinal symmetry vs SPX r43 NFCI weekly + SBOI monthly

The r43 SPX section ships with 2/3 daily-clean (VIX + VXV) + 1 weekly (NFCI) + 1 monthly
(SBOI). The frequency-mismatch warning is concentrated on SBOI only. AUD r46 ships with
0/3 daily-clean + 3/3 monthly, so the annotation is global across the whole section, NOT
just one paragraph. The ADR-093 surface pattern documents this difference so audit reviewers
do not mistake the AUD section structure for a regression vs SPX. **It is a different signal
class, surfaced honestly.**

## Acceptance criteria

1. `_section_aud_specific(session, asset)` exists in `apps/api/src/ichor_api/services/data_pool.py`,
   asset-gated to `AUD_USD`, silent-skip when `IRLTLT01AUM156N` absent.
2. The section header MUST contain the string `ADR-093` AND `degraded explicit` AND
   `commodity surface gap` so the inline citation is greppable by future audit reviewers.
3. The composite triangle paragraph (at end-of-section) MUST contain the future-upgrade-path
   annotation (RBA F1.1 daily ADR-096 + AKShare re-vetting path).
4. Empirical 3-witness (rule 18) :
   - Witness 1 : ≥15 unit tests pass (mirror r43 SPX template + r45 JPY parametrize structure).
   - Witness 2 : `is_adr017_clean(rendered_text)` returns True on all rendered branches.
   - Witness 3 : `build_data_pool(asset="AUD_USD")` returns a `data_pool` containing the
     `aud_specific` section when DB rows are present (parsed via `await aud_md, aud_src`).
5. **No new collector / migration / ORM / cron** — pure Tier 1 inline FRED ship (mirror
   BTP r34 + JPY r45 precedent). Revert = single-commit revert.

## Reversibility

- **Section addition** : pure additions to `data_pool.py` (`_section_aud_specific` + 4 lines
  in `_FRED_SERIES_MAX_AGE_DAYS` + wiring after `_section_jpy_specific` in `build_data_pool`).
  Revert = `git revert <commit>`.
- **fred_extended.py SERIES_TO_POLL** : 4 new entries (`IRLTLT01AUM156N`, `MYAGM2CNM189N`,
  `PIORECRUSDM`, `PCOPPUSDM`). Revert is symmetric. The next FRED collector cron picks up
  the changes ; before that, the AUD section silently skips (no rendered text, no error).
- **No Hetzner deploy gate** : section is graceful-skip when rows absent, so it can land
  on `main` without immediate ingestion. Backfill happens on the next scheduled
  `ichor-fred-extended.timer` fire.

## Consequences

### Positive

- **GAP-A 5/5 closed** : the 5-asset D1 universe per ADR-083 is fully covered by per-asset
  `_section_<asset>_specific` modules (EUR + XAU + NAS + SPX + JPY + AUD). The remaining
  3 assets of the 8-card D1 universe (GBP_USD + USD_CAD + USD_JPY/dup-of-JPY ; cf. CLAUDE.md
  D1 asset universe) inherit cross-asset matrix coverage with USD/EUR-side bidirectional
  hints from r38. **Per-asset specific module surface = 5/5 of the GAP-A scope**.
- **Voie D respected** : zero new paid feeds, zero new auth surface, zero new ToS-grey
  exposures. The 4 new FRED series are free + canonical + already in the same family as
  the round-34 BTP-via-FRED precedent.
- **Doctrinal honesty** : the "degraded explicit" surface pattern is a first-class doctrinal
  primitive, NOT a hack. Future per-asset sections with similar daily-feed gaps (e.g. an
  NZD or CHF section if D1 expands) can mirror this ADR's annotation pattern.
- **Future-proof upgrade path** : ADR-094 / 095 / 096 are the staged shipping path. Each
  upgrade is documented in advance, with empirical trigger conditions.
- **No Hetzner deploy gate** : the round-46 ship lands on `main` with the same single-PR
  cadence as r41 / r42 / r43 / r45. Backfill is autonomous via existing cron.

### Negative

- **Signal quality strictly degraded vs r41-r43-r45** : 3/3 monthly drivers means Pass-2
  cannot react to intraday or weekly commodity moves. The annotation surfaces this honestly,
  but the underlying quality gap remains.
- **Pass-2 LLM must read all 3 signals as REGIME indicators** — this is documented inline
  but creates a different consumption pattern vs r41-r43. Critic should verify the Pass-2
  prompt does NOT extrapolate the monthly signals to intraday entries.
- **AKShare / LME / Polygon Currencies / yfinance vetting is moved out of scope** — future
  Ichor maintainer must consult this ADR before reopening any of those paths.

### Neutral

- **The 4 new FRED series adds** happen in `fred_extended.py` SERIES_TO_POLL. The actual
  ingestion is driven by the existing cron infrastructure, no new timer needed.
- **No regression risk on r41-r43-r45 sections** — the AUD section is purely additive,
  asset-gated, with no shared state mutation.

## Open questions for Eliot

1. **Ratify the "degraded explicit" surface pattern as a doctrinal primitive ?** Default
   answer = YES (the alternative is silent omission, which is worse for audit trails and
   future-Claude orientation).
2. **Iron-ore daily upgrade timing** : after RBA F1.1 (ADR-096) ships and an empirical
   Brier improvement is measurable, OR only after AUD anti-skill emerges in Vovk Sunday ?
   Recommendation : the latter (Vovk trigger is a more reliable signal that the section
   quality is actually limiting Pass-2 performance).
3. **AKShare ToS re-vetting** : would Eliot accept commissioning a 1-shot legal-review of
   the AKShare redistribution chain (~1h researcher dispatch + 30min Eliot read) ? Defer
   until Trigger 1 fires.

## Sources (researcher audit trail, round-46 2026-05-14)

- [FRED IRLTLT01AUM156N Australia 10Y monthly](https://fred.stlouisfed.org/series/IRLTLT01AUM156N)
- [FRED MYAGM2CNM189N China M2 monthly](https://fred.stlouisfed.org/series/MYAGM2CNM189N)
- [FRED PIORECRUSDM Global Iron Ore monthly](https://fred.stlouisfed.org/series/PIORECRUSDM)
- [FRED PCOPPUSDM Global Copper monthly](https://fred.stlouisfed.org/series/PCOPPUSDM)
- [ADR-092 (round-44) Asian-Pacific daily-proxy upstreams PROPOSED](ADR-092-gap-d-asian-pacific-daily-proxy-upstreams.md)
- [Voie D AKShare ToS-opacity rejection (ADR-092 §DEFER firmly)](ADR-092-gap-d-asian-pacific-daily-proxy-upstreams.md#defer-firmly--fail-voie-d-cost-benefit)

## Framework DOI references (round-46 verifier audit trail, all DOI-verified Crossref r44)

- Engel & West 2005, "Exchange Rates and Fundamentals", J.Political Economy 113(3):485-517 — `10.1086/429137`
- Chen & Rogoff 2003, "Commodity currencies", J.Int.Economics 60(1):133-160 — `10.1016/S0022-1996(02)00072-7`
- Ready, Roussanov & Ward 2017, "Commodity Trade and the Carry Trade: A Tale of Two Countries", J.Finance 72(6):2629-2684 — `10.1111/jofi.12546`
- Adrian, Etula & Muir 2014, "Financial Intermediaries and the Cross-Section of Asset Returns", J.Finance 69(6):2557-2596 — `10.1111/jofi.12189`
