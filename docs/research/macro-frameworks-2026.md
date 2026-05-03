# Macro Frameworks for Directional Session Views — Research Brief

> Source : research subagent task `abd09fb8eeb4c1000`, completed 2026-05-03.
> Persisted by main thread for context preservation.

## 1. Cross-asset macro framework

### The "macro trinity" (DXY + 10Y yields + VIX)

The standard regime-detection logic combines these three as orthogonal axes :
- **VIX** captures fear / risk appetite
- **10Y yields** capture growth / policy expectations
- **DXY** captures relative US strength + global funding stress

Practitioners commonly z-score each axis on a rolling window and require alignment before assigning conviction. **Common quadrant map** :

| Quadrant | Regime |
|---|---|
| DXY↓ + VIX↑ | Haven bid |
| DXY↑ + VIX↑ | **Funding stress** (dollar wrecking ball) |
| DXY↓ + VIX↓ | Goldilocks / risk-on |
| DXY↑ + VIX↓ | USD-dominant complacency |

Single-axis moves are typically discarded as noise.

### Real yields (10Y TIPS)

Calculated as nominal 10Y − breakeven, or read directly from FRED's `DFII10` series.

- Drives **gold** via opportunity cost (PIMCO empirical "real duration" ≈ 18 → ~18 % gold price decline per 100 bps real-yield rise, historically)
- Drives **long-duration tech (NDX)** via discount-rate channel
- Drives **USD** because rising US real yields attract capital

### Term structure (2s10s, 5s30s, 3M10Y)

- **2s10s inversion** preceded 6 of last 7 recessions with median 14-month lag
- **NY Fed prefers 3M10Y** for its recession probability model
- **5s30s** is more about long-end inflation / term-premium ; steepens on reflation, flattens on stagnation / QE expectations
- The 2022–24 episode was the longest inversion on record without (yet) a confirmed recession — reminder : the signal is probabilistic

### Credit spreads (HY OAS, IG OAS)

- **HY OAS** (FRED : `BAMLH0A0HYM2`) = most sensitive market-based gauge of risk appetite ; widening typically leads equity tops by 2–8 weeks
- **IG OAS** (FRED : `BAMLC0A0CM`) = steadier, used for financial conditions composites
- Combined with curve inversion, has flagged every US recession since 1990

### Dollar smile theory (Stephen Jen, 2001)

DXY smiles in two regimes :
1. **Global crisis / funding stress** → forced USD demand on dollar-denominated debt
2. **US growth outperformance** → capital inflows + Fed leadership in tightening

Bottom of the smile = "muddle through" with steady Fed = USD weakness.

**Critical for interpreting why DXY can rally on both risk-off AND risk-on days.** Without this lens, DXY moves look contradictory.

### Liquidity proxies

The widely used formula :
```
Net Liquidity = Fed Balance Sheet − TGA − RRP
```

- **TGA up** = reserves drained = tightening
- **RRP down** = cash redeployed to risk = supportive
- Once RRP buffer approaches zero, QT must come out of reserves directly — historically a stress trigger (Sept 2019 repo blowup is the canonical case)

Live dashboard : netliquidity.org

---

## 2. FX-specific frameworks

### Interest rate differential (IRD)

Both nominal and real differentials matter :
- **EUR/USD** historically tracks the US-Germany 10Y spread
- **USD/JPY** tracks the US-Japan 10Y spread very closely
- **The widening of the differential (rate of change) tends to drive trends more than the absolute level**

### Carry baskets

Standard G10 carry basket : long top-3 yielders (recently NZD, AUD, NOK), short bottom-3 (JPY, CHF, EUR). JPY is the dominant funder due to BoJ's decade-long ultra-low rate stance.

**Carry works in low-vol regimes ; unwinds violently when vol spikes** (BoJ's July 2024 hike triggered a textbook unwind).

### Central bank divergence

Build a hawkish/dovish score across G10 from :
- Policy-rate path expectations (OIS curves)
- Recent statement tone
- Inflation / jobs data trajectory

The pair = (hawkish CB) / (dovish CB) is the higher-conviction directional bet, but **pre-pricing means you need to trade the change in expectations, not the level**.

### Risk-on/off behavior of majors

| Type | Currencies | Notes |
|---|---|---|
| Safe havens | USD (smile-dependent), CHF, JPY | JPY mostly via carry-unwind, not pure flight |
| Pro-cyclical | AUD, NZD, CAD, NOK | Commodity link + carry |
| Mixed | EUR, GBP, SEK | |

Academic work : liquid currencies (JPY, EUR) have negative liquidity betas ; illiquid ones (NOK, NZD) the most positive.

### Per-pair primary drivers

| Pair | Primary drivers |
|---|---|
| **EUR/USD** | Fed vs ECB policy differential ; Eurozone energy/geopolitics ; EU growth surprises |
| **GBP/USD** | BoE policy ; UK politics/fiscal ; risk sentiment (more pro-cyclical than EUR) |
| **USD/JPY** | US-Japan rate differential (esp. 10Y) ; BoJ policy shifts ; MoF intervention thresholds ; risk-off carry-unwind |
| **AUD/USD** | China growth + iron ore/copper ; RBA ; global risk sentiment |
| **USD/CAD** | WTI crude ; BoC vs Fed differential ; US ISM/employment |

---

## 3. Gold framework

### Real yields (10Y TIPS) — historic primary driver

- Inverse correlation
- PIMCO real duration : ~−18 % per +100 bps
- Chicago Fed VAR : ~−3.4 % per +100 bps
- Erb-Harvey : −0.82 long-run correlation

### DXY — secondary

Inverse, but not always ; can co-move during haven episodes when both are bid.

### Geopolitical risk premium

Post-Feb 2022 (Russian FX-reserve freeze) became **structural rather than transient** ; sanctions risk has been priced into central bank reserve mix.

### ETF flows + central bank buying

- EM central banks (PBoC, RBI, Turkey, Poland, Kazakhstan) buying > 1 000 t/year since 2022, ~2× decade average
- ETFs = cyclical accelerator (record H1 2025 inflows ~$38 bn / ~397 t)
- EM central banks = structural floor

### Inflation expectations (5Y5Y, breakevens)

Gold reacts more to *expected* inflation than realized. WGC : +50 bps in 10Y breakeven ≈ +4 % gold historically.

FRED series : `T5YIFR`, `T5YIE`

### Crisis hedge premium

Activates during equity drawdowns + credit stress + geopolitical shocks ; **can override real-yield signal entirely** (the 2023–25 decoupling is exhibit A).

---

## 4. US equity indices framework

### SPX drivers (broad)

```
SPX = Earnings (level + revisions)
    × Discount rate (10Y nominal + ERP)
    × Sentiment / positioning
    × Breadth (advance-decline, % above 200dma)
    × Flows (systematic, retail, buybacks)
```

Standard Gordon-growth decomposition works as a sanity check, not a forecast.

### NAS100 / NDX (tech-heavy)

- Higher real-yield duration (long cash flows)
- Mag-7 concentration risk
- AI capex cycle as a structural driver
- **Real-yield moves get amplified vs SPX**

### Gamma exposure (GEX) / dealer positioning

- **Positive gamma** = dealers sell rallies, buy dips (mean-reverting / pinned)
- **Negative gamma** = dealers buy rallies, sell dips (momentum / amplified)
- **Zero-gamma flip level** = regime boundary
- **Call walls** = resistance, **put walls** = support
- **0DTE now drives > 50 % of SPX daily option volume**

### VIX term structure + skew

- **Contango ~84 % of the time** (default)
- **Backwardation** = stress AND historically a contrarian-bullish signal for SPX
- **M1:M2 spread** = the workhorse metric
- **Steep put skew** = downside hedging demand (often pre-event)

### BofA Global Fund Manager Survey (FMS)

- Composite sentiment
- **Bull & Bear Indicator** (> 8 = contrarian sell)
- **FMS Cash Rule** : cash < 4 % = top warning, > 5 % = buy signal historically
- Most-crowded-trade question

### Sector rotation

Defensive (XLP, XLU, XLV) vs cyclical (XLI, XLF, XLY) ratios as growth-expectation proxy ; XLK / SPY for tech leadership.

### Earnings cadence

Q earnings season weeks 2–6 post quarter-end ; **revision breadth + guidance > headline EPS beats**.

---

## 5. Catalyst calendar

### Top releases by market impact (CME ranked by volume)

1. **FOMC announcements** — largest aggregate volume
2. **NFP** — largest per-surprise spike (~9× baseline volume in first minute)
3. **CPI / Core CPI**
4. **Retail Sales**
5. **Core PCE** (Fed's preferred)
6. **PPI**
7. **ISM/PMIs, GDP advance, Durable Orders**

### Central bank meetings

FOMC (8/yr), ECB (8/yr), BoE (8/yr), BoJ (8/yr), BoC (8/yr), RBA (~11/yr), SNB, RBNZ.

Speeches : Powell/Lagarde + voting members ; "Fedspeak" blackout window starts ~10 days pre-FOMC.

### Treasury auctions

Watch :
- **Tail** (stop-out yield − WI yield)
- **Bid-to-cover**
- **Indirect bidder %**
- **Primary-dealer take-up**

**Tail > +2 bp** (especially 10Y / 30Y) = repricing term premium → equity headwind, USD pressure if foreign demand weak.

Calendar published quarterly via QRA.

### Earnings calendar

Mag-7 reports drive NDX / SPX more than aggregate season ; bank earnings (early in season) signal credit/loan trends.

### Geopolitical

Elections, OPEC+ meetings, G7/G20, NATO, debt-ceiling deadlines, sanctions windows.

---

## 6. Session behavior heuristics

### Asia (Tokyo, ~00:00–09:00 GMT)

- ~20 % of global FX volume
- Lowest vol, range-bound
- JPY pairs most active ; AUD/NZD via own session overlap
- BoJ, China data, RBA can produce sharp moves
- Gold momentum often **builds** here (PBoC fix + Shanghai physical)

### London open (~07:00–08:00 GMT / 09:00 Paris)

- **Volatility step-up ; sets day's tone**
- EUR/USD, GBP/USD, EUR/GBP momentum
- **Gold breakouts often confirm here**
- London 4 pm fix is a pension/asset-manager benchmark for FX rebalancing

### NY open (~13:30 GMT / 08:30 ET / 14:30 Paris)

- Major US data releases at 08:30 ET (NFP, CPI, retail sales)
- **London-NY overlap (~12:00–16:00 GMT) ≈ 50–70 % of daily FX volume**
- Cash equity open at 09:30 ET = GEX activates, sector rotation visible

### Lunch lull (~12:00–13:00 ET / 18:00–19:00 Paris)

- Liquidity drops, ranges tighten ; setups often fail

### Late-session repositioning (~15:00–16:00 ET / 21:00–22:00 Paris)

- Hedging into close
- GEX-driven pinning around big strikes (esp. OPEX / VIX expiry weeks)

### End-of-day / month-end flows

- Pension rebalancing concentrated last 2–3 trading days
- Goldman-tracked April 2026 rebalance was the largest non-quarter monthly sell program on record (~$25 bn equities to sell)
- When stocks outperform bonds → sell-equities/buy-bonds ; reverse when bonds outperform
- London 4 pm fix is the primary FX execution window

---

## 7. Probability calibration

### Frame views as probabilities, not binaries

Tetlock's superforecasters distinguish 55/45 from 60/40 ; rounding their forecasts to nearest 5 % degrades accuracy. **Granularity itself predicts skill.**

### Stylized "70 % bias + invalidation"

> "Bias EUR/USD higher next session, ~65 % probability. Thesis: ECB hawkish surprise + soft US JOLTS. Invalidation: a 4-handle US CPI print, OR DXY breaking 105.20 with risk-off, OR 10Y yields > 4.50 % — any of those collapses conviction toward 50/50."

Notice **three separate invalidation conditions**, each independently sufficient — that's the discipline.

### Why "100 % confident" views are red flags

Aleatory uncertainty (irreducible) plus epistemic uncertainty (knowable but unknown) mean macro is rarely outside 5–95 %. Tetlock : stay in the maybe-zone (35–65 %) for genuinely uncertain questions, move out tentatively. **Anyone claiming certainty is signaling either a model error or a marketing pitch.**

### Track-record patterns for self-correction

- **Brier score** (calibration + resolution combined)
- Superforecasters update **often, in small increments** — the Bayesian rhythm
- They keep journals ; they Fermi-decompose questions ; they consult comparison classes (outside view) before applying inside-view nuance
- **The single strongest predictor of forecasting skill is *commitment to belief updating* — 3× stronger than IQ**

### Domain caveat

Recent work shows financial / economic forecasts are **harder** than political ones ; calibration techniques transfer but base accuracy is lower. Build that humility into the system.

---

## Confidence map

**Verified via primary/authoritative sources:**

- Stephen Jen as originator of dollar smile (Eurizon SLJ, 2001)
- TGA/RRP/balance-sheet mechanics — Federal Reserve own publications
- HY OAS series codes (BAMLH0A0HYM2 etc.) and behavior — FRED + ICE BofA
- FRED breakeven series (T5YIE, T5YIFR, DFII10) — FRED
- VIX contango ~84 % of historical sample — Macroption / Cboe
- 2s10s preceded 6 of 7 recessions — multiple sources including FRED + NBER
- Tetlock's superforecaster findings — Wharton paper + multiple summaries
- CME release-impact ranking with NFP / FOMC / CPI hierarchy — CME Group Economic Research
- BoFA FMS indicators — multiple secondary reports
- Pension month-end rebalancing mechanics + April 2026 ~$25 bn sell program — Goldman estimate

**General professional knowledge (widely held, not single-source verified):**

- Per-pair drivers (EUR/USD = Fed/ECB diff, USD/CAD = oil, etc.) — consensus framework
- Session volume splits (London ~30 %, NY ~17 %, London-NY overlap ~50–70 %)
- GEX positive vs negative regime behavior — well-documented in options literature

**Deliberately omitted (could not verify with confidence):**

- Specific named-analyst attributions (Bridgewater, Variant Perception, Real Vision, 42 Macro, GMI, Hedgeye, Brent Donnelly) — omitted citations rather than invent
- Precise current numerical levels (rates, prices, FMS readings beyond cited articles)

---

## Sources

### Cross-asset
- [ACY: Gold strategy using VIX, yields, DXY](https://acy.com/en/market-news/education/gold-strategy-using-vix-yields-dxy-2025-l-s-162409/)
- [Eurizon SLJ — Dollar Smile](https://www.eurizonsljcapital.com/dollar-smile/)
- [Schroders — Dollar Smile validity](https://www.schroders.com/en-us/us/institutional/insights/the-dollar-smile-theory-what-is-it-and-is-it-still-valid-in-the-new-market-regime/)
- [PIMCO — Understanding Gold Prices](https://www.pimco.com/us/en/resources/education/understanding-gold-prices)
- [Chicago Fed — What Drives Gold Prices](https://www.chicagofed.org/-/media/publications/chicago-fed-letter/2021/cfl464-pdf.pdf)
- [NY Fed — Yield Curve as Leading Indicator FAQ](https://www.newyorkfed.org/research/capital_markets/ycfaq)
- [FRED — HY OAS BAMLH0A0HYM2](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)
- [Federal Reserve — TGA fluctuations effects](https://www.federalreserve.gov/econres/notes/feds-notes/fluctuations-in-the-treasury-general-account-and-their-effect-on-the-feds-balance-sheet-20250806.html)
- [NetLiquidity dashboard](https://www.netliquidity.org/dashboard)

### FX
- [EBC — Yen Carry Trade Unwind](https://www.ebc.com/forex/yen-carry-trade-unwind-could-it-trigger-the-next-market-crash)
- [ING THINK — G10 FX Outlook 2026](https://think.ing.com/articles/g10-fx-outlook-2026/)
- [Fusion Markets — Interest Rate Divergence 2025](https://fusionmarkets.com/posts/interest-rate-divergence-2025)
- [LogikFX — Interest Rate Differential](https://www.logikfx.com/post/what-is-interest-rate-differential-a-comprehensive-guide-for-traders)
- [Forex.com — USD price action setups](https://www.forex.com/en-uk/news-and-analysis/us-dollar-price-action-setups-eur-usd-usd-jpy-gbp-usd-usd-cad-2026-03-20/)

### Gold
- [VanEck — Gold structural strength](https://www.vaneck.com/us/en/blogs/gold-investing/gold-in-2025-a-new-era-of-structural-strength-and-enduring-appeal/)
- [World Gold Council — Gold Demand Trends](https://www.gold.org/goldhub/research/gold-demand-trends)
- [EBC — Geopolitics and Gold](https://www.ebc.com/forex/how-geopolitics-and-central-banks-are-driving-gold-higher)
- [FRED — T5YIFR (5Y5Y forward)](https://fred.stlouisfed.org/series/T5YIFR)

### Indices
- [SpotGamma — GEX explained](https://spotgamma.com/gamma-exposure-gex/)
- [Cboe — VIX Backwardation](https://www.cboe.com/insights/posts/inside-volatility-trading-is-vix-backwardation-necessarily-a-sign-of-a-future-down-market/)
- [Macroption — VIX Futures Curve](https://www.macroption.com/vix-futures-curve/)
- [Investing.com — March 2026 BofA FMS](https://www.investing.com/news/stock-market-news/bofa-fund-manager-survey-shows-no-signs-of-equity-capitulation-yet-4565163)

### Catalysts
- [CME Group — Economic Indicators That Most Impact Markets](https://www.cmegroup.com/insights/economic-research/2025/economic-indicators-that-most-impact-markets.html)
- [Loomis Sayles — Anatomy of Treasury Auction](https://www.loomissayles.com/insights/the-anatomy-of-a-treasury-auction/)

### Sessions
- [Babypips — Forex Trading Sessions](https://www.babypips.com/learn/forex/forex-trading-sessions)
- [OANDA — Best Times to Trade Forex](https://www.oanda.com/us-en/trade-tap-blog/trading-knowledge/when-is-the-best-time-for-forex-trading/)
- [BigGo Finance — Goldman month-end rebalancing](https://finance.biggo.com/news/qGYFvJ0BrdTHlKtCcBzy)

### Calibration
- [Farnam Street — Ten Commandments for Superforecasters](https://fs.blog/ten-commandments-for-superforecasters/)
- [Wharton — Superforecasting paper](https://faculty.wharton.upenn.edu/wp-content/uploads/2015/07/2015---superforecasters.pdf)

---

**Report compiled** : 2026-05-03 by main thread from research subagent output.
