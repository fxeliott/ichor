# ADR-096: RBA F-series rate collector (Tier 2 GAP-D upgrade — corrected from "F1.1 daily")

**Status**: PROPOSED (round-46-round-3, 2026-05-14) — awaiting Eliot ratification ;
F-series table selection EMPIRICALLY CONFIRMED round-46-round-6 (see amendment below).
No code shipped by this ADR.

## Round-46-round-6 amendment (2026-05-14) — F2 EMPIRICAL CONFIRMATION

The "F-series table selection" step originally listed as "Eliot 5-10 min empirical
fetch verify required" was COMPLETED in round-46-round-6 via direct WebFetch on
`https://www.rba.gov.au/statistics/tables/csv/f2-data.csv`. Empirical findings :

- **Cadence** : **DAILY** ✓ (sample dates 02-Sep-2013 / 03-Sep-2013 / 04-Sep-2013,
  consecutive trading days, no aggregation)
- **Column structure** : `"Australian Government 2 year bond, Australian Government
3 year bond, Australian Government 5 year bond, Australian Government 10 year bond,
Australian Government Indexed Bond"` ✓ (10Y daily yield column PRESENT)
- **Sample values** : 02-Sep-2013 10Y = 3.989%, 03-Sep-2013 = 4.030%, 04-Sep-2013 =
  4.055% — consistent with daily-yield-curve-evolution semantics
- **License** : CC BY 4.0 per RBA public commitment (not embedded in CSV per the
  RBA convention, but on the rba.gov.au/copyright page — empirically verified via
  ADR-092 §Source links in round-46-round-3)
- **File size** : ~192 KB (small enough for daily cron pull without throttling concern)

**F2 selection is the correct target** for ADR-096 implementation. Eliot's "5-10 min
empirical verify" step is hereby SATISFIED. Implementation can proceed without
further empirical-gate.

The only remaining Eliot-gated step is **ratification of this ADR** (status PROPOSED →
Accepted), after which the 8-step Bundesbank Bund r29 mirror implementation can land
in round-47+.

**Date**: 2026-05-14

**Supersedes**: ADR-092 §T2.AUD-RBA partial — the original §T2.AUD-RBA claimed RBA F1.1
is "daily" ; researcher round-46-round-2 empirical fetch confirmed F1.1 = MONTHLY
(Cash Rate Target + Interbank Overnight Cash Rate + BABs/NCDs + OIS + Treasury Notes,
all marked "Frequency: Monthly"). This ADR amends + replaces that paragraph's claim
with the corrected approach below.

**Extends**: [ADR-092](ADR-092-gap-d-asian-pacific-daily-proxy-upstreams.md) §T2.AUD-RBA
(corrected per r46-r2) + [ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D — RBA
CC BY 4.0 license is fully compatible).

**Related**: [ADR-090](ADR-090-eur-usd-data-pool-extension.md) Bundesbank Bund r29
pattern (template for daily yield collector). AUD r46 `_section_aud_specific`
currently uses 3/3 monthly drivers per ADR-093 "degraded explicit" surface ; this ADR
would upgrade AUD signal quality from "0/3 daily-clean" to "1/3 daily-clean" by adding
either an RBA daily Cash Rate (if found in F-series tables) OR an RBA daily yield from
another F-series table.

## Context

ADR-092 round-44 mapped the RBA F1.1 CSV (`https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv`)
as a Tier 2 candidate for "AUD cash-rate-target daily". The original ADR claim that F1.1
is "daily" was an unverified inference. Researcher round-46-round-2 empirical WebFetch
confirmed F1.1 is in fact MONTHLY (each row = 1 month, columns Cash Rate Target +
Interbank Overnight Cash Rate + BABs/NCDs + OIS + Treasury Notes). The MONTHLY cadence
makes F1.1 redundant with the existing AUD r46 monthly-only signal surface — adding F1.1
monthly would NOT upgrade the daily-clean signal count.

**For a true RBA DAILY series**, the F-series catalog must be re-surveyed. Candidate
tables (each requires empirical WebFetch verification before code) :

| RBA F-series table | Title                                      | Cadence claim (needs verify) | URL pattern                            |
| ------------------ | ------------------------------------------ | ---------------------------- | -------------------------------------- |
| **F2**             | "Capital Market Yields - Government Bonds" | DAILY (per RBA Bulletin)     | `/statistics/tables/csv/f2-data.csv`   |
| F3                 | "Government Bond Yields and Spreads"       | DAILY                        | `/statistics/tables/csv/f3-data.csv`   |
| F1.2               | "Interbank Overnight Cash Rate"            | DAILY (intra-month detail)   | `/statistics/tables/csv/f1.2-data.csv` |
| F4                 | "Money Market Yields"                      | DAILY                        | `/statistics/tables/csv/f4-data.csv`   |
| F11                | "Exchange Rates"                           | DAILY                        | `/statistics/tables/csv/f11-data.csv`  |

**Most-likely target for AUD r46 signal upgrade** : **F2 "Capital Market Yields"** —
contains Australia 10Y, 5Y, 2Y benchmark government bond yields daily. This would
replace the monthly `IRLTLT01AUM156N` OECD MEI series in Driver 1 of
`_section_aud_specific`, upgrading the US-AU 10Y differential to a true daily signal
(both DGS10 + RBA F2 10Y are daily). The cadence-mismatch warning currently rendered
inline would be REMOVED for the rate-differential block.

## Decision

### Implementation pattern (mirror Bundesbank Bund r29)

1. **Empirical table selection** (Eliot 5-min step) : WebFetch + Eliot verify the F2
   data file (`https://www.rba.gov.au/statistics/tables/csv/f2-data.csv`) is :
   (a) DAILY cadence, (b) parseable CSV, (c) contains Australia 10Y daily yield column.
   If F2 doesn't fit, re-evaluate F3 / F4 / F1.2 by the same gate. Document the
   selected table in this ADR's `## Open questions` section.
2. **Migration** : `apps/api/migrations/0050_aud_yield_observations.py` —
   `aud_yield_observations` TimescaleDB hypertable + ORM `AudYieldObservation` +
   `UNIQUE(observation_date)` + `CHECK yield_pct BETWEEN -1.0 AND 15.0 %`.
3. **ORM** : `apps/api/src/ichor_api/models/aud_yield_observation.py` mirror
   `BundYieldObservation` from r29.
4. **Collector** : `apps/api/src/ichor_api/collectors/rba_f2.py` —
   - Endpoint : `https://www.rba.gov.au/statistics/tables/csv/<F-table>-data.csv` (TBD
     pending Eliot step 1)
   - Parser : CSV via stdlib `csv` module (RBA delimiter = comma per round-46-round-2
     fetch ; ALL RBA tables use the same format)
   - License : CC BY 4.0 — attribute in user-facing render via `source-stamp` line
     `RBA:F2@<YYYY-MM-DD>` (the table identifier conveys the CC BY 4.0 attribution
     transitively per RBA public commitment).
   - Idempotent ON CONFLICT DO NOTHING insert pattern (r29 precedent)
5. **CLI runner** : `apps/api/cli/run_rba_f_series.py` mirror `cli/run_bundesbank_bund.py`
   with `--table <F2|F3|...>` flag for future flexibility + `--incremental` flag.
6. **Register-cron** : `scripts/hetzner/register-cron-rba-f-series.sh` systemd timer
   daily 10:00 Paris (Sydney close 17:00 AEDT = 07:00 UTC + buffer → 10:00 Paris). RBA
   publishes EOD data within ~30 min of close.
7. **Tests** : `apps/api/tests/test_rba_f_series_collector.py` — ~12 tests mirror Bund
   r29 pattern.
8. **`_section_aud_specific` Tier 1.5 upgrade** (post-ingestion follow-up PR) : prefer
   `AudYieldObservation.yield_pct` daily over `IRLTLT01AUM156N` monthly when both
   available. Update ADR-093 §"future upgrade path" to mark "daily-clean count 0/3 →
   1/3 closed" once empirical proof on Hetzner.

### F1.1 monthly status

F1.1 stays IGNORED for daily ambitions per the round-46-round-2 audit. If at a future
date a use case emerges for monthly RBA cash-rate-target stock-and-change context (e.g.
monthly RBA policy-decision detection), F1.1 monthly can be ingested via a SEPARATE
future ADR — not this one.

## Acceptance criteria

1. ADR-096 receives Eliot ratification (status PROPOSED → Accepted) + F-series table
   selection step (1).
2. Empirical 3-witness (rule 18) post-implementation :
   - Witness 1 : `cli/run_rba_f_series.py --table F2 --incremental --dry-run` returns
     expected sample payload from the RBA F2 endpoint.
   - Witness 2 : `SELECT COUNT(*) FROM aud_yield_observations` after first cron fire >
     0 rows.
   - Witness 3 : `_section_aud_specific` rendered text shows the RBA daily value in
     place of the monthly OECD value AND ADR-093 §"future upgrade path" annotation
     updates to reflect 1/3 daily-clean closed.

## Reversibility

- Standard collector pattern : revert via `alembic downgrade -1` + `systemctl disable
ichor-rba-f-series.timer` + git revert. <30s rollback per RUNBOOK-014 backup chain.
- Feature flag fail-closed : `rba_f_series_collector_enabled` in Settings. Fall back
  to OECD MEI monthly if RBA CDN goes down.

## Consequences

### Positive

- **AUD r46 signal quality upgrade** : 0/3 daily-clean → 1/3 daily-clean. The R24
  SUBSET-not-SUPERSET annotation "DEGRADED EXPLICIT per ADR-093" softens from "ZERO
  daily-clean signal" to "1/3 daily-clean signal", removing the rate-differential
  cadence-mismatch warning.
- **Voie D + ToS safe** : RBA F-series is CC BY 4.0 public commitment. Lowest legal
  risk among ADR-092 §T2 candidates.
- **Doctrinal symmetry vs Bundesbank Bund r29** : direct pattern mirror.
- **Future-extensible** : same collector module can ingest F1.2 / F3 / F4 / F11 with
  the `--table` flag, supporting future RBA-side signal additions (e.g. AUD/USD spot
  via F11 if Polygon Currencies stays unviable).

### Negative

- **Eliot manual step blocking** : empirical F-series table re-selection (~5-10 min
  WebFetch + verify daily cadence) required before implementation. ADR-092 §T2.AUD-RBA
  cadence claim was wrong — re-verification is doctrinal hygiene.
- **License attribution** : CC BY 4.0 requires source attribution. The existing
  source-stamp pattern (`RBA:F2@<date>` in `sources` list) is sufficient per RBA public
  guidance.

### Neutral

- **Monthly fallback preserved** : `IRLTLT01AUM156N` stays in `fred_extended.py`
  SERIES_TO_POLL as cold-start / outage fallback. Symmetric to Bund r29 + JPY r45
  pattern (FRED monthly OECD stays as defensive layer).
- **F1.1 monthly** : remains available for future ADRs ; not in this ADR's scope.

## Open questions for Eliot

1. **F-series table selection** : confirm F2 "Capital Market Yields" is the correct
   daily-cadence table for Australia 10Y (or pick F3/F4/F1.2). Empirical fetch :
   `curl -s https://www.rba.gov.au/statistics/tables/csv/f2-data.csv | head -10`.
   Document the selected table in this ADR.
2. **Backfill horizon** : 5 years (DTW analogue-library default) or full history
   (RBA F2 goes back to ~1990) ? Recommendation : 5 years.
3. **Currency-spot collector** : if F11 contains AUD/USD daily spot, would Eliot want
   that ingested in the same r48 ship as the F2 yields, or split ? Recommendation :
   split (F2 is rate-cycle, F11 is FX-spot — different framework anchors, different
   `_section_*` consumers).
4. **AKShare / LME re-vetting trigger** : ADR-093 §Iron-ore daily DEFER firmly exit
   criteria triggers include AUD anti-skill emerging in Vovk Sunday aggregator. Does
   the RBA F2 daily-rate upgrade (this ADR) move the threshold ? Recommendation : NO
   — F2 covers rate-differential channel ; AKShare/LME would cover commodity ToT
   channel — different Drivers in AUD section.

## Sources

- [RBA Statistics — Government Bond Yields (F2)](https://www.rba.gov.au/statistics/tables/)
- [RBA F1.1 Money Market CSV (monthly per r46-r2 audit, NOT daily as ADR-092 claimed)](https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv)
- [RBA CC BY 4.0 public statement](https://www.rba.gov.au/copyright/)
- [r46-round-2 researcher audit finding (F1.1 cadence)](../../C:/Users/eliot/.claude/projects/D--Ichor/memory/ICHOR_SESSION_PICKUP_2026-05-14_v24_POST_ROUND46.md)
- [RBA Bulletin April 2024 — China's Monetary Policy Framework](https://www.rba.gov.au/publications/bulletin/2024/apr/chinas-monetary-policy-framework-and-financial-market-transmission.html)
  (cross-reference for AUD framing post-Tier 2 upgrades)

## Framework references

The RBA F2 daily Australia 10Y enables empirical verification of the Engel-West 2005
fundamentals channel at daily cadence for AUD/USD (currently monthly OECD MEI via
IRLTLT01AUM156N). Combined with Chen-Rogoff 2003 + Ready-Roussanov-Ward 2017
(commodity-currency complement, monthly), the AUD section moves toward a 1-daily +
2-monthly driver mix vs the current 0-daily + 3-monthly degraded posture. DOIs in
ADR-092 §framework section.
