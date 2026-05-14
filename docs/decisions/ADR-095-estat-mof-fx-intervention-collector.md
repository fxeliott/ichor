# ADR-095: e-Stat MoF FX intervention monthly collector (Tier 2 GAP-D upgrade)

**Status**: PROPOSED (round-46-round-5, 2026-05-14) — awaiting Eliot ratification +
empirical statsDataId verification step. No code shipped by this ADR.

**Date**: 2026-05-14

**Supersedes**: none

**Extends**: [ADR-092](ADR-092-gap-d-asian-pacific-daily-proxy-upstreams.md) §T2.JPY-Intervention
(Tier 2 e-Stat MoF FX intervention monthly collector deferred path) +
[ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D — e-Stat API free, requires
appId registration ; no metered cost).

**Related**: [ADR-094](ADR-094-boj-jgb-daily-collector.md) BoJ JGB daily collector
(complementary — BoJ stance + MoF intervention threat form a 2-leg "Japan monetary
operations" surface). JPY r45 `_section_jpy_specific` currently references Ito-Yabu
2007 reaction function DOI:10.1016/j.jimonfin.2006.12.001 inline as deferred-context ;
this ADR's implementation lets the section consume actual intervention data when the
collector is active.

## Context

Round-44 ADR-092 mapped the e-Stat Japan FX intervention monthly dataset as a Tier 2
candidate (`statsDataId=000040061200`, framework-anchored on Ito-Yabu 2007 reaction
function). The dataset publishes monthly Ministry of Finance FX intervention
operations (intervention amount in trillion JPY, dates, direction USD-JPY buy/sell).

**Round-46-round-2 researcher audit flagged two latent issues** :

1. **statsDataId `000040061200` unconfirmed** : researcher WebFetch on the e-Stat URL
   `https://www.e-stat.go.jp/en/stat-search/files?...stat_infid=000040061200` did not
   resolve to the expected MoF FX intervention dataset. Example statsDataIds returned
   by e-Stat search are 7-digit numerical (`0003036792`, `0003103532`) or alphanumeric
   (`C0020050213000`). The 12-digit `000040061200` format does not match the e-Stat
   conventional pattern.

2. **Possible upstream pivot** : MoF Japan publishes the FX intervention operations
   directly at `https://www.mof.go.jp/english/policy/international_policy/reference/feio/monthly/index.html`
   as monthly Excel/CSV downloads. If the e-Stat statsDataId cannot be confirmed, the
   collector can pivot to mof.go.jp direct CSV scrape (slightly higher maintenance
   cost but eliminates the e-Stat appId dependency).

**Round-46-round-5 researcher dispatch confirms** :

- e-Stat API endpoint `https://api.e-stat.go.jp/rest/3.0/app/getStatsData` is LIVE
  (HTTP 200 base URL, requires appId).
- Free `appId` registration still functional in 2026 at e-stat.go.jp MyPage portal
  (3 applications max per account — non-blocker for Ichor's 1-env).
- Researcher could NOT confirm `statsDataId=000040061200` via web search ; the
  identifier may be wrong or have changed since ADR-092 was authored.

## Decision

### Path A : e-Stat API (preferred if statsDataId confirmable)

1. **Eliot step (~10 min) — empirical verification** : navigate to e-stat.go.jp and
   manually search for "外国為替平衡操作" (Foreign Exchange Equalization Operations)
   OR "Ministry of Finance FX intervention" in the dataset catalog. Document the
   actual statsDataId in this ADR's `## Open questions` section.
2. **Register appId** at e-stat.go.jp MyPage. Store in `infra/secrets/estat.env`
   (SOPS-encrypted) + add to `Settings.estat_app_id` Pydantic field.
3. **Migration** : `apps/api/migrations/0051_mof_fx_intervention.py` —
   `mof_fx_intervention_observations` TimescaleDB hypertable + ORM
   `MofFxInterventionObservation` + `UNIQUE(operation_date)` + columns
   (operation_date, direction enum {BUY_USD, SELL_USD, BUY_JPY, SELL_JPY},
   amount_jpy_trillion Decimal, counterparty TEXT NULL).
4. **ORM** : `apps/api/src/ichor_api/models/mof_fx_intervention_observation.py` mirror
   `BundYieldObservation` from r29.
5. **Collector** : `apps/api/src/ichor_api/collectors/estat_mof_intervention.py` —
   - Endpoint : `https://api.e-stat.go.jp/rest/3.0/app/getStatsData?appId=$ESTAT_APP_ID&statsDataId=<TBD>`
   - Parser : JSON response per e-Stat API spec (download manual from
     `e-stat.go.jp/api/en/api-spec/how_to_use` at impl time)
   - Idempotent ON CONFLICT DO NOTHING insert pattern (r29 precedent)
   - Conservative request rate : 1 request/month via cron (MoF publishes ~once/month)
6. **CLI runner** : `apps/api/cli/run_estat_mof_intervention.py`
7. **Register-cron** : `scripts/hetzner/register-cron-estat-mof.sh` systemd timer
   monthly first-business-day-Tokyo-close +24h = Paris 11:00 the next morning
   (covers typical 1-week MoF publication lag).
8. **Tests** : `apps/api/tests/test_estat_mof_intervention_collector.py` — ~12 tests.

### Path B : mof.go.jp direct CSV scrape (fallback if e-Stat blocked)

1. **No appId needed** — public download page.
2. **Endpoint** : `https://www.mof.go.jp/english/policy/international_policy/reference/feio/monthly/<YYYY>.csv`
   (URL pattern TBD ; researcher to confirm exact path during impl).
3. **Maintenance risk** : MoF page format could change without notice ; periodic CI
   parser-drift test recommended.

### `_section_jpy_specific` consumption pattern (post-ingestion follow-up)

Once the collector is active, extend `_section_jpy_specific` with a Driver 3 block :

- If MoF intervention observation within last 60 days : surface "MoF intervention
  threat tag" with Ito-Yabu 2007 reaction-function framing (deviation vs 21-day MA +
  asymmetric political cost — strong JPY hurts exporters)
- ADR-017 boundary preserved : no "BUY JPY now" framing — only conditional probability
  language ("MoF intervention probability elevated when USD/JPY > 160 + 21d MA
  deviation > +5σ" etc.)
- Tetlock invalidation : threat-tag invalidated if 60 days pass without intervention
  AND USD/JPY > intervention-threshold persistently

## Acceptance criteria

1. ADR-095 receives Eliot ratification (status PROPOSED → Accepted).
2. statsDataId is empirically confirmed via e-Stat search (Path A) OR mof.go.jp URL
   pattern is verified (Path B). Documented in this ADR.
3. Empirical 3-witness (rule 18) post-implementation :
   - Witness 1 : `cli/run_estat_mof_intervention.py --dry-run` returns expected sample
     payload.
   - Witness 2 : `SELECT COUNT(*) FROM mof_fx_intervention_observations` after first
     cron fire > 0 rows AND most-recent operation_date matches publicly-known recent
     interventions (e.g. 2024 JPY interventions ¥9.79T total per MoF disclosures).
   - Witness 3 : `_section_jpy_specific` rendered text shows MoF intervention threat
     tag when observation within 60 days, OR silent skip when no recent intervention.

## Reversibility

- Standard collector pattern : revert via `alembic downgrade -1` + `systemctl disable
ichor-estat-mof.timer` + git revert. <30s rollback per RUNBOOK-014 backup chain.
- Feature flag fail-closed : `estat_mof_collector_enabled` in Settings. Pivot to
  Path B (mof.go.jp scrape) if e-Stat API rate-limits us OR statsDataId changes.

## Consequences

### Positive

- **JPY r45 framework completion** : Ito-Yabu 2007 reaction function gets actual
  data, not just inline citation. The intervention-threat surface lets Pass-2 LLM
  read MoF policy reaction asymmetry properly.
- **Voie D respected** : zero metered spend (e-Stat appId free, MoF direct free).
- **Doctrinal symmetry vs r29 + r34** : monthly cadence + frequency-mismatch warning
  pattern consistent with BTP r34 + Bund r29.
- **Complementary to ADR-094 BoJ JGB daily** : the 2 collectors together form a "Japan
  monetary operations surface" — BoJ stance (daily) + MoF intervention threat
  (monthly).

### Negative

- **2 Eliot manual steps blocking** : (a) statsDataId confirmation (~10 min e-Stat
  search), (b) appId registration (~5 min). Total impact : 1 calendar day defer.
- **e-Stat API rate-limit** : 3 appId max per account, but request rate caps unknown.
  Defense : monthly cron + retry envelope.
- **Path B maintenance** : if pivot to mof.go.jp scrape, parser-drift CI test needed.
- **statsDataId may have changed** : the ADR-092 r44 claim of `000040061200` was
  unverified ; round-46-r2 + r5 researcher dispatch failed to confirm. Highest-risk
  unknown of the Tier 2 collectors.

### Neutral

- **MoF intervention sparsity** : Japan intervenes ~once every 3-6 years
  (2022 + 2024 episodes ; ~2011 + 2003 prior). The data is mostly empty rows.
  Acceptable signal density per Ito-Yabu — the rare interventions are
  high-conviction-tags when they happen.
- **Backfill horizon** : 1991 → present for MoF historical disclosures, ~33 years.
  Trivial DB cost.

## Open questions for Eliot

1. **Confirm statsDataId** via e-stat.go.jp search OR commit to Path B mof.go.jp
   direct CSV scrape. Recommendation : try Path A first (10 min) ; pivot to B if
   statsDataId cannot be confirmed.
2. **appId registration** : Eliot creates the appId at e-Stat MyPage + adds to
   `infra/secrets/estat.env` (SOPS-encrypted). ~5 min.
3. **Intervention-threat surface threshold** : USD/JPY > X.X triggers the threat
   tag, X.X TBD per recent intervention data + Ito-Yabu calibration. Defer to
   post-impl r48+.

## Sources

- [e-Stat API portal](https://www.e-stat.go.jp/api/en)
- [e-Stat How to use API](https://www.e-stat.go.jp/api/en/api-dev/how_to_use)
- [MoF Japan FX Intervention Operations monthly disclosure](https://www.mof.go.jp/english/policy/international_policy/reference/feio/monthly/index.html)
- [Ito & Yabu 2007 — What prompts Japan to intervene in the Forex market ?](https://doi.org/10.1016/j.jimonfin.2006.12.001) (DOI corrected from .11.002 per r44 verifier ; .12.001 = Ito-Yabu, .11.002 = Kasuga 2007 adjacent paper)
- [Round-46-round-2 + round-3 researcher audit (statsDataId unconfirmed)](../../C:/Users/eliot/.claude/projects/D--Ichor/memory/ICHOR_SESSION_PICKUP_2026-05-14_v24_POST_ROUND46.md)

## Framework references

The MoF FX intervention monthly data enables empirical verification of the
**Ito-Yabu 2007** reaction function : friction-ordered-probit model of MoF
intervention based on deviation vs 21-day moving-average + asymmetric political
cost (strong JPY hurts exporters, weak JPY hurts importers ; MoF reacts more
aggressively to strong JPY excursions per the political-economy framework).

Combined with **Brunnermeier-Nagel-Pedersen 2009** carry-crash skew (already cited
in `_section_jpy_specific` r45), the section can flag the "MoF threat + carry-crash
risk" combo configuration which historically precedes intervention episodes.

Combined with **ADR-094 BoJ JGB daily** (post-ship), the JPY section becomes a
3-driver framework :

- Driver 1 : US-JP rate-differential (Engel-West 2005 fundamentals)
- Driver 2 : BoJ stance (JGB 10Y daily, post-ADR-094)
- Driver 3 : MoF intervention threat (post-ADR-095)
