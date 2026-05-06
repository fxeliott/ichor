# SPEC v2 — Contenu trader expert (SMC, multi-TF, volume profile, capabilities HF)

**Date** : 2026-05-04
**Compagnon de** : `D:\Ichor\SPEC.md` (Phase 2 Ichor)
**Source** : recherche READ-ONLY web 2026 (joshyattridge/smart-money-concepts, Marketcalls, Zeiierman, ICT, GoCharting, QuantVPS, Goldman Marquee, ACY, Bridgewater, Two Sigma)
**Stratégie Eliot** : momentum sessions Londres/NY, forex majors + indices US + gold, RR3 minimum, BE@RR1, partial 90 % @ RR3, trail 10 % vers RR15+. AT perso 10 % (TradingView), Ichor 90 % (macro/sentiment/positioning/options/CB-NLP).

**ADR-017 contrat dur** : Ichor n'émet jamais de signal BUY/SELL. Affichage **structurel descriptif** OK ; signaux entry/exit interdits.

## 1. SMC algorithmiques pour Ichor

Lib publique `joshyattridge/smart-money-concepts` (MIT, PyPI `smartmoneyconcepts`).

### 1.1 Order Block detection

`smc.ob(ohlc)` retourne colonnes `OB`, `Top`, `Bottom`, `OBVolume = volume + 2 last volumes`, `Percentage = min(highVol,lowVol)/max(highVol,lowVol)`. Détection : dernière bougie de couleur opposée précédant un mouvement impulsif qui casse la structure.

**Ichor affiche** : zones rectangulaires sur mini-chart de la SessionCard avec annotation "OB H4 baissier valide depuis 3j, mitigation 0 %".

### 1.2 FVG (Fair Value Gaps)

Pattern 3-bougies : haut bougie 1 < bas bougie 3 (bullish) ou inverse. Champ `MitigatedIndex` quand le gap est revisité.

**Ichor affiche** : liste des FVG H1/H4 non-mitigés avec distance au spot, zones colorées sur mini-chart.

### 1.3 Liquidity sweep

Détection algorithmique selon Zeiierman : sweep d'un swing high/low + CHoCH micro dans ≤ 5 bars + FVG ≥ 0.5×ATR14 + bougie de displacement. `smc.liquidity(ohlc)` sort les liquidity points.

**Ichor affiche** : "Sweep PDH 1.0915 confirmé 09:42 → reversal bias actif" avec timestamp.

### 1.4 BoS / CHoCH

`smc.bos_choch(ohlc, close_break=True)` retourne BOS/CHOCH ∈ {-1, 0, 1}, Level, BrokenIndex. CHoCH = premier flip de structure intraday ; BOS = confirmation profonde. Paramètre `swing_length` (30 candles left/right typique) contrôle la sensibilité.

### 1.5 Compatibilité ADR-017 (formulation conforme)

- **OK** : "OB H4 baissier non-mitigé à 1.0950-1.0965 — zone d'origine vendeuse historique, à confronter avec ton plan AT"
- **INTERDIT** : "BUY le retest OB H1"

L'analyste senior livre un **état de structure**, pas un signal d'entrée.

## 2. Multi-timeframe synthesis (D1 → H4 → H1 → M15)

### 2.1 Algo de synthèse

Pour chaque TF, calculer :

- (a) régime structurel = up/down/range via swing highs-lows ordering
- (b) état FVG/OB last 50 bars
- (c) position spot vs PDH/PDL/Pivot

Score d'alignement = somme pondérée (D1 ×0.4, H4 ×0.3, H1 ×0.2, M15 ×0.1) ∈ [-1, +1] → libellé `aligned bullish` / `mixed` / `conflict`.

Top-down logic : HTF direction → MTF structure → LTF timing.

### 2.2 UI — composant `<MultiTFContext>`

4 mini-cards horizontales (D1/H4/H1/M15), chacune avec :

- Flèche tendance
- Dernier event SMC (ex "BOS H4 il y a 6h")
- Spot vs range PDH-PDL en %
- Bougie résumée

Header : badge "alignment 75 % bullish" ou "conflict (H4↑ / M15↓)". Couleurs cobalt+navy design system Ichor.

## 3. Volume profile & VWAP par session

### 3.1 VPOC + VAH/VAL

Binner les prix de bougies M1/M5 par tick (1 tick standard, 1 pip pour FX). Volume distribué uniformément sur le range high-low. **VPOC** = bin max volume. **Value Area** : expansion depuis VPOC en ajoutant le voisin de plus gros volume jusqu'à ≥ 70 % (ou 68.2 % Fibonacci) du volume total.

### 3.2 Session split

- Tokyo 00:00-08:00 UTC
- Londres 07:00-16:00 UTC
- NY 13:00-22:00 UTC

Calculer VPOC + VAH/VAL **par session glissante** + **composite 5j** + **previous day**.

### 3.3 Premium / discount

Au sein du range D1 ou de la session : 50%+ = premium (zone short-friendly), 50%- = discount (long-friendly). Code couleur sur la chart Ichor.

### 3.4 Sources data

- **Polygon Currencies $49** WebSocket fournit aggregates per-second et tick-by-tick sur 1000 pairs FX, suffisant pour VPOC FX.
- **Stooq daily** inutile pour VP intraday.
- ⚠ **À confirmer 2026** : la search n'a pas retrouvé le tier Polygon Currencies $49 mentionné dans `ADR-017.md:147-152`. Tiers vus 2026 : Stocks $29 / $79 / $199. **Confirmer pricing avec Eliot avant commit.**

## 4. CVD futures sur 8 actifs

### 4.1 Mapping forex/indices/gold → futures

- EUR/USD → 6E (CME)
- GBP/USD → 6B
- USD/JPY → 6J
- AUD/USD → 6A
- USD/CAD → 6C
- XAU/USD → GC (COMEX)
- US100 → NQ
- US500 / Dow → ES / YM (CME)

### 4.2 Sources free pour CVD — verdict honnête

True CVD nécessite tick + bid/ask attribution (licencié). Options :

- **TradingView** $7/mois real-time CME (le moins cher visualisation manuelle)
- **Crypto WebSocket** Binance/Bybit free tick → BTC CVD comme proxy risk-on/off (déjà partiellement utilisé `confluence_engine.py:466-535`)
- **CME DataMine** = paid sub, hors budget

**Conclusion** : CVD vrai sur futures FX/indices = **pas accessible free tier**. Proxy = OFI Lee-Ready déjà calculé sur Polygon FX dans `confluence_engine.py:219-264`.

### 4.3 Interprétation + UI

- **Absorption** : volume haut / prix immobile = institutionnel accumule
- **Exhaustion** : prix poussé / volume tombe = momentum mort
- **Divergence delta** : prix higher high mais delta lower high = retournement probable

**UI Ichor** : ne pas afficher de CVD inventé ; afficher l'OFI Polygon avec libellé "proxy CVD spot (pas tick futures)".

## 5. Liquidity heatmap (sans dealer flow proprio)

### 5.1 Algo stop clusters

Générer points de liquidité depuis :

- (a) round numbers (.00, .50, .000 ; FX : 1.0900, 1.1000, 152.00 USD/JPY ; gold : 2000, 2050)
- (b) PDH/PDL/PWH/PWL — déjà dans `confluence_engine.py:267-304`
- (c) Asian range high/low
- (d) session opens (Londres 08:00 UTC, NY 13:00 UTC)
- (e) swing highs/lows non-balayés des 10 dernières sessions

**Score "densité de stops"** = somme pondérée des sources convergentes ± buffer 5-15 pips.

### 5.2 UI heatmap

Barre horizontale colorée à droite du mini-chart, gradient rouge (zone short-stops) / vert (zone long-stops), niveaux étiquetés. Pondération honnête : "estimation algorithmique sans données dealer".

## 6. Asian session / Tokyo fix

### 6.1 Détection

**Tokyo fix** = 09:55 JST = 00:55 UTC (été) / 01:55 UTC (hiver). Window de volatilité USD/JPY ±30 min autour, lié au book-balancing institutions japonaises.

### 6.2 Range Asian

High-low entre 00:00 et 08:00 UTC.

- Si range > 50 % ADR moyen → spring déjà épuisé, breakout Londres moins probable
- Si range < 30 % ADR → setup tight, breakout probable

### 6.3 Effet annoncé

Le 08:00 UTC candle close out-of-range = direction journée. Pattern dominant : Londres sweep une side de l'Asian range puis snap-back → vraie direction = opposite.

**Affichage SessionCard Pré-Londres** : "Asian range 1.0890-1.0910 (24p, 40 % ADR) ; sweep upside avant 08:00 GMT inviterait reversal short".

## 7. Order flow profiling — feasible free tier ?

### 7.1 Bid-ask imbalance

Polygon FX WebSocket fournit quotes (bid/offer real-time). OFI Lee-Ready déjà implémenté `confluence_engine.py:219-264` sur bars 4h. Améliorations possibles : OFI sur trades (pas bars) si Polygon expose trades ticks FX en real-time.

### 7.2 Footprint charts

Aucune lib Python open-source dédiée trouvée. Plateformes ($98-200/mois ATAS, Sierra Chart) hors budget. **Verdict** : non-feasible free tier sur FX. Faisable bricolage sur crypto (BTC) via WebSocket Binance free.

### 7.3 Delta divergence

Approximable via OFI vs price action. À afficher comme indicator binaire "OFI 4h diverge du prix : retournement potentiel".

## 8. Multi-asset confluence (étend `confluence_engine.py`)

### 8.1 Facteurs à ajouter pour matcher pro level

Manquants par rapport aux 10 actuels (rate_diff, cot, microstructure_ofi, daily_levels, polymarket, funding_stress, surprise_index, vix_term, risk_appetite, btc_risk_proxy) :

- **DXY directional alignment** (poids 0.3)
- **US 10Y - foreign 10Y slope** (court vs long terme, pas juste niveau)
- **Real yields TIPS 10Y** (haven proxy)
- **Cross-asset corrélations rolling** (EUR/USD vs DXY, gold vs real yields)
- **Sentiment Polymarket Fed-cut probability shift 24h**
- **Asian range expansion ratio**
- **Round number proximity** (distance en ATR au plus proche level psy)

### 8.2 Anti-confluence

Si ≥ 2 facteurs majeurs en contradiction structurelle (ex: rate_diff long EUR/USD + DXY long + cot short EUR), flag `no-trade : régime contradictoire` avec rationale détaillé.

La logique existante `confluence_count` (`confluence_engine.py:633-639`) compte les drivers alignés mais **n'expose pas explicitement les contradictions** — ajout recommandé.

## 9. Session bias frameworks pro

### 9.1 Format institutionnel typique

Goldman Marquee, JPM Markets : _headline conviction_ (Low/Med/High) + _trade thesis_ 2-3 lignes + _triggers_ (catalyst calendar) + _invalidation_ (price level + macro) + _sizing/risk_ (RR cible) + _cross-asset map_. Goldman insiste sur "pre-trade is the hard part".

### 9.2 Adaptation SessionCard Ichor (sans signal entry — ADR-017)

Structure suggérée 8 blocs :

1. **Conviction** % + magnitude attendue
2. **Thesis** 3 lignes synthèse macro+sentiment+structure
3. **Triggers** liste 3-5 catalysts datés
4. **Invalidation** conditions précises (level + macro change)
5. **Cross-asset map** (DXY/yields/VIX/gold/oil cohérents ou pas)
6. **Top idea / supporting / risks** triplet
7. **Confluence score** (déjà en place)
8. **Calibration track-record** (Brier rolling)

## 10. Event-trading filters

### 10.1 Calendrier filter pro

Red-only (3 étoiles) + currencies tracked. Sources free :

- ForexFactory (scrape, fragile DOM)
- FXStreet (deviation ratio = `Actual - Consensus` normalisé)
- Investing.com (scrape, ToS hostile)

### 10.2 Fed-day / NFP rules

- 8 FOMC/an à 14:00 ET, 19:00 UTC
- NFP 1er vendredi du mois 13:30 UTC
- CPI ~2 semaines avant FOMC

Règles pro :

- Pas de trade -2h pré-event
- Ré-évaluation 30min post-release
- ADP comme leading proxy NFP
- ISM Services PMI comme proxy croissance + emploi forward

### 10.3 Volatilité pré-event proxy

- Ratio ATR14 vs ATR60 > 1.3 = volatilité montante
- Spread bid-ask élargi via Polygon quotes
- Positioning Polymarket Fed-cut prob shift > 5pp en 48h

## 11. Hedge funds capabilities — comparatif public

| Firme                       | Public ?                                                                                                               | Mappable Ichor                                                                                                                           |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Bridgewater All Weather** | OUI (4-box growth/inflation typology, risk parity allocation par vol)                                                  | Régime detection : déjà implicite via `risk_appetite`+`funding_stress`+`vix_term`. À formaliser comme "macro régime quadrant" dans Ichor |
| **Two Sigma Factor Lens**   | OUI (Venn — 18 facteurs : Equity, Rates, Credit, Commodities + EM, FX, Local Inflation + Equity Styles + Macro Styles) | Plus alignée avec quant cross-asset que macro pré-trade ; valeur Ichor = catégorisation orthogonale des drivers existants                |
| **Renaissance Medallion**   | NON public (signaux "incl. weather")                                                                                   | Non-mappable, non-cherchable                                                                                                             |
| **Citadel multi-strategy**  | NON public (HFT + sentiment + news real-time)                                                                          | Approche multi-strat, pas un factor library                                                                                              |
| **AQR**                     | OUI (academic factor papers)                                                                                           | Carry, value, momentum, defensive style — ajout possible facteur "carry differential" pour FX (déjà partiellement via rate_diff)         |

## 12. Recommandations concrètes pour SPEC.md

À ajouter en Phase 2 (services backend + composants UI) :

1. **`services/smart_money_structure.py`** — utilise `joshyattridge/smart-money-concepts` (lib MIT) pour calculer OB / FVG / BOS / CHoCH / liquidity sur D1/H4/H1/M15, persiste table `smc_zones` (nouvelle migration).
2. **Composant UI `<MultiTFContext>`** — 4-cards alignées D1→M15 avec score d'alignement.
3. **Section SessionCard "Structure technique contextuelle"** — listant zones SMC actives + niveaux psy + Asian range, avec disclaimer non-signal AMF.
4. **`services/volume_profile.py`** — calcul VPOC/VAH/VAL par session (Tokyo/Londres/NY) sur Polygon WebSocket aggregates, persiste hypertable Timescale.
5. **`services/liquidity_heatmap.py`** — agrégeant round numbers + PDH/PDL + Asian range + swing unswept, score densité.
6. **`services/tokyo_fix.py`** — détection automatique fenêtre 00:55 UTC ±30min, range Asian normalisé en %ADR.
7. **Étendre `confluence_engine.py`** — ajouter facteurs `dxy_alignment`, `real_yields`, `cross_asset_corr`, `round_number_proximity`, `asian_range_expansion`.
8. **Flag `anti_confluence`** dans `ConfluenceReport` quand ≥ 2 drivers majeurs contradictoires → libellé "régime contradictoire, no-trade".
9. **Section "Macro régime quadrant"** Bridgewater-style sur SessionCard (Growth↑/↓ × Inflation↑/↓) avec asset bias par quadrant.
10. **Calendar filter pro** — sourcer ForexFactory ICS + FXStreet deviation ratio, exposer endpoint `/api/events?impact=red&hours=24`.
11. **Pre-event volatility proxy** — ratio ATR14/ATR60 + Polymarket Fed-cut prob shift, exposer comme champ SessionCard.
12. **Vérifier tarif Polygon Currencies $49** — search 2026 ne retrouve pas ce tier — confirmer avec Eliot avant commit (peut-être renommé / changé).
13. **CVD honnête** — ne pas afficher de CVD futures faux ; étiqueter OFI Polygon comme "proxy spot, pas tick futures".
14. **Aucun footprint chart** dans Ichor (pas accessible free tier FX) — éliminer du scope.
15. **Format SessionCard institutionnel** — ajouter blocs `top_idea` / `supporting_2_3` / `risks` au layout courant.

## Sources principales

- [joshyattridge/smart-money-concepts (GitHub)](https://github.com/joshyattridge/smart-money-concepts)
- [smartmoneyconcepts (PyPI)](https://pypi.org/project/smartmoneyconcepts/)
- [Marketcalls SMC + FVG Python tutorial](https://www.marketcalls.in/python/smart-money-concepts-smc-structures-and-fvg-a-python-tutorial.html)
- [Zeiierman Liquidity Sweeps](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading)
- [GoCharting Volume Profile docs](https://gocharting.com/docs/orderflow/volume-profile-charts)
- [Letian Wang Market Profile Python](https://letian-wang.medium.com/market-profile-and-volume-profile-in-python-139cb636ece)
- [QuantVPS CVD](https://www.quantvps.com/blog/cumulative-volume-delta)
- [CME Volume & OI Reports](https://www.cmegroup.com/market-data/volume-open-interest.html)
- [Goldman Sachs Marquee FX](https://marquee.gs.com/welcome/products/execution/foreign-exchange)
- [ACY Multi-Timeframe SMC](https://acy.com/en/market-news/education/power-of-multi-timeframe-analysis-in-smart-money-concepts-j-o-134004/)
- [FXNX Asian Session Breakout](https://fxnx.com/en/blog/master-asian-session-breakout-ultimate-set-forget-strategy)
- [Bridgewater All Weather Story](https://www.bridgewater.com/research-and-insights/the-all-weather-story)
- [Two Sigma Factor Lens FAQ — Venn](https://help.venn.twosigma.com/en/articles/1392786-two-sigma-factor-lens-faq)
- [PriceActionNinja round numbers](https://priceactionninja.com/psychological-levels-round-numbers-how-they-move-price/)
- [International Trading Institute liquidity grabs](https://internationaltradinginstitute.com/blog/liquidity-grabs-institutional-trading-strategy/)
