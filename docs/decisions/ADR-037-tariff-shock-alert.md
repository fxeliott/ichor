# ADR-037: TARIFF_SHOCK alert — GDELT tariff narrative burst with tone gate

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP D.5.b.2

## Context

The 2026 tariff regime is the most volatile in 50 years of US trade
policy :

- **2026-02-20** — SCOTUS in *Learning Resources, Inc. v. Trump*
  (6–3) ruled that IEEPA does NOT authorize tariffs, invalidating
  the 2025 "Liberation Day" reciprocal tariffs and ~$166B of
  collected duties.
- **2026-02-25** — Trump administration pivoted to **Section 122**
  (Trade Act 1974) imposing a 10% across-the-board surcharge,
  expiring 2026-07-24 unless extended by Congress.
- **2026-03-11** — USTR launched **76 simultaneous Section 301
  investigations** covering 99% of US imports — unprecedented (avg
  <3/year over the 50-year statutory history). Hearings April 28,
  determinations within 12 months.
- **Tariff stack** layered on China-origin goods : Section 301
  (7.5–25%, some elevated 50–100%) + Section 232 (25% steel /
  10–25% aluminum) + Section 122 BOP (10%) + residual IEEPA
  litigation = effective duties >50%.
- **2026 ART program** : framework deals signed/announced with
  Argentina, Bangladesh, Cambodia, EU, India, Japan, South Korea,
  etc.

In this regime, individual tweets, USTR press releases or court
rulings can shift the entire macro narrative within hours. Trader-
relevant moves : USD/CNH, USD/MXN, EUR/USD, gold, equity risk premia.

Ichor already collects GDELT 2.0 articles (translingual news stream,
65 languages, every 15 min via DOC API ; persisted in `gdelt_events`
with `tone` ∈ [-10, +10] computed by GDELT's VADER lexicon). The
default_queries cover 8 buckets (fed, ecb, boe, boj, geopolitics,
us_data, oil, gold) — none of which is tariff-specific. Yet tariff
narrative bleeds through `geopolitics`, `us_data` and `fed` buckets.

This ADR adds **TARIFF_SHOCK**, a catalog alert that detects bursts
of tariff narrative in the GDELT flow without requiring a new
collector bucket.

## Decision

Wire one new catalog alert :

```python
AlertDef("TARIFF_SHOCK", warning,
         "Burst narrative tarif count_z={value:+.2f}",
         "tariff_count_z", 2.0, "above", ...)
```

Fires when **BOTH** :

```
count_z = (today_count - mean_30d) / std_30d  >=  2.0
avg_tone(today's tariff articles)             <= -1.5
```

The combined gate — count anomaly AND negative tone — is the standard
pattern from GDELT sentiment-burst research (knowledge4policy.ec.
europa.eu Socioeconomic Tracker ; Empirical Use of GDELT Big Data,
GLOBE-project 2024). Count alone catches benign newswire repetition
(syndication boilerplate inflates raw counts). Tone alone fluctuates
on style. Together they identify *agitated* tariff coverage at scale.

### Implementation : pure SQL filter + Python aggregation

`services/tariff_shock_check.py` :

- `TARIFF_KEYWORDS` — 16 substrings covering 2026 macro terms
  (`tariff`, `trade war`, `section 301`, `section 232`, `section
  122`, `ustr`, `protectionism`, `reciprocal tariff`, `ieepa`,
  `art program`, `liberation day`, `import dut`, etc.).
- `_fetch_tariff_articles(session, *, days=37)` — SQL query with
  `OR(GdeltEvent.title.ilike(f"%{kw}%") for kw in KEYWORDS)`. Filter
  pushed to Postgres so we don't ship the full 30d article volume
  into Python.
- `_bucket_by_day(articles, *, today)` — group SQL rows by UTC date,
  return (today_count, history_counts, today_n, today_tones,
  today_titles_sample). Title sample capped at 5 for audit drill-back.
- `_zscore(history, current)` — defensive : returns `(None, None,
  None)` below `_MIN_ZSCORE_HISTORY = 14` ; returns `(None, mean,
  std)` if std == 0 (empty history).
- `evaluate_tariff_shock(session, *, persist, today)` — orchestrate,
  fire `check_metric` only when both gates cross.

### Cron schedule

`Mon..Fri 11:30 / 15:30 / 18:30 / 22:30 Paris` — 4× business days,
covering :

- **11:30** mid-Londres pre-NY (overnight + Asia close digestion)
- **15:30** 1h post-NY-open (Trump tweets, USTR press releases,
  WH economic policy briefings tend to land 14:00-16:00 ET)
- **18:30** US PM session (mid-NY, post-lunch news cycle)
- **22:30** post-NY-close (late news + consolidation)

Weekend skipped because GDELT volume drops 60–70% (most outlets
publish less) and a count anomaly would be confounded by the
weekend baseline.

### Threshold rationale

- **`count_z >= 2.0`** : catalog convention (matches DATA_SURPRISE_Z,
  REAL_YIELD_GOLD_DIVERGENCE, GEOPOL_FLASH). 2σ on a 30d window =
  ~1-in-20 day under approximate normality.
- **`avg_tone <= -1.5`** : research benchmark for "agitated"
  reporting. GDELT VADER tone scores cluster around 0 ; -1.5 is
  ~1.5σ below typical news baseline (0 ± ~1.0 stdev for newswire).
- **AND combination** (not OR) : 2026 has frequent benign tariff
  repetition (deal announcements, ART framework progress) that
  inflates count without negative tone. The AND gate excludes those.

### Source-stamping (ADR-017)

`extra_payload.source = "gdelt:tariff_filter"`. Plus :

- `today_count`, `baseline_mean`, `baseline_std`, `n_history`
- `avg_tone_today`, `n_articles_today`
- `title_sample` (up to 5 verbatim titles for drill-back)
- `tariff_keywords_used` (the full keyword list, in case it's
  bumped between releases — the alert payload self-documents
  what was filtered against)

## Consequences

### Pros

- **Trader-actionable mid-session** : 4× business-day cadence catches
  Trump-tweet / USTR-presser bursts within ≤4h. Faster than waiting
  for a Bloomberg news ticker integration.
- **Macro-broad signal** : `asset = None` because tariff news affects
  multiple cross-rates simultaneously. Trader inspects the narrative
  + their TradingView chart of choice.
- **Reuses existing GDELT collector + table** — zero new sources, no
  migration. Just SQL filter + aggregation.
- **Combined gate eliminates false positives** : count anomaly +
  negative tone means agitated coverage, not deal-progress repetition.
- **Self-documenting payload** : `tariff_keywords_used` and
  `title_sample` let any auditor reconstruct the trigger fully.
- **Cheap** : 4 SQL queries/day × ~few hundred rows = sub-second
  per execution.

### Cons

- **Keyword-only filter** misses tariff content that doesn't use the
  16 keywords explicitly (e.g. "trade barrier", "duty hike", paywall
  paraphrase). Mitigation : keyword list is extensible ; a future
  v2 can add LLM-based topic classification on the GDELT GKG themes.
- **English-only narrative bias** : even though GDELT is translingual,
  our keywords are English. A Section 301 announcement reported in
  Le Figaro / Handelsblatt in native language won't match unless the
  outlet uses the English term (often they do — "Section 301" is
  rarely translated).
- **30d window dampens long campaigns** : if a tariff narrative ramps
  steadily over months (which is the 2026 reality given Section 301
  hearings April-October), the rolling baseline catches up and the
  z-score shrinks. Mitigation acceptable : when narrative is steady-
  high, the absolute USD/CNH move has already happened and the alert
  is post-hoc anyway. The alert's job is to catch *delta* not level.
- **Tone is GDELT VADER, not FinBERT-FOMC**. Could be migrated to
  FinBERT-tone or news-tone Couche-2 agent in a v2. Today's tone is
  the GDELT-native field already in `gdelt_events.tone` — zero
  additional cost.

### Neutral

- The cron fires 4× day even when nothing happens. The CLI prints a
  one-line "tariff today=N baseline=M±S count_z=Z avg_tone=T" status
  either way, so operators see the baseline drift.

## Alternatives considered

### A — Single threshold on count alone (no tone gate)

Rejected : 2026 has benign-deal-progress days where USTR signs an
ART framework with a partner (e.g. India, Korea) and 50+ outlets
syndicate it. Count z >> 2 with positive-or-neutral tone. Without
the tone gate, this fires TARIFF_SHOCK as if it were a new
escalation — false positive that would erode trust.

### B — OR gate (count anomaly OR negative tone)

Rejected : tone alone is a noisy signal because GDELT VADER scores
fluctuate on style across outlets. A single grumpy editorial would
trip the alert. AND requires *both* the volume and the agitation —
much higher precision.

### C — Add a "tariff" bucket to the GDELT collector DEFAULT_QUERIES

Tabled (not rejected) for v2. v1 keeps the SQL-side filter so the
alert can run *immediately* against the existing 30d backlog of
articles. Adding a bucket would require a redeploy of the collector
and 30+ days of warm-up before z-scores are credible. The SQL filter
catches articles in the 8 existing buckets (geopolitics, us_data,
fed) that mention tariff terms — a sufficient sample for v1.

### D — FinBERT-FOMC tone instead of GDELT VADER

Rejected for v1 (perfect-being-enemy-of-good). FinBERT-FOMC is
deployed in `apps/api/.venv` already (Phase 0 install) but it scores
NEWS articles with a CB-tone bias, not generic tariff sentiment. A
proper v2 would compute FinBERT-tone on the same filtered subset and
cross-check vs GDELT VADER. Out of scope for v1.

### E — Use GDELT GKG themes (ECON_TARIFF, TRADE_DISPUTE) instead of
title keywords

Rejected for v1 : we don't currently persist the GDELT GKG file
(only the DOC API article list). Going GKG would require a new
collector + table. Title-based filter is already in our schema.

### F — Hardcode threshold = 50 articles/day instead of count z-score

Rejected : tariff news flow has structural drift (more outlets cover
in 2026 than 2024). A fixed threshold would over-fire in active
periods and under-fire during lulls. Z-score is self-calibrating.

### G — Cron daily 22h Paris like REAL_YIELD_GOLD

Rejected : tariff news is intraday-actionable. A daily-only check
misses moves that would already have priced in.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/tariff_shock_check.py` (NEW)
- `apps/api/src/ichor_api/cli/run_tariff_shock_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with one
  AlertDef + bump assert 38 → 39)
- `apps/api/tests/test_tariff_shock_check.py` (NEW, 12 tests)
- `scripts/hetzner/register-cron-tariff-shock-check.sh` (NEW)
- `docs/decisions/ADR-037-tariff-shock-alert.md` (this file)

## Related

- ADR-017 — Living Macro Entity boundary (no BUY/SELL).
- ADR-033 — DATA_SURPRISE_Z (sister Phase D.5 alert, FRED proxy).
- ADR-034 — REAL_YIELD_GOLD_DIVERGENCE (sister, FRED z-score).
- ADR-035 — QUAD_WITCHING + OPEX_GAMMA_PEAK (sister, calendar).
- ADR-036 — GEOPOL_FLASH (sister Phase D.5.b alert, AI-GPR daily
  z-score). Same combined-gate philosophy minus the tone term.
- Caldara, Dario and Matteo Iacoviello (2022). "Measuring
  Geopolitical Risk." *American Economic Review* 112(4): 1194–1225.
- Knowledge for Policy / EU JRC. "GDELT Socioeconomic Tracker."
  Methodology for tone-burst sentiment monitoring.
- USTR. "2026 Trade Policy Agenda" (March 2026 annual report).
- *Learning Resources, Inc. v. Trump*, U.S. Supreme Court, 2026-02-20.

## Followups

- v2 : add FinBERT-tone score on top of VADER tone for cross-check.
- v2 : LLM-based topic classification on GDELT GKG themes (would
  require collector extension).
- v2 : add `tariff` bucket to GDELT DEFAULT_QUERIES for higher recall.
- v2 : country-specific tariff alerts (USDCNH on China-301, USDMXN on
  Mexico-122, EURUSD on EU framework).
- Capability 5 ADR-017 followup : Claude tools runtime can evaluate
  the title_sample at alert time and produce a 1-paragraph
  human-readable narrative summary.
