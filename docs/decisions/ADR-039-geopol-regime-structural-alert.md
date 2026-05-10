# ADR-039: GEOPOL_REGIME_STRUCTURAL alert — 252d AI-GPR companion to GEOPOL_FLASH

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP D.5.b structural companion (ichor-trader follow-up #2)

## Context

The Phase D.5.b.1 alert GEOPOL*FLASH (ADR-036) detects acute spikes
in AI-GPR over a **30d trailing window**. The ichor-trader review of
PR #24 flagged a gap : *"sur un slow-build régime (escalation
Taiwan-strait sur 6 semaines, ou crise Russie sur 8 semaines avec
montée graduelle), la baseline se "rattrape" et tue le z-score → faux
négatifs sur les vraies escalades structurelles. Mitigation suggérée
future : doubler avec un `ai_gpr_z_252d` en alert info distincte (pas
warning) pour catcher le slow-build."\_

The 2026 macro context makes this gap consequential :

- **Russia-Ukraine** war started 2022-02 ; 4-year cumulative escalation
  on infrastructure / drone strikes / NATO involvement.
- **Taiwan-strait** : 2025 PLA "Justice Mission" drills, 2026 Crisis24
  "moderate flare-ups expected", structurally heightened tension.
- **US-China decoupling** : 76 simultaneous Section 301 investigations
  (March 2026), COINS Act outbound investment restrictions (FY2026
  NDAA), Entity List enforcement — multi-year arc.
- **MENA cluster** : Iran nuclear question, Israel-Hamas, US-Yemen
  strikes, Saudi de-risking — sustained elevation since 2024.

WEF Global Risks Report 2026 §2 : _"Geopolitical cycles are long —
historically, they last between 80 and 100 years. Structural changes
like those we're witnessing now only come around once per century and
tend to be disruptive."_

A 30d window cannot detect a 6-month or 4-year structural shift —
the rolling baseline absorbs the new "normal" and the relative z-score
shrinks. We need a longer-window companion.

## Decision

Wire one new catalog alert :

```python
AlertDef("GEOPOL_REGIME_STRUCTURAL", info,
         "Regime structurel geopol z_252d={value:+.2f}",
         "ai_gpr_z_252d", 2.0, "above", ...)
```

Fires when `|z| >= 2.0` where the z-score is computed over a
**252-day (1 trading year) trailing window** of AI-GPR daily readings.

### Severity = `info` (not `warning`)

Structural regime shifts are slow context, not actionable urgency.
The trader uses GEOPOL*REGIME_STRUCTURAL to \_frame* their session
expectations ("we're in a high-geopol regime overall, vol skew bias
should reflect that") but takes immediate trade decisions only on
GEOPOL_FLASH (warning, 30d acute). The two-window stack is :

| Alert                    | Window | Severity | Cadence        | Use                   |
| ------------------------ | ------ | -------- | -------------- | --------------------- |
| GEOPOL_FLASH             | 30d    | warning  | daily 23:30    | acute repricing event |
| GEOPOL_REGIME_STRUCTURAL | 252d   | info     | weekly Sun 22h | regime context        |

### Implementation : duplication over premature abstraction

`services/geopol_regime_check.py` is structurally a 90% duplicate of
`services/geopol_flash_check.py` — same source (`gpr_observations`),
same `_zscore` helper shape, same `_fetch_recent_observations` shape.
We deliberately keep two separate files rather than abstracting because :

1. The two alerts will likely diverge in v2 : GEOPOL_FLASH might gain
   FinBERT-tone cross-confirmation, GEOPOL_REGIME might gain regime
   classification (war / sanctions / cyber / economic).
2. A single-file abstraction would require parameterizing window,
   threshold, severity, and metric_name — effectively 4 axes of
   configuration that bloat the API for marginal gain.
3. ~80 LOC of duplicated `_zscore` + `_fetch` is acceptable maintenance
   cost ; the alternative (shared utility module) creates a
   `services/geopol_common.py` import dependency that adds blast radius
   without clarity.

If a v3 ever needs >2 windows, then a shared utility module makes sense.
For now, two files = two alerts, easy to reason about.

### Cron schedule

`Sun *-*-* 22:00:00 Europe/Paris` — weekly Sunday post-NY-close.
Keeps the alert fresh for Monday pre-Londres briefings. Daily evaluation
of a 252d-window signal would be wasteful (the z-score moves <1 sigma
per day on average).

### Threshold rationale

`|z| >= 2.0` matches the catalog convention (DATA_SURPRISE_Z,
REAL_YIELD_GOLD_DIVERGENCE, GEOPOL_FLASH, TARIFF_SHOCK). 2σ on a 252d
window corresponds to a ~1-in-50 weekly event under approximate
normality — rare enough that a fired GEOPOL_REGIME_STRUCTURAL is
genuinely meaningful regime context, not noise.

### Source-stamping (ADR-017)

`extra_payload.source = "ai_gpr:caldara_iacoviello"`. Same as
GEOPOL_FLASH for consistency. Plus :

- `window_days = 252` (lets audit consumer distinguish from FLASH)
- `regimes_signaled` : informational tags surfaced to the trader
  (Russia-Ukraine, Taiwan, US-China, MENA cluster)
- `baseline_mean` / `baseline_std` / `n_history` for re-derivation

## Consequences

### Pros

- **Closes the slow-build gap** identified by ichor-trader on PR #24.
- **Two-window stack** — acute (30d, warning) + structural (252d, info)
  is a defensible doctrinal pattern. Mirrors how option traders watch
  short-term vs long-term volatility separately.
- **Zero new collector** — reuses `gpr_observations` already populated
  daily by AI-GPR collector.
- **Cheap** — ~1 SQL query/week × 252 rows = sub-second per execution.
- **Self-calibrating** — the 252d trailing baseline absorbs steady-state
  regime shifts naturally ; the alert fires only on _acceleration_
  vs the year-trailing pace.

### Cons

- **Duplicated code with geopol_flash_check.py** (~80 LOC). Mitigation :
  acceptable maintenance cost for single-purpose alert clarity. Future
  consolidation possible if 3rd window emerges.
- **252d may still miss multi-year regimes** : if the entire 2024-2026
  AI-GPR distribution is structurally heightened vs 2018-2022, the 252d
  baseline absorbs it and we never fire. Mitigation : the original
  Caldara-Iacoviello GPR (monthly, 1985-) provides decadal context as
  a separate static reference (out-of-band of this alert).
- **No event categorization** : "structural shift" is a single signal,
  not "war regime vs sanctions regime vs cyber regime". v2 could add
  category-specific 252d alerts using the original GPR's 8 categories
  (war threats, peace threats, military buildups, nuclear threats,
  terror threats, etc.).

### Neutral

- Weekly cadence means the alert state can be stale up to 7 days. By
  design — structural shifts are slow, not minute-to-minute. A trader
  consulting Friday's session card sees Sunday's reading.

## Alternatives considered

### A — Extend GEOPOL_FLASH with a 252d field in extra_payload

Rejected : conflates two semantically distinct signals. Would require
a single threshold (acute window) but the structural signal often
deviates differently. Two AlertDef rows with two metric_names is
clearer for the catalog and the audit log.

### B — Multiple windows (30d + 90d + 252d) in one alert

Tabled (not rejected) for v2 : richer but multiplies analytic surface.
v1 starts with 2 windows (30d + 252d). v2 can add a 90d "tactical"
companion if Eliot finds the gap.

### C — Use the original Caldara-Iacoviello GPR (monthly, 1985-) instead

Rejected : monthly cadence is too slow even for a "structural" alert.
The 252d-rolling daily AI-GPR catches structural shifts on a 6-12 month
arc, which is the actionable horizon for a discretionary FX/macro trader.
The original GPR is useful as out-of-band context (not wired as alert).

### D — Higher threshold (|z| >= 3.0) for "real" structural shift

Rejected : 3σ on a 252d window with daily readings is ~1-in-1000 — would
fire ~once every 4 years, missing the sub-bunch of meaningful shifts
(Q1-Q3 2026 is the _third_ 2σ regime shift since AI-GPR started, per
backtests). 2σ matches the catalog convention and gives ~quarterly
regime context.

### E — Rolling median + MAD instead of mean + std (robust to outliers)

Tabled : robust statistics defensible for a noisier index. AI-GPR's
LLM-scoring already smooths outliers somewhat ; mean/std with the 252d
window is empirically not pathological. v2 could explore.

### F — Daily cadence even on 252d window

Rejected : computational waste. A 252d z-score moves <1σ per day. Weekly
suffices for context-flag use.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/geopol_regime_check.py` (NEW, ~210 LOC)
- `apps/api/src/ichor_api/cli/run_geopol_regime_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with one
  AlertDef + bump assert 40 → 41)
- `apps/api/tests/test_geopol_regime_check.py` (NEW, 10 tests)
- `scripts/hetzner/register-cron-geopol-regime-check.sh` (NEW)
- `docs/decisions/ADR-039-geopol-regime-structural-alert.md` (this file)

## Related

- ADR-017 — Living Macro Entity boundary (no BUY/SELL).
- ADR-036 — GEOPOL_FLASH (acute 30d window, warning, daily). Sister
  pathway. Same source, different time horizon.
- ADR-037 — TARIFF_SHOCK (sister Phase D.5.b alert).
- Caldara, Dario and Matteo Iacoviello (2022). "Measuring Geopolitical
  Risk." _American Economic Review_ 112(4): 1194–1225.
- Iacoviello, Matteo and Jonathan Tong (2026). "The AI-GPR Index."
  Federal Reserve Board IFDP / SF Fed.
- WEF Global Risks Report 2026, §2 "Global risks in-depth".
- Council on Foreign Relations 2026 Conflict Risk Assessment.

## Followups

- v2 : 90d "tactical" companion (between acute and structural).
- v2 : category-specific 252d alerts (war / sanctions / cyber / nuclear)
  using GPR's 8-category taxonomy.
- v2 : Capability 5 ADR-017 — Claude tools runtime can fetch the
  current major-power conflict map at alert time and produce a
  1-paragraph regime narrative summary.
- Phase E : conformal prediction wrapper Brier V2 with regime context
  feature = which `regimes_signaled` are active.
