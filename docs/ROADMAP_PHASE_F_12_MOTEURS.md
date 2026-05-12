# Phase F — 12 trading engines + Bias Aggregator (blueprint W111-W115)

> Synthèse des 3 subagent researcher round 10 (2026-05-12) consolidée en
> blueprint d'implémentation backend pour les 8 moteurs manquants
> (4 actuellement effectifs — top-down macro, bottom-up micro,
> momentum partial, mean-reversion partial).

## Principe doctrinal

Ichor n'est PAS Citadel / Renaissance / Two Sigma — pas la même data
quality, pas la même infrastructure, pas la même horizon de holding.
Mais Ichor PEUT être un système d'analyse pre-trade calibré
contre les outcomes réalisés, avec les meilleurs frameworks
institutionnels académiquement validés.

**Différentiation Ichor vs hedge funds institutionnels** :

| Edge           | Hedge funds top-tier             | Ichor                                                                          |
| -------------- | -------------------------------- | ------------------------------------------------------------------------------ |
| Execution      | Microstructure depth (Medallion) | N/A (Eliot trade discretionary)                                                |
| Data quality   | LOB tick-by-tick + decades clean | Polygon FX 1-min + Stooq daily                                                 |
| Infrastructure | Pods, $30B AUM, 100 PhDs         | Single Hetzner box + Claude Max 20x                                            |
| Horizon        | μs to weeks                      | Days to weeks (pre-trade)                                                      |
| **Edge**       | **Multi-decade signal mining**   | **Narrative + retail extreme triangulation + per-asset transparent reasoning** |

L'edge d'Ichor = la **synthèse multi-perspective transparente** que les
quants ne font pas et que le trader discrétionnaire n'a pas la
bande passante de faire. Voie D + 6 assets + frameworks académiques.

## Les 12 moteurs canonical — académiquement grounded

### Engine 1 — Top-Down Macro (BRIDGEWATER-style)

**Statut Ichor** : ✅ EFFECTIF (Pass-1 régime + ADR-075 cross-asset matrix 6-dim).

**Framework** : Bridgewater 4-quadrant (growth × inflation) + Economic Machine
(productivity trend + short debt cycle + long debt cycle). Implementation
existante Ichor :

- `services/regime_classifier.py` 7-bucket master regime (W104c)
- `_section_cross_asset_matrix` 6-dim (W79 ADR-075)
- Pass-1 régime LLM emission

**Edge decay 2025** : Pure Alpha +33%, Risk-parity drawdown -30% RPAR
(2022 stock-bond corr flip).

**Papers** :

- ResearchGate 2025 _Adaptive All-Weather Portfolio_ (Sharpe 1.17)
- AQR Asness-Frazzini-Pedersen 2012 _Understanding Risk Parity_

**Roadmap Ichor** : déjà solide ; W120 candidate = ajouter Economic Machine
debt-cycle stage classifier explicit.

### Engine 2 — Bottom-Up Micro (BREVAN HOWARD-style)

**Statut Ichor** : ✅ EFFECTIF (Pass-2 asset specialization + 6 frameworks
in `passes/asset.py:_FRAMEWORK_*`).

**Framework** : Per-asset idiosyncratic drivers (rate diff EURUSD,
WTI/oil USDCAD, real yields XAUUSD, etc.). Brevan Howard 14 economists

- 15 quant analysts identifient bottom-up drivers.

**Edge decay** : UIP forward premium puzzle robuste (Lustig 2011 reaffirmed
2024).

**Papers** :

- Morgan Stanley 2025 _Global Macro Strategy Outlook_
- US Treasury Nov 2024 FX Report ($262B EUR reserve manager flows)

**Roadmap Ichor** : déjà solide. W120 = ajouter reserve manager flows
proxy (Treasury TIC monthly = trop slow, need higher freq).

### Engine 3 — Carry Trade

**Statut Ichor** : ❌ ABSENT en moteur formel (rate_diff section data_pool
mais pas de carry signal explicite).

**Implementation pseudo-code** :

```python
def carry_signal(asset: str, lookback_days: int = 60) -> float:
    """Carry trade signal = vol-adjusted rate differential."""
    rate_long, rate_short = get_funding_rates(asset)  # FRED+ECB
    rate_diff = rate_long - rate_short
    fx_vol_60d = realized_vol(asset, lookback_days)
    global_fx_vol = average_vol([EURUSD, GBPUSD, USDJPY, AUDUSD], lookback_days)
    if global_fx_vol > threshold(95th_pctl):
        return 0.0  # carry unwind regime, no position
    return rate_diff / fx_vol_60d  # vol-adjusted carry z-score
```

**Failure modes** : volatility spikes (Aug 5 2024 yen unwind canonical).
Filtre `global_fx_vol` obligatoire.

**Papers** :

- Lustig-Verdelhan 2007 _Currency Returns + Consumption Growth Risk_
- Menkhoff-Sarno-Schmeling-Schrimpf 2012 _Carry Trades + Global FX Vol_
- Asano-Cai-Sakemoto 2024 _Review of Finance_ Vol 28 pp 1759-1805 (vol ambiguity)
- Filipe et al. 2023 _J. Banking & Finance_ 148:106713 (USD funding risk)

**Sub-wave** : W111 (~1 dev-day).

### Engine 4 — Mean-Reversion / Stat Arb

**Statut Ichor** : ❌ ABSENT (pas de moteur dédié).

**Implementation pseudo-code** :

```python
def mean_reversion_signal(asset: str, window: int = 200) -> dict:
    """Z-score on cointegrated spread w.r.t. correlated assets."""
    candidates = correlated_assets(asset, threshold=0.6)
    for partner in candidates:
        spread = log(asset_px) - beta * log(partner_px)  # OLS
        adf_p = adfuller(spread[-200:]).pvalue
        if adf_p < 0.05:
            z = (spread[-1] - mean(spread)) / std(spread)
            if abs(z) > 2.0:
                return {"partner": partner, "z": z, "edge": -sign(z)}
    return {"signal": None}
```

**Cointégration check** : Engle-Granger ADF p<0.05 + half-life OU < 30d.
Re-validation mensuelle obligatoire (structural break risk).

**Papers** :

- Gatev-Goetzmann-Rouwenhorst 2006 (foundational baseline)
- Chen-Alexiou 2025 _J. Asset Management_ (30 ETF pairs 2000-2024)
- Zhu 2024 Yale _Examining Pairs Trading Profitability_

**Sub-wave** : W112 (~1.5 dev-day, requires cointegration test infra).

### Engine 5 — Time-Series Momentum (TSMOM)

**Statut Ichor** : 🟡 PARTIEL (Pass-2 mentions momentum mais pas signal
formel quantifié).

**Implementation pseudo-code** :

```python
def tsmom_signal(asset: str) -> float:
    """Moskowitz-Ooi-Pedersen 2012 TSMOM."""
    r_1mo = log_return(asset, 21)
    r_3mo = log_return(asset, 63)
    r_6mo = log_return(asset, 126)
    r_12mo = log_return(asset, 252)
    signal = sum([sign(r) for r in [r_1mo, r_3mo, r_6mo, r_12mo]])
    target_vol = 0.15
    realized_vol_60d = realized_vol(asset, 60)
    scale = target_vol / max(realized_vol_60d, 0.01)
    return signal * scale  # vol-scaled multi-horizon momentum
```

**Edge decay** : Goyal-Jegadeesh 2023 conditional sur "inferior information
dissemination" regime. AQR replication 2024 confirm robust through 2024.

**Papers** :

- Moskowitz-Ooi-Pedersen 2012 _Time Series Momentum_ JFE
- Wiest 2023 FMPM 30-year review
- Ehsani-Linnainmaa 2022 (factor momentum subsumes stock momentum)

**Sub-wave** : W111 (~0.5 dev-day).

### Engine 6 — Cross-Sectional Momentum (XSMOM)

**Statut Ichor** : ❌ ABSENT.

**Implementation pseudo-code** :

```python
def xsmom_signal(asset: str, universe: list[str]) -> float:
    """Jegadeesh-Titman 1993 + Asness 2013 XSMOM."""
    returns_3to12mo = {a: log_return(a, 252) - log_return(a, 21) for a in universe}
    ranks = pd.Series(returns_3to12mo).rank(pct=True)
    asset_rank = ranks[asset]
    return 2 * asset_rank - 1  # [-1, +1] scaled
```

**Asness 2013** _Value & Momentum Everywhere_ — works cross-asset (FX, indices).

**Sub-wave** : W111 (~0.5 dev-day, combine avec TSMOM).

### Engine 7 — Contrarian / Sentiment Fade

**Statut Ichor** : 🟡 PARTIEL (AAII surface W104b + MyFXBook live mais
pas de signal contrarian formel).

**Implementation pseudo-code** :

```python
def contrarian_signal(asset: str) -> float:
    """Fade retail extremes when sentiment > 2σ z-score."""
    aaii_spread = get_aaii_spread()  # bull - bear
    myfxbook_pct = get_myfxbook_long_pct(asset)
    tff_specnet = get_cftc_tff_specnet_z(asset, 60)

    extremes = []
    if abs(aaii_spread) > 0.40:
        extremes.append(-sign(aaii_spread))
    if abs(myfxbook_pct - 50) > 30:
        extremes.append(-sign(myfxbook_pct - 50))
    if abs(tff_specnet) > 2.0:
        extremes.append(-sign(tff_specnet))

    if len(extremes) >= 2:  # K-of-N voting
        return sum(extremes) / len(extremes)
    return 0.0
```

**Papers** :

- Chicago Fed WP 2023-34 (Luo et al.) — retail contrarian contributes to PEAD
- CFTC 2024 _Retail Traders in Futures Markets_

**Sub-wave** : W112 (~0.5 dev-day).

### Engine 8 — Event-Driven

**Statut Ichor** : ❌ ABSENT (calendar surfaced mais pas signal asymétrique).

**Implementation pseudo-code** :

```python
def event_driven_signal(asset: str, calendar: list[Event]) -> dict:
    """Calendar-proximity × historical reaction asymmetry."""
    upcoming = [e for e in calendar if 0 <= e.minutes_until <= 4320]
    signals = []
    for event in upcoming:
        if event.kind == "FOMC":
            # Pre-FOMC drift short-lived (Applied Economics 2024)
            if event.minutes_until in range(1440, 4320):  # T-1 to T-3 days
                signals.append({"event": event, "bias": +1, "horizon": "intraday"})
        elif event.kind == "ECB" and event.has_press_conf:
            # Bauer et al. CEPR DP21003 — press conf > statement
            signals.append({"event": event, "bias": "wait", "size_scale": 0.5})
    return signals
```

**Papers** :

- Bauer-Acosta-Coibion-Gorodnichenko CEPR DP21003 (USMPD database 2026)
- Lucca-Moench AFA _Pre-FOMC drift_
- Marmora 2023 (foreign-distraction attention)
- Narain-Sangani 2024 (Powell-era press conf reverses statement direction)

**Sub-wave** : W113 (~1 dev-day, requires reaction-asymmetry historical lookup).

### Engine 9 — Narrative Tracking

**Statut Ichor** : 🟡 PARTIEL (news_nlp Couche-2 agent + narrative_tracker
keyword-TF naïf).

**Implementation upgrade** :

- Replace keyword-TF with BERTopic (UMAP + HDBSCAN) ON Reuters/Bloomberg news 30d.
- Top-5 emerging themes per asset via theme_to_asset mapping (CAMEO codes).
- Decay kernel : weight = exp(-age_days / 7).

**Papers** :

- Zhu et al. 2024 arXiv:2404.02053 (BERTopic-Driven Stock Predictions)
- MDPI 2025 _Narrative Econometrics in Equity Markets_
- arXiv:2506.20269 (RollingLDA + LLM hybrid — anti-narrative-invention)

**Failure modes** : narrative reversal (AI bubble Q2 2024 example), polysemy.

**Sub-wave** : W114 (~1.5 dev-day, BERTopic infra setup).

### Engine 10 — Liquidity-Aware (Microstructure proxy)

**Statut Ichor** : 🟡 PARTIEL (VPIN partial wire + dealer GEX absent).

**Implementation** :

- VPIN BVC déjà code (Easley-LdP-O'Hara 2012) ; wire dans data_pool si pas déjà.
- SqueezeMetrics DIX/GEX daily CSV import (W111 candidate).
- Funding spreads SOFR-OIS + FRA-OIS (FRED).
- Si VPIN > 0.4 OR GEX < 0 : `reduce_size + widen_stops` flag.

**Failure modes** : 0DTE flow disruption (post-2024 SPX phenomenon).

**Papers** :

- Easley-Lopez de Prado-O'Hara 2012 _Flow Toxicity & Liquidity_ (canonical)
- Easley et al. 2024 Cornell WP (crypto extension)
- arXiv:2512.17923 (SPY GEX 91.2% pattern materialization 2024)

**Sub-wave** : W114 (~1 dev-day).

### Engine 11 — Vol-Regime

**Statut Ichor** : 🟡 PARTIEL (VIX term + SKEW + VVIX live mais pas signal
formel regime classifier).

**Implementation pseudo-code** :

```python
def vol_regime_signal() -> str:
    """HMM 2-3 states OR rule-based VIX term + VVIX + RR25Δ."""
    vix_term_ratio = vix_1m / vix_3m
    vvix_z = vvix_z_score(60)
    rr_25d = average_rr_25d(["EURUSD", "GBPUSD", "USDJPY"])

    if vix_term_ratio > 1.0 and vvix_z > 2.0:
        return "defensive_regime"
    if rr_25d < -0.5:  # heavy put skew
        return "tail_risk_elevated"
    return "risk_on"
```

**Papers** :

- Yoon 2022 Wiley J. Futures Markets (VIX option IV slope → VIX futures returns)
- arXiv:2510.03236 (regime-switching HAR)
- SEC DERA WP 2504 (Aug 2024 VIX surge analysis)

**Sub-wave** : W113 (~1 dev-day).

### Engine 12 — Cross-Asset Arbitrage + Relative-Value Pairs

**Statut Ichor** : ❌ ABSENT (cross-asset matrix présent mais pas signal).

**Implementation pseudo-code** :

```python
def cross_asset_arb_signal() -> list[dict]:
    """Correlation break detection (Chow test)."""
    historical_corr = {("DXY", "GOLD"): -0.55, ("SPX", "VIX"): -0.78, ...}
    current_corr_60d = {pair: corr_60d(*pair) for pair in historical_corr}
    breaks = []
    for pair, hist in historical_corr.items():
        cur = current_corr_60d[pair]
        if chow_test(pair, breakpoint=Jan2024).pvalue < 0.05:
            breaks.append({"pair": pair, "old": hist, "new": cur, "regime": "structural_break"})
    return breaks
```

**Papers** :

- Herley-Orlowski-Ritter 2024 ScienceDirect (DXY-Gold 2023-2024 breakdown)
- arXiv:2512.12815 (Chow test BTC ETF Dec 2025)
- Zhu 2024 Yale + Gatev et al. 2006 (pairs trading baseline)

**Sub-wave** : W115 (~1.5 dev-day).

## Interconnection patterns (Bias Aggregator W116)

Le Bias Aggregator (`services/bias_aggregator.py`) implémente la couche
de **convergence** entre les 12 moteurs :

### Pattern 1 — Independence gating (Bayesian prior)

- Pictet Alphanatics target **< 0.1 average correlation** between strategies.
- CFM Cumulus accept un nouveau moteur seulement si correlation aux moteurs existants < seuil.
- **Ichor implementation** : track `engine_correlation_matrix` rolling 30d, refuse confluence boost si toutes les engines actives ont corr > 0.5 (= effectively 1 engine, no signal independence).

### Pattern 2 — K-of-N voting confluence threshold

- Pratique : `K=3-5` of 12 engines aligning avant de scaler conviction.
- Below K : default flat or neutral.

### Pattern 3 — Brier-optimized weights (auto-amélioration)

- Per-regime empirical posterior update :
  `weight_engine_at_regime = posterior(engine | regime, realized_outcome)`
- Update via Brier feedback loop (Couche 9 Phase D).
- Bornes [0.05, 0.5] par engine pour éviter degeneracy.

### Pattern 4 — Veto rules (hierarchy)

- **Macro régime vetoes carry trade** pendant high FX vol (Asano 2024).
- **Microstructure vetos sizing** si VPIN > 0.4 (no-trade zone).
- **Top-down régime vetoes momentum** pendant regime change inflection (Goyal-Jegadeesh 2023).
- **Event proximity vetoes new entries** T-12h avant FOMC/ECB.

### Pattern 5 — Hierarchy implicite

```
Engine 1 Top-down macro          → SETS asset class allocation
  ↓
Engine 2 Bottom-up micro         → SETS per-asset directional bias
  ↓
Engines 3,5,6,7 Carry/Mom/Contr  → MODULATES bias (additive z-scores)
  ↓
Engine 4 Mean-rev                → TACTICAL timing within regime
  ↓
Engines 8,11 Event/Vol           → CONSTRAINTS on entry (no-trade zones)
  ↓
Engine 9 Narrative + Engine 12 X-arb → INFORMATIONAL (Pass-3 stress inputs)
  ↓
Engine 10 Liquidity              → EXECUTION layer (sizing scale)
```

## Roadmap W111-W116 estimation

| Wave | Title                           | Effort | Engines           |
| ---- | ------------------------------- | ------ | ----------------- |
| W111 | Carry + TSMOM + XSMOM           | 1.5d   | 3, 5, 6           |
| W112 | Mean-rev + Contrarian           | 2d     | 4, 7              |
| W113 | Event-driven + Vol-regime       | 2d     | 8, 11             |
| W114 | Narrative BERTopic + Liquidity  | 2.5d   | 9, 10             |
| W115 | Cross-asset arb / RV pairs      | 1.5d   | 12                |
| W116 | Bias Aggregator + Brier weights | 2d     | Convergence layer |

**Total Phase F** : ~11.5 dev-days backend pour 12 moteurs + Bias Aggregator.

## Caveats — Ichor != Hedge fund top-tier

- **No execution edge** (vs Medallion microstructure depth).
- **No multi-decade clean tick data** (vs Renaissance moat).
- **No pod army** (vs Citadel 5 strategy businesses).
- **No $30B AUM team** (vs Brevan Howard 14 economists + 15 quants + 26 risk).

**Ichor's actual moat** :

- Narrative integration via Couche-2 + Pass-5 counterfactual + LLM Sonnet 4.6.
- Retail-extreme triangulation (Polymarket + AAII + MyFXBook + Reddit).
- Per-asset transparent reasoning (mechanism cite chiffres réels stamped).
- ADR-017 boundary respect + Critic gate + 7-bucket scenarios calibrés Brier.
- Voie D — $220/mo flat vs $200k+/mo per quant.

Phase F transforms Ichor's analytic depth without trying to match
institutional infrastructure. Each engine is a **synthetic perspective**
the LLM consumes, not a trading algo executing in microseconds.

## Sources

Researcher subagents 2026-05-12 round 10 :

- [Two Sigma Factor Lens (Venn)](https://www.venn.twosigma.com/resources/factor-lens-update)
- [Cliff Asness on Factor Investing (Hoover Oct 2025)](https://www.hoover.org/research/cliff-asness-factor-investing)
- [Taming the Factor Zoo (Feng-Giglio-Xiu JoF 2020)](https://dachxiu.chicagobooth.edu/download/ZOO.pdf)
- [Bridgewater Pure Alpha deep dive (Bawa 2025)](https://navnoorbawa.substack.com/p/inside-bridgewaters-pure-alpha-how)
- [Brevan Howard 2026 (Disruption Banking)](https://www.disruptionbanking.com/2026/01/30/how-brevan-howard-fell-behind-in-the-macro-surge-of-2025/)
- [Multi-Manager Mini-Correction Q1 2026 (HedgeCo)](https://www.hedgeco.net/news/04/2026/the-multi-manager-mini-correction-cracks)
- [Asano-Cai-Sakemoto 2024 SSRN FX Vol Carry](https://papers.ssrn.com/sol3/Delivery.cfm/4993938.pdf?abstractid=4993938)
- [Chen-Alexiou 2025 J. Asset Management cointegration ETF pairs](https://link.springer.com/article/10.1057/s41260-025-00416-0)
- [Wiest 2023 FMPM momentum review](https://link.springer.com/article/10.1007/s11408-022-00417-8)
- [Goyal-Jegadeesh 2023 ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0927538X23002731)
- [Chicago Fed WP 2023-34 retail contrarian](https://www.chicagofed.org/publications/working-papers/2023/2023-34)
- [USMPD CEPR DP21003](https://cepr.org/publications/dp21003)
- [Yoon 2022 J. Futures Markets VIX](https://onlinelibrary.wiley.com/doi/full/10.1002/fut.22317)
- [Herley-Orlowski-Ritter 2024 DXY-Gold breakdown](https://www.sciencedirect.com/science/article/abs/pii/...)
- [arXiv 2512.17923 GEX pattern materialization](https://arxiv.org/html/2512.17923v2)
- [arXiv 2511.09754 History Rhymes macro retrieval](https://arxiv.org/html/2511.09754v1)
- [Zhu et al. 2024 BERTopic arXiv 2404.02053](https://arxiv.org/abs/2404.02053)
- [SNB WP 2025-11 Ballinari-Maly FX sentiment LLMs](https://www.snb.ch)
