# ADR-094: BoJ Time-Series JGB 10Y daily collector (Tier 2 GAP-D upgrade)

**Status**: PROPOSED (round-46-round-3, 2026-05-14) — awaiting Eliot UI exploration of
stat-search.boj.or.jp series code identification before implementation. No code shipped
by this ADR.

**Date**: 2026-05-14

**Supersedes**: none

**Extends**: [ADR-092](ADR-092-gap-d-asian-pacific-daily-proxy-upstreams.md) §T2.JPY-Daily
(Tier 2 BoJ JGB daily collector deferred path) + [ADR-009](ADR-009-voie-d-no-api-consumption.md)
(Voie D spend discipline — BoJ API free + public, no auth).

**Related**: [ADR-090](ADR-090-eur-usd-data-pool-extension.md) Bundesbank Bund r29 pattern
(SDMX-CSV collector with daily cadence) — direct template precedent for the BoJ-side
implementation. JPY r45 `_section_jpy_specific` currently uses `IRLTLT01JPM156N` (Japan
10Y monthly via OECD MEI / FRED) ; this ADR's daily collector would upgrade JPY signal
quality from "1/2 daily-clean" to "2/2 daily-clean", removing the cadence-mismatch
warning currently rendered inline.

## Context

Round-44 ADR-092 mapped the BoJ Time-Series Data Search API as a Tier 2 candidate for
JGB 10Y daily ingestion. The API launched 2026-02-18 (T-3 months at ADR-092 writing)
per the BoJ launch notice. Two community Python wrappers exist (`bojpy`,
`delihiros/boj-api-client`) — both confirm the API is public + auth-free + free.

**The blocker is purely series-code identification** : the BoJ API uses a `<PREFIX>'<CODE>`
pattern (e.g. `BS01'MABJMTA` for an accounting indicator). The JGB 10Y benchmark code
was not surfaced by the round-46-round-3 researcher dispatch (WebFetch on the API manual

- search via DuckDuckGo on community wrappers' GitHub READMEs returned only the
  accounting example). The canonical code for "JGB 10Y daily benchmark yield" must be
  extracted from the stat-search.boj.or.jp UI under Financial Markets → Interest Rates →
  Government Bond Yields, by an Eliot manual exploration step (estimated 15-30 minutes).

Once the code is confirmed, the implementation pattern is identical to the Bundesbank
Bund r29 ship : 1 alembic migration + 1 ORM model + 1 collector + 1 CLI runner + 1
register-cron script. The full ship cost is ~2 dev-days from code confirmation.

## Decision

### Implementation pattern (mirror Bundesbank Bund r29)

1. **Migration** : `apps/api/migrations/0049_jgb_yield_observations.py` —
   `jgb_yield_observations` TimescaleDB hypertable + ORM `JgbYieldObservation` +
   `UNIQUE(observation_date)` + `CHECK yield_pct BETWEEN -1.0 AND 10.0 %`.
2. **ORM** : `apps/api/src/ichor_api/models/jgb_yield_observation.py` mirror
   `BundYieldObservation` from r29.
3. **Collector** : `apps/api/src/ichor_api/collectors/boj_jgb.py` —
   - Endpoint : `https://www.stat-search.boj.or.jp/api/v1/getDataCode?code=<JGB_10Y_CODE>`
     (TBD pending Eliot UI step ; placeholder `BS01'<JGB_10Y_BENCHMARK_CODE>`)
   - Parser : JSON response per BoJ API manual (download from
     `stat-search.boj.or.jp/info/api_manual_en.pdf` at impl time to confirm exact schema)
   - Idempotent ON CONFLICT DO NOTHING insert pattern (r29 precedent)
   - Conservative request rate : 1 request/day via cron (~365 requests/year, well under
     BoJ rate-limits which are not published but assumed liberal for daily-cadence usage)
4. **CLI runner** : `apps/api/cli/run_boj_jgb.py` mirror `cli/run_bundesbank_bund.py`
   with `--incremental` flag.
5. **Register-cron** : `scripts/hetzner/register-cron-boj-jgb.sh` systemd timer daily
   11:00 Paris (Tokyo close 15:00 JST + 2h buffer + 6h timezone delta = 11:00 Paris next
   morning — covers asia-session closing yields).
6. **Tests** : `apps/api/tests/test_boj_jgb_collector.py` — ~12 tests covering parser
   happy-path + idempotent insert + ORM round-trip + W90 invariant.
7. **`_section_jpy_specific` extension** (post-ingestion) : add a Tier 1.5 block that
   prefers `JgbYieldObservation.yield_pct` daily over `IRLTLT01JPM156N` monthly when both
   are available, falling back to the monthly OECD MEI series when the BoJ collector is
   dormant or pre-deploy. This is a follow-up post-ADR-094 ship in a future round.

### Series code identification protocol (Eliot manual step)

Eliot exploration procedure :

1. Navigate to `https://www.stat-search.boj.or.jp/index_en.html`
2. Top menu → "List of Statistics" → "Financial Markets" → "Interest Rates"
3. Drill to "Treasury and JGB Yields" (the exact wording may vary by translation)
4. Identify the time-series for "Japanese Government Bond 10-Year Benchmark Yield"
   (daily cadence, available since at least 1986)
5. Click the series — the URL or metadata pane will display the canonical
   `<PREFIX>'<CODE>` identifier. Document it in this ADR's `## Open questions` section
   before merging the BoJ JGB collector implementation.

Estimated time : 15-30 minutes Eliot manual.

## Acceptance criteria

1. ADR-094 receives Eliot ratification (status PROPOSED → Accepted).
2. JGB 10Y benchmark series code is documented in this ADR's `## Open questions`
   section by Eliot.
3. Implementation lands per the 7-step pattern above.
4. Empirical 3-witness (rule 18) :
   - Witness 1 : `cli/run_boj_jgb.py --incremental --dry-run` returns expected sample
     payload from the JGB 10Y endpoint.
   - Witness 2 : `SELECT COUNT(*) FROM jgb_yield_observations` after first cron fire >
     0 rows.
   - Witness 3 : `_section_jpy_specific` rendered text shows the BoJ JGB daily value
     in place of the monthly OECD value when both are present + frequency-mismatch
     warning is REMOVED for the rate-differential block.

## Reversibility

- Standard collector pattern : revert via `alembic downgrade -1` + `systemctl disable
ichor-boj-jgb.timer` + git revert. <30s rollback per RUNBOOK-014 backup chain.
- Feature flag fail-closed : `boj_jgb_collector_enabled` in Settings. If the BoJ API
  rate-limits us or returns invalid data, the flag flips to false and the section
  falls back to OECD MEI monthly.

## Consequences

### Positive

- **JPY r45 signal quality upgrade** : 1/2 daily-clean → 2/2 daily-clean, removes the
  cadence-mismatch warning from `_section_jpy_specific`, makes the US-JP 10Y differential
  a real-time intraday signal instead of a REGIME indicator.
- **Voie D respected** : zero new spend (BoJ API free + public). No auth surface.
- **Doctrinal symmetry vs Bundesbank Bund r29** : direct pattern mirror, low novel risk.
- **Ito-Yabu 2007 intervention reaction function** (ADR-095 future) gets a richer
  context once BoJ JGB daily + e-Stat MoF intervention monthly are both ingested. The
  pair forms a 2-leg "BoJ stance + intervention threat" surface.

### Negative

- **Eliot manual step blocking** : ~15-30 min UI exploration required before implementation
  can proceed. Estimated impact : 1 calendar day defer (Eliot's session schedule).
- **BoJ API rate-limit risk unknown** : the launch notice does not specify rate caps.
  Conservative 1 request/day cron mitigates, but a future spike (backfill scenario) may
  hit unspecified limits. Defense : feature flag + retry envelope `(5,15,45,90)` per r28
  precedent.

### Neutral

- **JGB stock + macro surface** : the BoJ Time-Series API has hundreds of series. r46
  Tier 2 scope is JGB 10Y benchmark only. If empirical Brier improvement is measurable
  post-ship, follow-up ADRs can add JGB 2Y / 5Y / 30Y for the full yield-curve surface.
- **Monthly fallback preserved** : `IRLTLT01JPM156N` remains in `fred_extended.py`
  SERIES_TO_POLL as the cold-start / outage fallback. Pre-r29 Bund precedent : the FRED
  monthly Germany 10Y stayed too.

## Open questions for Eliot

1. **Confirm JGB 10Y benchmark series code** via stat-search.boj.or.jp UI exploration
   (~15-30 min). Documented placeholder in §Implementation §3 ; replace before merging
   the impl PR.
2. **Cron timing** : daily 11:00 Paris is the recommended slot (Tokyo close +2h buffer).
   Alternative : daily 02:00 Paris (Tokyo close +12h = next business day 09:00 JST,
   captures the prior session more reliably during summer DST). Eliot doctrinal call.
3. **Backfill horizon** : 5 years (matches FRED Bund Bundesbank r29 backfill) or full
   history (since 1986) ? Recommendation : 5 years to match analogue-library DTW
   windows (~252 trading days × 5 = 1260 obs ample).
4. **Series-curve extension** : after JGB 10Y benchmark ships, do JGB 2Y / 5Y / 30Y for
   the yield-curve surface ? Recommendation : DEFER until JGB 10Y empirical Brier
   improvement measurable in Vovk Sunday aggregator.

## Sources

- [BoJ API Launch Notice 2026-02-18](https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm)
- [BoJ Time-Series Data Search portal](https://www.stat-search.boj.or.jp/index_en.html)
- [BoJ API User Manual (PDF)](https://www.stat-search.boj.or.jp/info/api_manual_en.pdf)
- [bojpy Python wrapper](https://github.com/philsv/bojpy)
- [delihiros/boj-api-client wrapper](https://github.com/delihiros/boj-api-client)
- [BoJ Outright Purchases JGBs (cross-reference for the JGB 10Y benchmark family)](https://www.boj.or.jp/en/mopo/measures/mkt_ope/ope_f/index.htm)

## Framework references

The BoJ JGB daily series enables empirical verification of the Engel-West 2005
fundamentals channel + Ito-Yabu 2007 intervention reaction function at daily cadence
(currently both rely on monthly OECD MEI). DOI references in ADR-092 §framework
section.
