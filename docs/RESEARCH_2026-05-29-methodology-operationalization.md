# Research dossier — Operationalizing the owner's macro methodology (2026-05-29)

> Durable capture of a 5-parallel-agent web-research burst (§6 of the owner's
> directive: "MAXIMUM ABSOLU de recherches web, vraies données only"). Purpose:
> turn the owner's trading transcript (3-step macro methodology) into a concrete,
> Voie-D-compatible (free data, Claude-local) build plan for Ichor's 5 priority
> assets (EUR/USD, GBP/USD, XAU/USD, S&P500, Nasdaq), calibrated for the NY
> 13h-16h Paris window. This is RESEARCH/PLAN — no BUY/SELL (ADR-017 holds).
>
> Source-of-truth for the Phase-1 ADRs (STIR, surprise-scoring, theme/cycle).

## 0. Citation correction (Pattern #20 — memory cite drift caught by R59)

- **Bauer & Swanson 2023** is in **NBER Macroeconomics Annual vol. 37, pp. 87-155, DOI `10.1086/723574`** — NOT the AER. ROADMAP.md / ADR-099 §Impl(r170) / memory `ichor_r170_detail.md` cite "AER DOI 10.1257/aer.20201220" which is **WRONG**. Fix these when the STIR ADR is authored.
- **Nakamura & Steinsson 2018**: QJE 133(3):1283-1330, DOI `10.1093/qje/qjy004` (verified, correct).
- **Born, Dovern, Enders 2023**: European Economic Review 154, p.104440, DOI `10.1016/j.euroecorev.2023.104440` (verified).

## 1. The owner's 3-step methodology (from transcript)

1. **Identify the underlying theme** via 8 drivers (engrenages): macroeconomic /
   monetary_policy / economic_data / fiscal_policy / market_interconnexions /
   geopolitics / price_action_flow / supply_demand. Plus: the 4 economic cycles,
   data taxonomy (growth vs inflation vs hybrid), temporality (leading/coincident/
   lagging), the discounting/forward-looking mechanism, the "river current" metaphor.
2. **Look for the surprise**: not the consensus point, but the RANGE/dispersion of
   economist expectations; + real-time newsfeed for the unscheduled (geopolitics,
   CB comments).
3. **Does the surprise change the theme?**: misprice (repricing in trend direction)
   vs true regime change (reversal) — judged via STIR markets (rate-path probabilities).

Ichor maps ~1:1 onto this: N1 theme classifier = step 1 (6/8 drivers wired),
economic_events range = step 2 (partial), STIR = step 3 (NOT built — the gap).

## 2. Step 3 — STIR / rate-path probabilities (the transformational gap)

**Method (CME FedWatch, verified)**: underlying = 30-Day Fed Funds futures (ZQ),
`implied_EFFR = 100 - price`; ZQ settles on the calendar-month AVERAGE EFFR;
meeting-timing weighting ("anchor months") resolves the post-decision implied rate;
`P(move) = (implied - lower_step) / 0.25%` linear interpolation; chain meeting-by-
meeting (cumulative = product of conditionals).

**Voie-D sourcing (free)**:

- Fed realized: FRED `DFF`/`EFFR`. ECB: FRED `ECBESTRVOLWGTTRMDMNRT` (€STR) + ECB Data Portal. BoE: FRED `IUDSOIA` (SONIA) + BoE IADB.
- Forward path: Eurex free settlement prices — `FST3` (3M €STR futures), `FEU3` (EURIBOR). ECB-dated OIS cleanest but no confirmed free stream → Eurex forwards substitute.
- Fed implied probabilities: the CME FedWatch **API is commercial (NOT confirmed free** — page 403'd, treat as paid). Free options: recompute from a ZQ quote (Yahoo `ZQ=F` / Barchart 1 CSV/day) OR scrape a pre-computed dashboard (`rateprobability.com`, `ecb-watch.eu`, Atlanta Fed Market Probability Tracker — fragile, no SLA).
- BCE/BoE: recompute in-house from €STR/SONIA (FRED) + Eurex forwards, **correcting the €STR↔depo spread** (⚠️ a 5bp error shifts the proba 10-20pts).
- **Bauer-Swanson orthogonalized FOMC surprises**: SF Fed publishes a FREE XLSX (`frbsf.org/.../monetary-policy-surprises-data.xlsx`, raw + orthogonalized, 30-min window).

**"Surprise changes the theme" signal** = combine (a) day-over-day change in implied
proba per meeting (curve move) + (b) Bauer-Swanson orthogonalized surprise post-FOMC
(distinguishes a real policy shock from already-priced noise). NS2018 + BS2023 validate this.

## 3. Step 2 — Surprise scoring (N2)

**Key finding**: a free min/median/max forecast RANGE does NOT exist intraday
(Bloomberg ECO / Econoday are paywalled). Two agents converged on the right design:

- **Compute σ_surprise IN-HOUSE**: Ichor already stores `actual`+`consensus`
  (`economic_events`, migration 0052) → `σ_surprise = std(actual - consensus)` over a
  rolling window (12-24 events) → standardized surprise `z = (actual - consensus) / σ_surprise`.
  This IS the Citi Economic Surprise Index (CESI) method; fresher/more reliable than any scrape.
- **Damp by dispersion (Born-Dovern-Enders 2023)**: high forecast dispersion → ATTENUATED
  market reaction (counterintuitive — the market trusts the print less). `reaction_expected =
z × damping(dispersion)`, damping decreasing in dispersion.
- **Free inputs**: FXStreet "deviation ratio" (pre-standardized surprise, free widget/API);
  consensus from ForexFactory (already) + FMP free (250/day, with a date-guard vs ForexFactory
  per freshness lessons r37/r41). SPF Philadelphia Fed D1 (IQR, free, quarterly) = slow
  dispersion-regime modulator (NOT a per-release range). Bloomberg/Econoday ranges = out (paid).

## 4. Step 1 — Theme + economic cycle (N1)

**Cycle framework = Merrill Lynch Investment Clock** (Greetham 2004): 2 axes growth ×
inflation → 4 quadrants = the owner's 4 cycles exactly: Recovery/Goldilocks (expansion),
Overheat (reflation), Stagflation, Reflation/Recession (déflation). **Classify by the SIGN
of the derivative** (Δ3m acceleration), not the absolute level. Same matrix at 42 Macro,
Hedgeye GIP. Caveat: the clock skips/reverses phases — never force the sequence.

- **Programmatic cycle**: Atlanta Fed **GDPNow** (FRED `GDPNOW`, free, key required, citation
  mandatory) + StL `STLENI` for growth; **Cleveland Fed inflation nowcast (Ichor ALREADY has
  this** — ADR-070, migration 0035) for inflation; `UNRATE` tiebreaker. Quadrant = sign of
  (Δgrowth_nowcast, Δinflation_nowcast).
- **Taxonomy (Conference Board)**: LEI 10 leading / CEI 4 coincident (= NBER recession-dating
  series) / LAG 7 lagging. Growth = payrolls/PMI/IP/retail; inflation = CPI/Core/PCE/import
  prices; hybrid = ISM/claims/consumer-confidence.
- **Dominant driver**: policy-dominant vs market-dominant. Tell = stock↔bond rolling
  correlation (positive, both fall = monetary/inflation driver; negative, bonds hedge =
  growth-fear), VIX>25 persistent = risk-off (geopolitics/price-action), MOVE = rate vol.
  argmax with hysteresis (already Ichor doctrine).

**The 2 missing theme drivers (free sources)**:

- `price_action_flow` (positioning + vol + levels): **CFTC COT** via Socrata API
  (`publicreporting.cftc.gov`, TFF dataset for FX: Dealers / Asset Managers / Leveraged Funds;
  non-reportable ≈ retail proxy; Python `cot_reports` lib) + VIX/MOVE (FRED) + Polygon levels
  (already). ⚠️ COT pub gap Oct-Nov 2025 (gov shutdown) — handle holes.
- `supply_demand` (commodities, mainly XAU): **EIA Weekly Petroleum Status** (crude stocks,
  Wed 10:30 ET, build > expected = bearish) + **COMEX warehouse stocks** (gold registered vs
  eligible, coverage ratio) + curve **backwardation/contango** (front−deferred calendar spread;
  backwardation = scarcity/bullish).

## 5. Voie-D data source map (free / freemium)

| Need                      | Recommended (stable)                                              | Tier          | Notes                                         |
| ------------------------- | ----------------------------------------------------------------- | ------------- | --------------------------------------------- |
| Institutional positioning | **CFTC COT** Socrata API                                          | free official | best ratio; handle pub gaps                   |
| Real-time news 360°       | **Investing.com RSS** + **Marketaux** (100/day) + GDELT (already) | free          | RSS hourly; Marketaux entity-filtered         |
| Options sentiment         | **CBOE Put/Call CSV**                                             | free stable   | adds to existing SKEW/VVIX/VIX                |
| Calendar consensus        | ForexFactory (already) + **FMP** (250/day)                        | free          | FMP date-guard vs FF (date errors documented) |
| Rate realized             | **FRED** `DFF`/`EFFR`/`ECBESTRVOLWGTTRMDMNRT`/`IUDSOIA`           | free          |                                               |
| Rate forwards             | **Eurex** FST3/FEU3 settlement                                    | free          |                                               |
| FOMC surprises            | **SF Fed** monetary-policy-surprises XLSX                         | free          | Bauer orthogonalized                          |
| Growth nowcast            | **FRED** `GDPNOW`/`STLENI`                                        | free          | citation mandatory for GDPNow                 |

**Out (paid / unusable)**: Bloomberg ECO, Econoday ranges, Trading Economics prod tier,
Finnhub economic calendar (premium), LiveSquawk/Newsquawk, Alpha Vantage news (25/day quota).
**No free clean text squawk exists** (Financial Juice = fragile X-scrape only — do not depend).
All free tiers (Marketaux 100/day, FMP 250/day, etc.) to re-test with a key before build.

## 6. Today's market validation (Fri 2026-05-29, Paris) — proves the pipeline produces real, sourced analysis

- **Dominant theme** = **Iran war → energy inflation → hawkish central banks** (the "moteur").
- **In-window NY catalyst**: **Chicago PMI 15h45 Paris** (prior 49.2, contraction) + German CPI ~14h.
- Fed hawkish (3.5-3.75%, 4 dissents = record since 1992, ~50% hike proba by Dec, Warsh incoming,
  next FOMC 16-17 June). ECB 2.00% (2 hikes expected 2026). BoE 3.75%, UK inflation FALLING 2.8%.
- DXY ~99.28. Close 28/05: EUR/USD >1.1600, GBP/USD >1.3400, XAU ~$4,395 under pressure,
  indices soft post-Fed, 10Y 4.41%. Iran 60-day ceasefire MoU pending Trump approval but strikes
  exchanged → **headline-gap risk during the NY window.**
- (All sourced; intraday 29/05 not live at research time — see SESSION research transcripts.)

## 7. Gap → build sequence (Phase 1 — cœur méthodo)

Model policy decision (this session): Passes 1-4 + Pass-6 = Opus xhigh (reasoning);
Couche-2 + Pass-5 stay Haiku low (ADR-023, CF-timeout + Max-20x quota). Voie D holds.

1. **Foundation first** (§11 — do before features): green PR #159 CI
   (lockfile sync branch↔main + the DXY test fix already committed `a63d695`) →
   merge r141-r188 to main → apply migration 0053 to prod (backup + dry-run; prod is at 0052).
2. **N1 completion**: wire the 2 missing theme drivers — `price_action_flow` (CFTC COT collector
   - VIX/MOVE) and `supply_demand` (EIA petroleum + COMEX gold + curve). New ADR. → theme 8/8.
3. **Cycle classifier**: Merrill quadrant service from GDPNow × Cleveland nowcast (exists) derivatives.
4. **Surprise scoring (N2)**: in-house σ_surprise + Born-Dovern-Enders damping on `economic_events`;
   optional FXStreet deviation ratio. New ADR.
5. **STIR / rate-path (N4 — transformational)**: collector (FRED rates + Eurex forwards + SF Fed
   surprises XLSX; Fed proba via scrape-or-recompute) + the "surprise-changes-theme" signal. New ADR
   (cite NS2018 + BS2023-NBER-corrected).
6. **Real-time layer (Phase 2 / ADR-106 Strides 2-7)**: Investing.com RSS + Marketaux + CFTC COT +
   CBOE Put/Call into the live-reactivity loop.
7. **Coach layer (Phase 3)**: pedagogical framing (river metaphor, beginner-level) woven into the
   frontend phrasing per §9.5 (no separate "methodology" section).

Each step: ADR-before-code (rule 3), tests, deploy via R-DEPLOY-6, empirical post-deploy witness.
