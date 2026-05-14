# ADR-092: GAP-D Asian-Pacific daily-proxy upstreams (unblock JPY + AUD GAP-A continuation 4/5 + 5/5)

**Status**: PROPOSED (round-44, 2026-05-14) — awaiting Eliot ratification. No code shipped by this ADR. Tier 1 inline FRED lookups (no new collectors) implemented in subsequent rounds : `_section_jpy_specific` round-45, `_section_aud_specific` round-46. Tier 2 collectors (BoJ Time-Series JGB 10Y daily, e-Stat MoF FX intervention monthly, RBA F1.1 cash-rate-target CSV daily) deferred to future ADRs once Tier 1 validated empirically on Hetzner.

**Date**: 2026-05-14

**Supersedes**: none

**Extends**: [ADR-083](ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md) D1 (6-asset universe — USD_JPY + AUD_USD listed as part of full 8-card D1 universe in CLAUDE.md), [ADR-090](ADR-090-eur-usd-data-pool-extension.md) (per-asset specific section pattern, BTP-via-FRED inline precedent), [ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D spend discipline — zero paid feeds).

**Related**: ADR-093 (PROPOSED future round — AUD commodity surface degraded explicit, iron-ore daily deferred).

## Context

Round-40 codified the **R24 SUBSET-not-SUPERSET mirror discipline** : a per-asset `_section_<asset>_specific` must triangulate via drivers whose cadences are **already daily** in the existing data pool, OR explicitly surface a frequency-mismatch warning (BTP r34 precedent). The 8-asset D1 universe progressed `_section_<asset>_specific` to **3/5 closed** through GAP-A continuation rounds 41-43 (XAU/NAS100/SPX500). 2 paires remain blocked :

- **USD_JPY** — `data_pool.py:2341-2346` carries only a 2-line stub (`vol_elevated → JPY-bid (safe haven)` + `inflation_pressure_up → UST yield up → USD-bid`). No daily JGB proxy, no carry-funding signal, no BoJ intervention tail-risk surface.
- **AUD_USD** — `data_pool.py:2348-2353` carries only a 2-line stub. The "commodity surface" needed for Chen-Rogoff 2003 commodity-currency triangulation is absent : no iron-ore feed, no copper feed, no China credit-impulse feed.

**Round-44 researcher audit** (this ADR) maps the upstream landscape exhaustively, identifies **3 Tier 1 inline-FRED signals** that ship without new collectors (mirror BTP r34 pattern), **3 Tier 2 collectors deferred** (BoJ + e-Stat + RBA), and **4 DEFER-firmly items** that fail Voie D cost-benefit (cost in dev-days + ToS opacity vs marginal Ichor edge).

## Decision

### Tier 1 — Ship-this-session via inline FRED (no new collector)

Mirror the BTP-via-FRED r34 inline pattern : `_section_jpy_specific` and `_section_aud_specific` consume `_latest_fred()` lookups with frequency-mismatch warning lines. The 3 Tier 1 signals are :

#### T1.JPY-1 — Japan 10Y monthly via FRED `IRLTLT01JPM156N`

- **Endpoint**: `https://api.stlouisfed.org/fred/series/observations?series_id=IRLTLT01JPM156N`
- **Ingestion status**: ✅ already in `fred_extended.py:105` SERIES_TO_POLL — no new ingestion code needed.
- **Cadence**: OECD MEI monthly, 1-month publication lag.
- **History**: January 1989 → present.
- **Registry**: ✅ already in `data_pool.py:_FRED_SERIES_MAX_AGE_DAYS["IRLTLT01JPM156N"] = 120` (r37 frequency-aware registry).
- **Framework anchor**: **Engel-West 2005**, "Exchange Rates and Fundamentals", J. Political Economy 113(3):485-517, DOI:10.1086/429137 — under near-unity discount factor, rate-differential proxies USD/JPY directional bias even when fundamentals are quasi-martingale.
- **Computed alongside**: `FRED:DGS10` (US 10Y daily) → `(DGS10 - IRLTLT01JPM156N)` US-JP 10Y differential. Cadence mismatch (daily / monthly) → surface as REGIME indicator, not intraday signal.

#### T1.AUD-1 — China M2 monthly via FRED `MYAGM2CNM189N`

- **Endpoint**: `https://api.stlouisfed.org/fred/series/observations?series_id=MYAGM2CNM189N`
- **Ingestion status**: ❌ NOT in `fred_extended.py` yet — adding 1 line in r46 implementation is the only delta.
- **Cadence**: IMF-sourced monthly.
- **History**: 1996 → present.
- **Registry add**: `_FRED_SERIES_MAX_AGE_DAYS["MYAGM2CNM189N"] = 60` (monthly 1-2 month lag).
- **Framework anchor**: AUD as commodity-currency proxy for China credit impulse — China M2 YoY growth is a known leading indicator of iron-ore demand and AUD spot via the China-property-construction channel. Adjacent to **Chen-Rogoff 2003** "Commodity Currencies" J.Int.Econ 60(1):133-160, DOI:10.1016/S0022-1996(02)00072-7 (commodity terms-of-trade transmitted to AUD spot in real time).

#### T1.AUD-2 — Global iron-ore + copper monthly via FRED `PIORECRUSDM` + `PCOPPUSDM`

- **Endpoint**: `https://api.stlouisfed.org/fred/series/observations?series_id={PIORECRUSDM,PCOPPUSDM}`
- **Ingestion status**: ❌ NOT in `fred_extended.py` — adding 2 lines in r46 implementation.
- **Cadence**: Global Price Index monthly (IMF World Bank pinkbook composite).
- **History**: 1980 → present.
- **Registry add**: `_FRED_SERIES_MAX_AGE_DAYS["PIORECRUSDM"] = 60` + same for `PCOPPUSDM`.
- **Framework anchor**: **Chen-Rogoff 2003** + **Ready-Roussanov-Ward 2017** "Commodity Trade and the Carry Trade: A Tale of Two Countries", J.Finance 72(6):2629-2684, DOI:10.1111/jofi.12546 — commodity-exporter currencies (AUD/CAD) co-move with commodity terms-of-trade ; structural carry premium emerges from commodity-exporter / final-goods-producer specialization split.

#### T1.AUD-3 — Australia 10Y monthly via FRED `IRLTLT01AUM156N`

- **Endpoint**: `https://api.stlouisfed.org/fred/series/observations?series_id=IRLTLT01AUM156N`
- **Ingestion status**: ❌ NOT in `fred_extended.py` — adding 1 line in r46 implementation.
- **Cadence**: OECD MEI monthly.
- **History**: Same as IRLTLT01JPM156N family.
- **Registry add**: `_FRED_SERIES_MAX_AGE_DAYS["IRLTLT01AUM156N"] = 120` (matches r37 registry pattern for OECD MEI series).
- **Framework anchor**: rate-differential channel for AUD/USD — RBA-Fed terminal differential is a primary AUD driver, especially during easing cycle divergences.

### Tier 2 — Defer to future rounds with dedicated ADRs

These have CLEAR specs but moderate dev-days + require Eliot manual identification for some upstream codes. NOT shipped round-44. Each requires its own ADR.

#### T2.JPY-Daily — BoJ Time-Series Data Search JGB 10Y daily collector (~2 dev-days)

- **Endpoint**: `https://www.stat-search.boj.or.jp/api/v1/getDataCode` (launched 2026-02-18, T-3 months at this ADR's writing).
- **Critical blocker**: code série JGB 10Y daily NOT confirmed via WebSearch on 2026-05-14. UI manual identification required at `https://www.stat-search.boj.or.jp/index_en.html` — Eliot to enumerate JGB benchmark codes.
- **Risk class**: similar to r33 Banca d'Italia SDMX BLOCKED, but BoJ API is public + no auth required (per 2 community wrappers `bojpy` + `delihiros/boj-api-client`). The risk is purely "wrong series code" not "endpoint inaccessible".
- **Mirror pattern**: Bundesbank Bund r29 — migration + ORM + collector + register-cron daily 11:00 Paris (Tokyo close +2h buffer).
- **Future ADR**: ADR-094 "BoJ Time-Series JGB collector" (PROPOSED after Eliot UI confirmation of series code).

#### T2.JPY-Intervention — e-Stat MoF FX intervention monthly collector (~1.5 dev-days)

- **Endpoint**: `http://api.e-stat.go.jp/rest/3.0/app/getStatsData?appId=X&statsDataId=000040061200`
- **Auth**: free `appId` registration at MyPage e-stat.go.jp (max 3 application IDs per account — non-blocker for Ichor 1-env).
- **Framework anchor**: **Ito-Yabu 2007**, "What prompts Japan to intervene in the Forex market? A new approach to a reaction function", J.Int.Money & Finance 26(2):193-212, DOI:10.1016/j.jimonfin.2006.12.001 (corrected DOI per round-44 verifier — the originally-claimed `.11.002` resolves to Kasuga 2007, an adjacent paper). Friction-ordered-probit modelling of MoF intervention reaction function ; deviation vs 21-day MA + asymmetric political cost (strong JPY hurts exporters).
- **Future ADR**: ADR-095 "MoF FX intervention reserves collector" (PROPOSED).

#### T2.AUD-RBA — RBA F1.1 cash-rate-target CSV daily collector (~0.5 dev-days)

- **Endpoint**: `https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv`
- **Auth**: none. License: **CC BY 4.0** (RBA public commitment) — Voie D safe + ToS clear.
- **History**: 1990 → present.
- **Pattern**: identical to Bundesbank Bund r29 (CSV pull + migration + ORM + register-cron daily 10:00 Paris = Sydney 18:00 close +2h).
- **Future ADR**: ADR-096 "RBA F1.1 cash rate target collector" (PROPOSED).

### DEFER firmly — fail Voie D cost-benefit

These are listed for completeness so a future Ichor maintainer does not re-investigate.

| Item                                          | Failing constraint                                                                                                                                                                                                                |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **yfinance `TIO=F` iron ore daily**           | Yahoo Developer API ToS prohibits automated access without permission. `hiQ v. LinkedIn 2022` limits CFAA but breach-of-contract risk persists. Voie D _spirit_ (zero paid feeds) ≠ Voie D _safe_ (zero legal ambiguity). Reject. |
| **AKShare LME/iron-ore mirror**               | Chinese-sourced open-source aggregator with opaque ToS chain — re-distribution risk unverifiable. Reject.                                                                                                                         |
| **LME 15-min delayed HTML scrape**            | No stable API ; HTML maintenance permanent cost ; LME public data ToS unclear. Reject.                                                                                                                                            |
| **BoJ rinban PDF schedule**                   | Quarterly PDF + ad-hoc news ; cadence + signal/noise incompatible with Ichor intraday. Aligned with WGC quarterly XLSX DROPPED 2026-05-11.                                                                                        |
| **PBoC 7d reverse repo daily**                | Scrape pbc.gov.cn HTML announcement index ; high parser maintenance ; AKShare alternative has same ToS issue. Reject.                                                                                                             |
| **Polygon C:AUDCNH daily**                    | Requires Polygon Currencies plan ($29-49/mo) — Voie D budget pressure. AUD-CNH ticker existence not confirmed in `/v3/reference/tickers?market=fx` query. Reject until ticker existence + cost-benefit re-evaluated.              |
| **Caixin/RatingDog PMI HTML scrape**          | 2026 brand rebrand changed IDs and URLs ; maintenance overhead persistent. Defer.                                                                                                                                                 |
| **PBoC TSF (Total Social Financing) monthly** | Scrape pbc.gov.cn ; Trading Economics free tier rate-limit too tight for cron use. Defer to future ADR if AUD signal-quality improvement empirically demonstrated post-Tier 1 ship.                                               |

## Acceptance criteria

### Tier 1 (this session, rounds 45-46)

1. **Round 45** : `_section_jpy_specific(session, asset)` exists in `data_pool.py`, asset-gated to `USD_JPY`. Emits 2-driver triangulation (JP10Y monthly via FRED + US-JP 10Y differential computed) with frequency-mismatch warning. Mirror BTP-via-FRED r34 pattern.
2. **Round 46** : 4 new FRED series ingested (`IRLTLT01AUM156N`, `MYAGM2CNM189N`, `PIORECRUSDM`, `PCOPPUSDM`) via `fred_extended.py` SERIES_TO_POLL addition + 4 registry entries in `_FRED_SERIES_MAX_AGE_DAYS`. `_section_aud_specific(session, asset)` exists, asset-gated to `AUD_USD`. Emits 3-driver triangulation (rate-diff + China credit impulse + commodity terms-of-trade). Surface "degraded explicit" annotation per ADR-093 PROPOSED (commodity daily feed absent).
3. **Empirical 3-witness (rule 18)** per `_section_<asset>_specific` :
   - Witness 1 : unit tests pass (>15 per section, mirror r43 SPX template).
   - Witness 2 : ADR-017 `is_adr017_clean(rendered_text)` returns True on all rendered branches.
   - Witness 3 : `build_data_pool(asset="USD_JPY")` or `"AUD_USD"` returns a section that includes the expected source-stamps when DB rows are present.
4. **R24 SUBSET-not-SUPERSET compliance** :
   - JPY : 1/2 drivers daily-clean (DGS10), 1/2 monthly mismatched (IRLTLT01JPM156N) → PASSES with mismatch warning, BTP r34 precedent.
   - AUD : 0/3 drivers daily-clean ; 3/3 monthly mismatched → PASSES via "degraded explicit" surface in ADR-093 documenting the gap.

### Tier 2 (deferred to future ADRs 094-096)

Each Tier 2 collector ships under its own ADR (PROPOSED → Accepted gate), each with the standard ADR-029 / ADR-077 / ADR-081 invariant set + RUNBOOK-014-class reversibility (<30s revert via .bak chain).

## Reversibility

- **Tier 1 inline FRED** : pure additions to `data_pool.py` (`_section_jpy_specific` + `_section_aud_specific` + 4 lines in `_FRED_SERIES_MAX_AGE_DAYS` + 4 lines in `fred_extended.py` SERIES_TO_POLL). Revert = single-commit revert. NO new migration. NO new ORM. NO new cron.
- **Tier 2 collectors** : each shipped under own ADR with standard reversibility (Bund r29 / €STR r34 precedents).

## Consequences

### Positive

- **GAP-A continuation 5/5 unlockable cette session** : JPY r45 + AUD r46 ship Tier 1 inline. Round-47 closes citation hygiene + W90 guards ; round-48 closing-sync v24.
- **Cost-benefit Voie D respected** : zero new paid feeds, zero new auth surface, zero new ToS-grey exposures. The 4 new FRED series are free + canonical + already-ingested-class (FRED API key already in env).
- **Doctrinal symmetry vs r34** : the BTP-via-FRED inline pattern is canonized as the standard "degraded-mode SUPERSET" approach when daily-clean upstreams are absent for monthly OECD MEI series.
- **Pass-2 narrative coherence improvement** : JPY + AUD Pass-2 prompts gain symmetric-language Tetlock-invalidation-ready interpretive branches, matching the standard set by r41-r43 (XAU/NAS/SPX).
- **Future-proof ADR roadmap** : ADR-094 (BoJ JGB daily) / ADR-095 (e-Stat intervention) / ADR-096 (RBA CSV) provide a clear shipping path when Eliot allocates Tier 2 dev-days.

### Negative

- **JPY r45 cadence-mismatch**: 1/2 drivers monthly = degraded signal quality vs the 3-daily-driver standard set by r43 SPX. Mitigation = explicit frequency-mismatch warning inline + Tetlock thresholds that accept monthly-cadence invalidation logic.
- **AUD r46 fully-monthly drivers** = "degraded explicit" surface in ADR-093 — Pass-2 LLM must read all 3 signals as REGIME indicators, not intraday signals. This is documented honestly rather than dissimulated.
- **BoJ JGB series code unconfirmed** : Tier 2 ADR-094 cannot ship until Eliot manually identifies the JGB 10Y benchmark series code via stat-search.boj.or.jp UI. Risk class : low (API + auth confirmed, only code ID missing).

### Neutral

- **The 4 new FRED series adds** are deferred to round-46 implementation, not this ADR. Tier 1 ship pace is single-PR-per-round for rollback safety (rule 19).
- **No Hetzner deploy gate** : the new sections are graceful-skip when FRED rows absent, so they can land on `main` without immediate ingestion ; the next Hetzner FRED collector cron (existing infrastructure, no new cron) will backfill.

## Open questions for Eliot

1. **Ratify Tier 1 ship round-45 + round-46 ?** — confirms doctrinal alignment with the inline-FRED degraded-SUPERSET pattern. Default answer = YES (BTP r34 precedent already validates the approach).
2. **Identify BoJ JGB 10Y daily series code** via stat-search.boj.or.jp manual UI exploration ? Required to unblock ADR-094 in a future round. Estimated 15-30 min Eliot manual exploration.
3. **AKShare ToS vetting** for any future iron-ore daily ambition ? Currently DEFER-firmly ; can be re-evaluated if AUD anti-skill emerges in Vovk Sunday fire after Tier 1 ship (analogous to EUR_USD round-29 anti-skill triggered ADR-090).
4. **Tier 2 shipping pace** : sequence ADR-094 / 095 / 096 in which order ? Recommended : RBA F1.1 first (lowest dev-days 0.5, lowest risk CC BY 4.0), then e-Stat (1.5d, framework-anchored Ito-Yabu), then BoJ JGB daily (2d, blocked on Eliot UI step).

## Sources (researcher audit trail, round-44 2026-05-14)

- [FRED IRLTLT01JPM156N Japan 10Y monthly](https://fred.stlouisfed.org/series/IRLTLT01JPM156N)
- [FRED IRLTLT01AUM156N Australia 10Y monthly](https://fred.stlouisfed.org/series/IRLTLT01AUM156N)
- [FRED MYAGM2CNM189N China M2 monthly](https://fred.stlouisfed.org/series/MYAGM2CNM189N)
- [FRED PIORECRUSDM Global Iron Ore monthly](https://fred.stlouisfed.org/series/PIORECRUSDM)
- [FRED PCOPPUSDM Global Copper monthly](https://fred.stlouisfed.org/series/PCOPPUSDM)
- [FRED IRSTCB01JPM156N Japan Central Bank Rate monthly](https://fred.stlouisfed.org/series/IRSTCB01JPM156N)
- [BoJ API launch notice 2026-02-18](https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm)
- [BoJ Time-Series Data Search portal](https://www.stat-search.boj.or.jp/index_en.html)
- [BoJ Outright Purchases JGBs](https://www.boj.or.jp/en/mopo/measures/mkt_ope/ope_f/index.htm)
- [MoF Japan FX Intervention Operations monthly](https://www.mof.go.jp/english/policy/international_policy/reference/feio/monthly/index.html)
- [e-Stat Japan FX Intervention dataset 000040061200](https://www.e-stat.go.jp/en/stat-search/files?page=1&layout=dataset&query=foreign&stat_infid=000040061200)
- [RBA F1.1 Money Market CSV direct (CC BY 4.0)](https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv)
- [Yahoo Developer API Terms of Use](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html)

## Framework DOI references (round-44 verifier audit trail)

- Engel & West 2005, "Exchange Rates and Fundamentals", J.Political Economy 113(3):485-517 — `10.1086/429137`
- Adrian, Etula & Muir 2014, "Financial Intermediaries and the Cross-Section of Asset Returns", J.Finance 69(6):2557-2596 — `10.1111/jofi.12189`
- Ito & Yabu 2007 (corrected DOI), "What prompts Japan to intervene in the Forex market?", J.Int.Money & Finance 26(2):193-212 — `10.1016/j.jimonfin.2006.12.001`
- Brunnermeier, Nagel & Pedersen 2009, "Carry Trades and Currency Crashes", NBER Macro Annual 23(1):313-348 — `10.1086/593088`
- Chen & Rogoff 2003, "Commodity currencies", J.Int.Economics 60(1):133-160 — `10.1016/S0022-1996(02)00072-7`
- Ready, Roussanov & Ward 2017, "Commodity Trade and the Carry Trade: A Tale of Two Countries", J.Finance 72(6):2629-2684 — `10.1111/jofi.12546`
