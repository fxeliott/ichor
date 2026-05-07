# ADR-036: GEOPOL_FLASH alert — AI-GPR z-score against trailing 30d

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP D.5.b.1

## Context

Geopolitical risk repricing is a recurring driver of intraday moves
in havens (gold, JPY, CHF, USD), oil, and risk currencies. Caldara &
Iacoviello (2022, *American Economic Review* 112(4)) introduced the
**Geopolitical Risk Index (GPR)** — a monthly text-search-based
measure built from 10 newspapers since 1985. In March 2026, the
San Francisco Federal Reserve published an upgraded version :
**AI-GPR** (Iacoviello & Tong 2026), which uses GPT-4o-mini to score
~5 million articles from the New York Times, Washington Post and
Chicago Tribune (1960-present) at **daily** frequency, replacing
keyword matching with semantic understanding. The AI-GPR is more
reactive than the original (week-scale vs month-scale) and assigns
gradations of risk intensity rather than binary classifications.

Ichor already collects the AI-GPR daily via
`apps/api/src/ichor_api/collectors/ai_gpr.py` (cron 23h Paris) and
persists into `gpr_observations`. The collector even ships a
`delta_30d()` helper that computes a z-score-style 30d delta. But
nothing in the alert catalog exposes a fire-on-spike pathway — a
trader would have to read the data_pool block manually.

This ADR adds **GEOPOL_FLASH**, a catalog alert that fires when the
latest AI-GPR reading is more than 2σ away from its trailing 30d
distribution.

## Decision

Wire one new catalog alert :

```python
AlertDef("GEOPOL_FLASH", warning,
         "Burst geopolitique AI-GPR z={value:+.2f}",
         "ai_gpr_z", 2.0, "above", ...)
```

Fires when `|z| >= 2.0` where :

```
z = (current - mean(history_30d)) / std(history_30d)
```

The history window EXCLUDES the current point so the baseline is not
biased by the very value we're testing.

### Implementation : pure SQL + Python

`services/geopol_flash_check.py` :

- `_fetch_recent_observations(session, *, days=44)` — pulls 30 + 14d
  buffer from `gpr_observations`, oldest-first.
- `_zscore(history, current)` — defensive : returns `(None, None,
  None)` below `_MIN_ZSCORE_HISTORY = 20` ; returns `(None, mean,
  std)` if std == 0 (degenerate).
- `evaluate_geopol_flash(session, *, persist=True)` — fetches,
  computes, fires `check_metric("ai_gpr_z", z, asset=None,
  extra_payload={...})` when threshold crossed AND persist=True.

### Cron schedule

Daily 23:30 Paris (after the AI-GPR collector lands at 23h Paris,
+30 min buffer for the parser to push to DB). Pure SQL z-score runs
in < 200 ms. Daily slot keeps the alert state fresh as new readings
arrive.

### Asset semantics : `None` (macro-broad)

GEOPOL_FLASH is fundamentally a **macro environmental** alert : it
doesn't target one asset but signals that a class of assets (havens)
is likely to react. Aligning with the existing
`LIQUIDITY_TIGHTENING` pattern, `asset = None`. The `extra_payload`
includes a `havens_likely_to_move` list (`XAU_USD`, `USD_JPY`,
`USD_CHF`, `DXY`) so the trader can immediately see where the
signal is most actionable.

### Source-stamping (ADR-017)

`extra_payload.source = "ai_gpr:caldara_iacoviello"`. Plus the raw
diagnostics (`ai_gpr_value`, `ai_gpr_date`, `baseline_mean`,
`baseline_std`, `n_history`, `havens_likely_to_move`) so any
audit consumer can re-derive the alert from the observation record.

### Threshold rationale

`|z| >= 2.0` is the catalog convention shared with
`DATA_SURPRISE_Z` and `REAL_YIELD_GOLD_DIVERGENCE` (Phase D.5
sister alerts). 2σ on a 30d window corresponds to a roughly 1-in-20
event under approximate normality — rare enough to avoid fatigue,
common enough to be informative.

## Consequences

### Pros

- **Trader-actionable** : geopolitical regime shifts are otherwise
  buried in news flow. A 2σ AI-GPR spike is an objective signal that
  *something* is happening at scale across 5M articles, not a
  narrative claim.
- **Minimal surface** : reuses the existing `gpr_observations` table
  (no new migrations) and the existing collector cron (no new feed).
  Only a new service + CLI + register-cron + AlertDef.
- **Bidirectional** : `default_direction="above"` on `|z|` —
  catches both up-spikes (escalation) and down-excursions (de-escalation
  / risk repricing on positive geopolitical news, e.g. ceasefire).
- **Source-stamped + reproducible** : the alert payload contains the
  exact AI-GPR value and date the alert was computed against. If a
  trader disputes the alert in 6 months, the audit log re-derives
  identically.
- **Cheap** : ~1 alert-firing per ~10-20 days under typical regimes
  (2σ on a 30d window). Each fires through a single `check_metric`
  call — same path as 32+ other alerts.

### Cons

- **30d window may dampen long-cycle regimes** : if geopolitical
  tension builds slowly over months (e.g. cumulative trade-war
  escalation), the 30d baseline drifts up and the relative z-score
  shrinks even though absolute risk is high. Mitigation : a longer-
  window companion alert (e.g. 252d) could be added in Phase E if
  needed. For now, the daily-frequency reactivity is the priority.
- **Single-source dependency** : the AI-GPR is one provider's index
  (Caldara-Iacoviello). If the methodology changes upstream
  silently, our z-score interpretation drifts. Mitigation : the
  source page is monitored manually ; the LLM-scoring methodology
  is documented in the SF Fed paper.
- **No event categorization** : GEOPOL_FLASH says "spike", not
  "war / sanctions / cyber / pandemic". The original Caldara-
  Iacoviello GPR has 8 categories (war threats, peace threats,
  military buildups, nuclear threats, terror threats, beginning of
  war, escalation, terror acts) — AI-GPR collapses into a single
  intensity score. A future enhancement could add a categorical
  classifier on top of GDELT geopolitics events for finer-grained
  alerts (cf TARIFF_SHOCK as a sister alert with topic filter).

### Neutral

- The cron fires daily even when no spike. By design : the CLI
  prints a one-line "ai_gpr=X baseline=Y±Z z=W" status either way,
  so operators have visibility into the baseline drift over time.

## Alternatives considered

### A — Use only the collector helper `delta_30d`

Rejected : the helper operates on the in-memory list returned by
`fetch_latest()`. That couples the alert to collector freshness.
Reading from Postgres lets the alert run independently — even if
the AI-GPR feed is briefly down, the alert evaluates against the
last-known stored history.

### B — Multi-window z-score (30d + 90d + 252d)

Tabled (not rejected) : richer signal but multiplies the alert
volume. v1 sticks to the 30d window for trader-actionable daily
reactivity. v2 can layer a 252d "structural geopol regime" alert
in Phase E.

### C — Alert per haven asset (XAU_USD, USD_JPY, ...)

Rejected : would multiply rows by 4 for the same underlying signal.
The `havens_likely_to_move` payload list communicates the same
information without spamming the alert table. Per-haven signals
already exist (`USDJPY_INTERVENTION_RISK`, `XAU_BREAKOUT_ATH`) for
asset-specific moves driven by other channels.

### D — Hardcoded fixed threshold instead of z-score

Rejected : the AI-GPR has no natural unit (it's a relative LLM
score). A fixed value (e.g. "alert if AI-GPR > 200") would drift
with the underlying scale recalibration. The relative z-score is
self-calibrating against the rolling baseline.

### E — Use the keyword-based GPR (monthly) instead of AI-GPR

Rejected : monthly cadence is too slow for intraday trading. The
AI-GPR's daily reactivity is the entire point of using the new
methodology. The classic GPR remains useful as a Pass-1 macro
context (regime call), wired separately in `data_pool.py` if needed.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/geopol_flash_check.py` (NEW)
- `apps/api/src/ichor_api/cli/run_geopol_flash_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with one
  AlertDef + bump assert 37 → 38)
- `apps/api/tests/test_geopol_flash_check.py` (NEW, 9 tests)
- `scripts/hetzner/register-cron-geopol-flash-check.sh` (NEW)
- `docs/decisions/ADR-036-geopol-flash-alert.md` (this file)

## Related

- ADR-017 — Living Macro Entity boundary (no BUY/SELL).
- ADR-033 — DATA_SURPRISE_Z (sister Phase D.5 alert, same threshold
  convention).
- ADR-034 — REAL_YIELD_GOLD_DIVERGENCE (sister Phase D.5 alert).
- ADR-035 — QUAD_WITCHING + OPEX_GAMMA_PEAK (calendar sister).
- Caldara, Dario and Matteo Iacoviello (2022). "Measuring
  Geopolitical Risk." *American Economic Review* 112(4): 1194–1225.
- Iacoviello, Matteo and Jonathan Tong (2026). "The AI-GPR Index:
  Measuring Geopolitical Risk using Artificial Intelligence."
  Federal Reserve Board IFDP / SF Fed publication.
- Source page: https://www.matteoiacoviello.com/ai_gpr.html

## Followups

- TARIFF_SHOCK (Phase D.5.b.2) — sister alert on GDELT-filtered
  tariff narrative, ADR-037.
- Categorical AI-GPR (war / sanctions / cyber / pandemic) — once
  a per-category daily series is published.
- Multi-window companion (252d structural regime) — Phase E if
  warranted.
