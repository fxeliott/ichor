# ADR-034: REAL_YIELD_GOLD_DIVERGENCE alert wiring

- **Status**: Accepted (ratification post-implementation)
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP D.5.c

## Context

The carry-channel relationship between gold and 10Y real yields is
the textbook macro pair :

> **Gold pays no yield.** When competing real-yielding assets pay
> more (TIPS yields rise), the opportunity cost of holding gold
> rises and the price falls. Hence the inverse correlation.

In normal regime the rolling-60d correlation between
`FRED:GOLDAMGBD228NLBM` (Gold London PM fix) and `FRED:DFII10`
(10Y TIPS real yield, constant maturity) sits around **-0.5 to
-0.7**. When it diverges from that baseline — going to ~ 0 or
flipping sign — the gold market has stopped responding to real
yields and is being driven by **another factor** :

- Sovereign accumulation (China PBoC, EM CBs since 2022).
- Geopolitical premium (Russia/Ukraine, Israel/Iran, US elections).
- Currency-debasement narrative (fiscal-dominance pricing).
- Coordinated intervention (rare but observed during BoJ FX
  episodes).

These divergences are precisely the **trader-actionable moments** :
the carry model is broken, the macro framework needs a refresh.

## Decision

Wire the catalog alert `REAL_YIELD_GOLD_DIVERGENCE` to a new service
`real_yield_gold_check.py` :

```
1. Pull 5y of XAU + DFII10 daily observations from FRED (already
   collected by collectors/fred_extended.py).
2. Inner-join on date → aligned XAU log-returns + DFII10 first-diffs.
3. Rolling 60d Pearson correlation (matches the baseline window most
   academic papers use).
4. Z-score : (current rolling-corr - mean_250d) / std_250d, where
   mean/std are computed over the trailing 250d of rolling-corr
   values (~1y of context, excluding today).
5. Fire `REAL_YIELD_GOLD_DIVERGENCE` if |z| >= 2.0.
6. Source-stamp `extra_payload.source = "FRED:DFII10+GOLDAMGBD228NLBM"`.
```

Cron : daily Mon-Fri 22h Paris (after NY close 22h ; FRED daily
publishes by then).

### Why log-returns for XAU but first-diffs for DFII10

XAU is a **level price** (USD/oz), so daily returns are
multiplicative. DFII10 is **already in % units** (yield), so the
"return" of a yield is its first difference (Δbps). Mixing these
correctly matters : if you used pct-changes on the yield series,
you'd compute correlation between log-returns and pct-yield-changes
which has no economic meaning.

### Why the rolling-corr-of-rolling-corr framing

Computing the z-score of the *raw correlation today* against the
historical *distribution of rolling correlations* :

- captures the **regime moment** when the carry channel breaks,
  rather than just "today is at the tail of returns".
- self-calibrates to the asset pair's natural baseline (we don't
  hard-code -0.5 to -0.7 — the market may settle at a different
  baseline post-COVID for instance).
- is robust to long-term trend shifts.

### Boundary (ADR-017)

The alert says "the gold–real-yield correlation has broken from its
trailing distribution". It does **not** recommend a direction — gold
could be ramping on geopol bid (positive direction) OR collapsing on
forced selling (negative direction). The trader interprets the
breakdown ; Ichor only flags it.

## Consequences

### Pros

- **Reuses existing FRED collector** — DFII10 + GOLDAMGBD228NLBM
  are already in `cross_asset_heatmap.py` and `causal_propagation.py`.
- **Pure SQL+Python** : no new collectors, no new dependencies.
- **Source-stamped** (ADR-017 invariant) : every alert payload
  carries `FRED:DFII10+GOLDAMGBD228NLBM` so Eliot can replicate
  the calculation in his TradingView session.
- **Self-calibrating baseline** : doesn't hard-code -0.7 — adapts
  to the prevailing correlation regime.

### Cons

- **Rolling 60d corr is laggy** : a 1-day shock won't flip the
  rolling-corr immediately. Trade-off is intentional — we want
  *regime* divergence, not noise.
- **No Brier feedback yet** : we never measure whether a fired
  divergence was followed by an outsized gold move. ROADMAP D.1
  (Brier V2) could later track the alert as a per-factor driver.
- **Single asset pair** : this same logic applies to silver/yields,
  yen/yields, etc. Multi-pair extension is a future ADR.

### Neutral

- The cron fires once per day. It's deterministic — running it 5
  times in the same day produces the same z-score (by construction
  the underlying data only refreshes daily).

## Alternatives considered

### A — Cointegration test (ADF on residual)

Considered : Engle-Granger style cointegration test on the residual
return of XAU regressed on DFII10. Rejected for now — the test is
slow to converge on regime shifts (needs ~ 250 obs to reject
cointegration), and the rolling-corr framing is more responsive.

### B — Kalman filter dynamic regression

Tabled — overkill for v1. The rolling-corr captures 80 % of the
signal at 5 % of the implementation cost.

### C — Direct gold/real-yields beta tracking

Considered : track β = cov(gold, real_yield) / var(real_yield) and
alert when β diverges from baseline. Equivalent to the rolling-corr
approach up to a scaling factor — picked correlation for
interpretability.

## Implementation

Already shipped in the same commit as this ADR :

- `apps/api/src/ichor_api/services/real_yield_gold_check.py` (NEW)
- `apps/api/src/ichor_api/cli/run_real_yield_gold_check.py` (NEW)
- `apps/api/src/ichor_api/alerts/catalog.py` (extend with
  `REAL_YIELD_GOLD_DIVERGENCE` AlertDef + bump assert 34 → 35)
- `apps/api/tests/test_real_yield_gold_check.py` (NEW, 10 tests)
- `scripts/hetzner/register-cron-real-yield-gold-check.sh` (NEW)
- `docs/decisions/ADR-034-real-yield-gold-divergence-alert.md` (this file)

## Related

- ADR-017 — boundary contractual.
- ADR-033 — DATA_SURPRISE_Z (sister alert in the macro family).
- ADR-022 — Brier optimizer V2 (could later track this alert as
  a per-factor Pass-1 driver).
- ROADMAP D.5/D.7 — 6 alertes restantes after this one
  (TARIFF_SHOCK, BOE_TONE_SHIFT, MEGACAP_EARNINGS_T-1,
  QUAD_WITCHING, XCCY_BASIS_STRESS, SOVEREIGN_CDS_WIDEN).

## Followups

- Multi-pair extension (silver/yields, yen/yields) when warranted.
- Brier feedback on alert-firing → realised gold move.
- Add the breakdown narrative to the SessionCard "Mechanisms" block
  when the alert is active for an asset that's gold-impacted (XAU,
  XAG).
