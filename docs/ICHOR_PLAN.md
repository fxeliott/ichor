# ICHOR — Plan de conception complet (V0+V1+V2+V3+UI)

> Document de référence, écrit 2026-05-02, à relire en début de chaque nouvelle session Claude Code sur Ichor.
> Owner : Eliot. Stack : Hetzner + Cloudflare + Claude Max 20x + free APIs. Budget data : 0 € (sauf Twitter strategic ~30-50€/mois max).

---

## VISION

**Ichor** = moteur d'analyse trading multi-domaine (hors AT). Objectif : couvrir 80% du process pré-trade d'Eliot pour forex majors + indices US + métaux + énergie sur horizons intraday → 4 semaines. Sortie : **indications probabilistes** (haussier/neutre/baissier %) calibrées + briefings + 27 types d'alertes. Jamais de signal d'achat/vente. Le trader décide.

**Ce qu'Ichor n'est PAS** : pas de psychologie/coaching/journal/sizing/AT/crypto/long terme. Outil d'analyse pure.

---

## LES 26 AXES D'ANALYSE (récolte de data exhaustive)

### Macroéconomie (1-4)
- Macro globale (FRED, ECB, BoE, BoJ, BoC, RBA, OECD, World Bank, IMF, Eurostat)
- Calendriers + surprise scores (Investing/FF scrape, Finnhub free, JBlanked)
- Nowcasting (Atlanta GDPNow, NY Fed Staff Nowcast)
- Cycles + leading/coincident/lagging (CFNAI, Sahm Rule SAHMREALTIME)

### Banques centrales (5-8)
- Statements + minutes + Beige Book + dot plot (12 banques) — URLs vérifiées Lot 1
- Speeches members (Fed regional + ECB + BoE + BoJ + RBA RSS)
- NLP Hawkish/Dovish — modèles HF : `gtfintechlab/FOMC-RoBERTa`, `ZiweiChen/FinBERT-FOMC`. Méthodologies Hansen-McMahon (JIE 2016), Aruoba-Drechsel (NBER WP 32417 2024)
- Pivot tracker historique
- ⚠ Powell pressers PDF path correct = `/mediacenter/files/`

### Liquidité & Funding (9-13)
- Net Liquidity (FRED `WALCL` - `RRPONTSYD` - `WTREGEN`)
- SOFR, OBFR, EFFR (FRED), repo data DTCC
- HY/IG spreads (FRED `BAMLH0A0HYM2`, `BAMLC0A0CM`) ⚠ **3 ans glissants depuis avril 2026 → archivage Phase 0 obligatoire**
- Money market flows (ICI MMF AUM weekly XLS, OFR Money Market Fund Monitor)
- Treasury flows (TIC foreign holders, QRA, NY Fed Primary Dealer Surveys)
- ⚠ Cross-currency basis = Bloomberg-only, pas de proxy gratuit propre. SOFR-OIS spread à calculer manuellement

### Inflation & Term Structure (14-17)
- TIPS breakevens FRED `T5YIE`, `T10YIE`, `T5YIFR`
- Surveys NY Fed SCE, U Mich `MICH`, Philly Fed SPF, Conference Board
- Yield curve `T10Y2Y`, `T10Y3M`, `DGS10`, `DGS2`
- Term premium NY Fed ACM (FRED `THREEFYTP10`)

### Fondamentaux entreprises (18-23)
- SEC EDGAR (10-K/Q/8-K/Form 4/13F/13D/G/D) ⚠ **UA strict format SEC `"AppName contact@email"` + 10 req/s**
- Earnings (Finnhub free, FMP free, sec-api.io free signup)
- Insider Form 4 (OpenInsider à reconfirmer en local — fragile, Quiver free Visitor plan)
- 13F (WhaleWisdom freemium, sec-api.io free)
- Short interest FINRA
- Buybacks/M&A/spin-offs/IPOs/dividends

### Smart Money & Government (24-27)
- Congressional trades (Capitol Trades scraping gratuit, Quiver free Visitor plan)
- Lobbying : Senate LDA (`lda.senate.gov/system/public/`) ⚠ **migration vers LDA.gov avant 2026-06-30**
- Government contracts (USAspending.gov, SAM.gov)
- Hedge fund letters (SeekingAlpha free paywall croissant)
- ⚠ **OpenSecrets API morte** depuis 2025-04-15 → exclure
- ⚠ **ValueWalk RSS compromis** (hijacké casino) → exclure

### Sentiment multi-canal (28-35)
- Polymarket Gamma API (gratuit, sans auth — gros levier différenciant)
- Kalshi (CFTC-regulated)
- Reddit OAuth API free 100 req/min
- StockTwits free
- **Twitter/X — whitelist stratégique 30-50 comptes officiels** (Fed/ECB/BoE/BoJ/officiels/agences). Budget 30-50€/mois max via TwitterAPI.io ou pay-per-task. Jamais finfluencers.
- Surveys traditionnels (AAII, Sentix, ZEW, IFO, GfK, Conference Board, U Mich)
- CNN F&G (wrappers PyPI), CBOE put/call ratio
- Google Trends (pytrends + API officielle 2025), Wikipedia pageviews
- NLP : FinBERT-tone (yiyanghkust), FinGPT (AI4Finance)

### Positionnement (36-38)
- CFTC COT (`cot_reports` lib + CFTC publicreporting direct)
- Retail SSI scrape DailyFX/MyFXBook
- Options dealer GEX : Matteo-Ferrara/gex-tracker, FlashAlpha free Starter (5 req/jour), Tradier free, CBOE Gamma Index dashboard

### Volatilité (39-44)
- VIX, VVIX, VIX9D, VIX3M, VIX6M (FRED + yfinance)
- Vol bonds/FX/commodities (^MOVE, ^OVX, ^GVZ)
- Term structure VX (CFE delayed)
- IV surfaces, skew, smile via Tradier raw chains
- VRP (calcul interne IV - RV30j)
- Microstructure VPIN via `flowrisk` (Easley/López de Prado), VisualHFT, OANDA streaming

### Cross-asset & corrélations (45-47)
- DXY broad (FRED `DTWEXBGS`), US10Y, gold, oil, copper, HY-IG, BDI
- Rolling correlations matrix + breakdowns
- Régime HMM 3 états (calm/elevated/stressed) + PCA cross-asset

### Énergie (48-52)
- Pétrole : EIA API v2 (STEO, AEO, weekly stocks), OPEC MOMR PDF, IEA OMR free, Baker Hughes XLSX
- NatGas : EIA storage + NOAA + CDD/HDD, Henry Hub
- Électricité : ISOs CAISO, NYISO, ERCOT, MISO, PJM, ISO-NE (free real-time)
- Tanker : VesselFinder, IMF PortWatch (2065 ports weekly mardi 9h ET)
- Crack spreads, refinery util, storage Cushing

### Métaux (53-55)
- Or : real yields TIPS, DXY, central bank purchases (WGC quarterly), ETF flows SPDR Gold
- Argent : gold/silver ratio
- Métaux industriels (cuivre yfinance `HG=F`, LME limited free)

### Agricoles (56-58)
- Grains : USDA NASS QuickStats, USDA WASDE PDF, USDA FAS PSD
- Softs : ICO (coffee), ICCO (cocoa), ISO (sugar)
- Climate & ENSO : NOAA NCEI + CPC ENSO, Drought Monitor

### Forex spécifique (59-62)
- Interest rate differentials (calcul interne FRED+ECB+BoE+BoJ)
- BIS effective exchange rates
- Foreign reserves IMF COFER
- Cross-currency basis (Bloomberg-only, proxy limité)

### Sessions & Volume (63-67)
- Sessions Asie/Europe/US, signatures, overlaps (LDN-NY 12-16 UTC = sweet spot Eliot)
- Volume Profile journalier (POC, VAH, VAL) calculé depuis OHLCV
- VWAP intraday + bands
- Cross-session range expansion
- Fixings : London 4 PM, ECB 14:15 CET, NY 10 AM cut

### Géopolitique & événements (68-73)
- Conflits/tensions : ACLED (free non-commercial), GDELT DOC 2.0
- Indices uncertainty : GPR Caldara-Iacoviello AI-GPR daily, EPU FRED `USEPUINDXD`, WUI Ahir-Bloom-Furceri, TPU
- Sanctions : OFAC SDN list XML, EU consolidated sanctions XML, UK OFSI
- Élections + sommets calendars (G7/G20/BRICS/OPEC)
- Catastrophes : USGS earthquakes, NOAA NHC hurricanes, NASA EONET, ESA Sentinel
- Cyber + terrorism : CISA advisories, GTD

### Shipping & global trade (74-78)
- Container freight : Drewry WCI weekly free, Freightos FBX, Xeneta XSI
- Bulk : Baltic Dry via TE/Investing scrape (officiel paid)
- Port activity : IMF PortWatch (gros levier free)
- Suez/Panama : scraping communiqués
- Land : ATA Truck (FRED `TRUCKD11`), Cass Freight (FRED `FRGSHPUSM649NCIS`/`FRGEXPUSM649NCIS`)

### News & Media (79-82)
- RSS officiels : Reuters, AP, FT free, MarketWatch, CNBC, Bloomberg public
- News APIs : GDELT DOC 2.0, GNews/NewsAPI/Currents free 100-1000 req/jour
- Blogs macro free portions : Calculated Risk, The Macro Compass
- NLP narrative tracking via topic modeling (LDA / BERTopic)

### Recherche académique (83)
- Fed FEDS notes, BIS WP, IMF WP, ECB WP, NBER, arXiv q-fin RSS daily, SSRN q-fin
- Pipeline : crawl → embed → ranker par relevance → digest hebdo dimanche

### Knowledge Graph (84)
- Stack : Neo4j community ou Kuzu embedded
- Entités : actifs, banquiers centraux, entreprises, pays, événements, narratives, sources
- Relations causales : Powell→Fed→USD→DXY→XAU ; OPEC→WTI→CAD/NOK ; ECB→EUR→DAX

### World State Hub + Calendar + Anti-Fraud + Crisis Mode (85-87, 26)
- Page synthèse "Le monde aujourd'hui selon Ichor" (Claude Opus daily)
- Events tracker exhaustif (earnings, macro, CB, OPEC, rebalancings, refunding)
- AMF blacklist (data.gouv.fr CSV) + SEC litigation + FINRA + FCA + ASIC + SEBI + BaFin → cross-check sentiment/news
- Crisis Mode trigger : VIX +30% OU GDELT mega-cluster OU CB emergency

---

## LES 12 MOTEURS D'ANALYSE (lentilles méthodologiques)

Pour chaque actif, Ichor applique simultanément :

1. **Top-down macro** (macro global → région → pays → actif)
2. **Bottom-up micro** (données granulaires → actif)
3. **Carry / rate differential** (différentiel taux → flow currencies)
4. **Mean reversion** (position extrême → retour moyenne)
5. **Momentum sentiment** (trend sentiment + flow)
6. **Contrarian positioning** (foule extrême → fade)
7. **Event-driven** (catalyseur connu → drift documenté)
8. **Narrative-driven** (narrative dominante → flow)
9. **Liquidity-driven** (funding stress → risk-off)
10. **Vol-regime** (régime vol → comportement)
11. **Cross-asset arbitrage** (décorrélation anormale → convergence)
12. **Pairs / relative value** (actifs corrélés divergent → trade)

**Bias Aggregator** = pondération Brier-weighted des 12 moteurs, par actif et horizon, ajustée au régime courant (Markov chains transition probabilities).

**Niveau quant institutionnel ajouté** :
- Mixed-frequency MIDAS regression (combine monthly + daily + intraday)
- State-space / Kalman filter (latent factors)
- Factor mining auto via Microsoft Qlib
- Counterfactual reasoning ("Si Powell n'avait pas dit X...")
- Causal Bayesian Networks (propagation cause→effet)

---

## PROFONDEUR PAR ACTIF — ~280 features

Chaque actif analysé via :
- 12 moteurs simultanés
- ~280 features (ex EURUSD : rate diff, CB NLP, COT, sentiment, vol, cross-asset, géo, sessions, etc.)
- 7 scenarios probabilisés (crash flush / strong bear / mild bear / base / mild bull / strong bull / melt-up) avec triggers + targets + invalidation
- 8-12 stress tests (CPI surprise +0.3pp, NFP miss, FOMC hawkish, ECB cut, VIX spike, etc.)
- 3-5 historical analogues via DTW (régimes historiques similaires)
- Driver decomposition explicite : chaque biais avec contributions par driver visibles et challengeables

---

## 15 INSTRUMENTS CIBLES + DRIVERS SPÉCIFIQUES

| Instrument | Drivers dominants |
|---|---|
| EURUSD | Rate diff US-EU, Fed/ECB NLP, COT, Polymarket Fed-cut, EU PMI |
| GBPUSD | BoE NLP, UK CPI/wages, Brexit-residual, gilt 10Y, GBP COT |
| USDJPY | Fed-BoJ rate diff, Yen carry, BoJ YCC, US10Y, JPY safe haven |
| AUDUSD | China data, iron ore, RBA NLP, AUD COT |
| USDCAD | Oil WTI/Brent, BoC, Canadian CPI, oil rig count |
| USDCHF | SNB stance, EUR strength, safe haven, CHF COT |
| NZDUSD | RBNZ, dairy, China demand, AUDUSD corrélation |
| NAS100 | Mega-cap tech earnings, AI capex, US10Y, GEX 0DTE, VIX |
| US30 | Cyclicals, ISM Manuf, oil, Fed, GEX |
| SPX500 | Broad US macro, S&P earnings, GEX major, Polymarket Fed-cut |
| XAUUSD | TIPS real yields, DXY, CB purchases (WGC), ETF flows, geo tail |
| XAGUSD | Gold/silver ratio, industrial demand China, solar capex |
| WTI | EIA STEO, OPEC MOMR, Baker Hughes, China demand, Cushing |
| Brent | Brent-WTI spread, EU demand, OPEC+ discipline, Suez |
| NatGas | EIA storage, NOAA weather (CDD/HDD), LNG, ISO grid load |

**Phase 1** : 3 actifs en profondeur (EURUSD + XAUUSD + NAS100). Phases 2-3 : extension aux 12 autres.

---

## ARCHITECTURE MULTI-AGENT

```
ORCHESTRATOR (Claude Opus 4.7, 1M ctx) — décompose, route, synthétise, mémoire long-terme via Letta
       │
       ├── MACRO AGENT (Cerebras Llama-70) : FRED, ECB, liquidity
       ├── SENTIMENT AGENT (Groq Llama-70) : Polymarket, Reddit, F&G
       ├── POSITIONING AGENT (Groq) : COT, 13F, GEX
       ├── CB-NLP AGENT (Claude Sonnet 4.6) : FOMC, ECB, BoE, BoJ
       └── NEWS-NLP AGENT (Haiku 4.5) : RSS, Reddit, FinBERT
       │
       ▼
BIAS AGGREGATOR (Bayesian + Logistic + LightGBM, Brier-weighted ensemble, regime-aware)
       │
       ▼
CRITIC AGENT (Claude Sonnet 4.6) — challenge, contre-arguments, flag overconfidence
       │
       ▼
JOURNALIST AGENT (Claude Opus) — briefings, asset cards, voice scripts ElevenLabs Brian
```

**Stack agents (vérifié Lot 3)** :
- **Claude Agent SDK Python** v0.1.72 (MIT, MCP natif) — recommandé principal
- **DSPy** v3.2.0 (MIT) — optimisation auto prompts, économie tokens
- **LlamaIndex Workflows** v0.14.21 — RAG sur news/filings/papers
- **Letta** v0.16.7 (Apache) — mémoire persistante long-terme
- **Pydantic AI** v1.89.1 — type-safe pipelines critiques

**Drapeaux rouges (à éviter)** : AutoGen (maintenance), OpenAI Swarm (déprécié), mlfinlab (passé propriétaire → réimplémentation maison triple-barrier/CPCV/PBO depuis López de Prado), alibi-detect (BSL 1.1), Kats/Merlion/scikit-multiflow (dormants).

---

## AUTO-APPRENTISSAGE V1

- **Brier-weighted ensemble** : poids = inverse Brier 90j. Modèles bien calibrés dominent automatiquement.
- **Regime-aware** : 3 jeux de poids HMM (calm/elevated/stressed). Switch auto.
- **Online Bayesian update** via NumPyro entre recalibrations.
- **Concept drift detection** via `river` (BSD-3, ADWIN/page-Hinkley) → ré-entraînement accéléré si distribution change.
- **Tournament of models** : 6 modèles concurrents, le meilleur Brier 60j gagne.
- **Self-Reflection hebdo dimanche** : Claude analyse les biais de la semaine + outcomes + identifie patterns d'erreurs **du modèle** (pas du trader). Ajustements auto.

**Plafond honnête** : Brier <0.20 + hit rate calibré 58-62% sur TCT, 60-65% CT, 55-60% MT. Au-delà = overfit ou tricherie.

---

## 27 TYPES D'ALERTES

1. Event surprise (data >1σ vs consensus)
2. Threshold (VIX>X, DXY breach, etc.)
3. Anomaly multi-source (VPIN spike, GDELT cluster)
4. Divergence (Polymarket vs COT, retail vs pro)
5. Régime change (HMM transition prob >0.7)
6. Calendar T-30min
7. Calendar T-5min
8. Narrative shift (top narrative change)
9. Polymarket move significatif (>10pp 24h)
10. CB tone shift (Hawkish→Dovish ou inverse)
11. Cross-asset corr breakdown
12. Vol regime change
13. Smart money positioning extreme (COT >2σ)
14. Insider cluster
15. Liquidity stress (HY OAS widening, RRP drop)
16. Geo escalation (ACLED level)
17. Earnings surprise
18. UOA — Unusual Options Activity
19. Power grid stress
20. Shipping disruption
21. Storage surprise (EIA crude/gas >1σ)
22. Weather extreme
23. Sanction announcement
24. Election result
25. Source credibility flag (broker blacklisted)
26. New paper highly relevant (cosine >0.85)
27. Crisis Mode triggered

**Canaux** : Telegram (déjà setup) + email + voice ElevenLabs (Brian) + dashboard live + push PWA.

---

## UI/UX VISION

### Identité visuelle
- **Inspirations** : Linear.app + Vercel + Polymarket + TradingView + Numerai + Stripe Dashboard + Bloomberg Terminal moderne
- **Dark mode par défaut** + light optionnel
- **Couleurs sémantiques** sobres : haussier #4ADE80, baissier #F87171, neutre #94A3B8, alerte #FB923C, crisis #E879F9, confidence haute #22D3EE
- **Typo** : Inter (UI) + JetBrains Mono (chiffres)
- **Aucun emoji UI**, icônes Lucide/Tabler
- **Logo** : monogramme géométrique + pulse dot animé

### Pages principales (sitemap)
`/` Dashboard live · `/world` World State Hub · `/asset/:symbol` Asset card profonde · `/scenarios/:symbol` 7 scenarios visualisés · `/macro` · `/central-banks` · `/sentiment` · `/positioning` · `/volatility` · `/cross-asset` · `/energy` · `/geopolitics` · `/shipping` · `/calendar` · `/narratives` · `/research` · `/knowledge-graph` · `/alerts` · `/performance` · `/briefings` · `/fraud-watch` · `/settings`

### Layout responsive
- Desktop ≥1280px : 3 colonnes (nav + main + right panel)
- Tablet 768-1280 : 2 colonnes
- Mobile <768 : 1 colonne, nav bottom tabs, swipe entre asset cards

### Vivant, pas static
- Pulse dot sur données live, count-up/down animés, transitions Framer Motion
- WebSocket push 5 sec, optimistic UI, stale indicator >X min
- Cmd+K command palette (Linear-like), hotkeys trader (e=EURUSD, g=gold...)
- Toasts non-intrusives Sonner, drag&drop asset cards
- Charts : transitions fluides, pas de flash

### Stack tech UI/UX
| Couche | Choix |
|---|---|
| Framework | Next.js 15 (App Router) |
| CSS | Tailwind CSS v4 |
| Composants | shadcn/ui + Radix UI |
| Charts financiers | lightweight-charts TradingView v5 (avec attribution) ou ECharts v6 |
| Knowledge graph | react-force-graph ou sigma.js |
| Animations | Framer Motion v11 |
| Icons | Lucide React |
| Real-time | Socket.IO ou native WS |
| State | Zustand + TanStack Query |
| PWA | next-pwa ou @serwist/next |
| Tableaux | TanStack Table v8 |
| Theme | next-themes (dark/light) |
| Toasts | Sonner |
| Command palette | cmdk |

**Frontend host** : Cloudflare Pages (gratuit, edge mondial, PWA-ready)
**Backend** : Hetzner (Postgres + TimescaleDB + Redis + FastAPI Python ou Hono Node)
**API** : tRPC ou GraphQL Yoga (type-safe)

### 12 composants design system
`<BiasBar />`, `<AssetCard />`, `<Heatmap />`, `<RegimeIndicator />`, `<EventTimeline />`, `<ScenarioBars />`, `<ContributionList />`, `<MetricCard />`, `<NarrativePill />`, `<AlertToast />`, `<SourceBadge />`, `<ConfidenceBand />`

---

## DELIVRABLES UTILISATEUR

- **Briefings multi-créneaux** : 06h00 UTC (pre-Londres), 12h00 UTC (pre-NY), 17h00 UTC (NY mid), 22h00 UTC (NY close), Dimanche 18h00 UTC (weekly review). Format : email + Telegram + page web + audio ElevenLabs FR voix Brian.
- **Voice Q&A** : "Ichor pourquoi tu es haussier sur EURUSD ?" → Whisper local Hetzner → Claude → ElevenLabs Brian (~30s réponse)
- **Asset Cards** : breakdown 250+ features par axe, confidence band, scenarios, événements à risque
- **Dashboard live** : top bar régime + calendar + Polymarket pulse + heatmap cross-instrument
- **World State Hub** : "Le monde aujourd'hui selon Ichor" daily synthesis
- **Knowledge Graph navigable** : D3/sigma.js entités + relations
- **Macro Narrative Tracker** : top narratives + trajectoires
- **Research digest hebdo dimanche** : papers ranked + résumé Claude
- **Scenarios visualisés** : 7 scenarios sur chart, target prices, triggers

---

## ROADMAP (focus profondeur par actif)

| Phase | Durée | Livrables |
|---|---|---|
| **0** | 1-2 sem | Setup : repo Git, structure dossiers, SSH Hetzner, Postgres+TimescaleDB+Redis install, clés API testées (FRED, EIA, Polymarket, OANDA, Tradier), **archivage HY/IG OAS dès J0** (critique), persona Ichor v1, voix Brian |
| **1** | 6-8 sem | **MVP : 3 actifs en profondeur** (EURUSD + XAUUSD + NAS100). 250+ features chacun, 7 scenarios, 8 stress tests, 12 moteurs, tournament basique, briefings 06h UTC + audio Brian, Telegram alerts (top 10 types). Frontend Next.js avec asset cards + dashboard. |
| **2** | 4-6 sem | Extension +5 actifs (GBPUSD, USDJPY, US30, SPX500, WTI). Scenarios visualisés. Critic Agent. World State Hub. |
| **3** | 4-6 sem | Extension +5 derniers actifs (AUDUSD, USDCAD, USDCHF, XAGUSD, Brent, NatGas). Knowledge Graph. Macro Narrative Tracker. |
| **4** | 4-6 sem | Axes manquants : climate events, shipping (PortWatch), satellite limited, power grid (CAISO/NYISO/ERCOT/MISO/PJM/ISO-NE), smart money/Congress (Quiver, Capitol Trades), CB NLP deep (FOMC-RoBERTa, Hansen-McMahon, Aruoba-Drechsel). |
| **5** | 4-6 sem | Tournament étendu + active learning + concept drift + Crisis Mode + Voice Q&A complet. |
| **6** | 4-6 sem | Recherche académique synthesizer (arXiv/NBER/BIS/IMF/Fed) + Fraud Watch complet (AMF/SEC/FINRA/SEBI) + tous les 27 types d'alertes. |
| **7** | 4-6 sem | Polish UX + multi-tenant scaffold optionnel (membres formation Yone). |

**Total** : 36-44 semaines pour Ichor V1 complet. **MVP utilisable Phase 1** : 7-9 semaines.

**Gate strict** : on ne passe à phase suivante qu'avec **3 mois Brier scores publiés** sur la phase précédente. Sinon consolidation, pas extension.

---

## DÉCISIONS VALIDÉES

- ✅ **Ichor = analyse pure** (pas psycho/journal/sizing/AT)
- ✅ **Phase 1 = 3 actifs en profondeur** plutôt que 15 superficiels
- ✅ **Budget 0 €** sauf Twitter strategic ~30-50€/mois max sur 30-50 comptes officiels
- ✅ **Discipline phases** avec gate Brier score
- ✅ **Frontend Next.js + Tailwind + shadcn/ui** sur Cloudflare Pages
- ✅ **Dark mode par défaut** (light togglable)
- ✅ **Mobile-first PWA** (installable home screen + push notifications)
- ✅ **Persona Ichor** : voix Brian ElevenLabs, sobre, francophone, jamais BUY/SELL, publie erreurs
- ✅ **Multi-tenant scaffold** prévu Phase 7 (refonte plus tard si on a tort)
- ✅ **Stop scope creep** : après V3, gates Brier 6 mois pour ajouter
- ✅ **Stack agent** : Claude Agent SDK + DSPy + LlamaIndex Workflows + Letta + Pydantic AI
- ✅ **Charts** : à choisir entre lightweight-charts (attribution TV) ou ECharts → décision SPEC
- ✅ **Knowledge graph** : à choisir entre Neo4j community ou Kuzu embedded → décision SPEC

---

## ALERTES CRITIQUES À NE PAS OUBLIER (issues recherche Lots 1+2+3)

1. **HY/IG OAS archivage J0 obligatoire** — FRED limite `BAMLH0A0HYM2`+`BAMLC0A0CM` à 3 ans glissants depuis avril 2026. Sans archivage immédiat, perte historique long irréversible.
2. **OpenSecrets API morte** depuis 2025-04-15 → utiliser Senate LDA bulk
3. **Senate LDA → migration LDA.gov avant 2026-06-30** → wrapper config bascule
4. **ValueWalk RSS compromis** (hijacké casino) → exclure
5. **GeoEconWatch n'existe pas** → mention initiale erreur
6. **mlfinlab passé propriétaire** → réimplémentation triple-barrier/CPCV/PBO depuis livre López de Prado
7. **alibi-detect BSL 1.1** → vigilance commerciale
8. **AutoGen + OpenAI Swarm + Kats + Merlion + scikit-multiflow** : drapeaux rouges
9. **SEC + Fed régionales WAF** → User-Agent format `"AppName contact@email"` + 10 req/s obligatoire
10. **Powell pressers PDF** path correct = `/mediacenter/files/` (pas `/monetarypolicy/files/`)
11. **BoC speeches** path = `/press/speeches/` (pas `/speeches-appearances/`)
12. **PBoC EN** section ID `3688006`
13. **ECB Working Papers** path = `/press/research-publications/working-papers/`
14. **Prompt injection détectée** lors recherche → tout pipeline NLP qui ingère contenu externe DOIT avoir couche sanitation systématique
15. **Cross-currency basis + FRA-OIS** = Bloomberg-only, pas de proxy gratuit propre. SOFR-OIS spread à calculer manuellement
16. **lightweight-charts TradingView** : attribution + logo obligatoires si utilisé en prod
17. **OpenBB AGPL** : si Ichor closed-source commercialisé → soit open-source / payer Pro / réécrire collectors maison

---

## ANTI-ARNAQUES — sources whitelist/blacklist strictes

### Bannies systématiquement
- Tous finfluencers Twitter/YouTube/TikTok/Telegram retail
- Sites d'éducation déguisés en signal-sellers (cf SEBI Avadhut Sathe déc 2025, sanction 60M€)
- Brokers blacklistés AMF (MEXC, CoinEX, Zoomex + 12 autres 2024)
- Signaux Telegram payants
- "Trading academies" promettant 80%+ win rate
- Sites avec affiliation broker non déclarée
- Indicateurs proprios sans peer review
- ZeroHedge / similaires non vérifiés

### Whitelistées
- Banques centrales officielles (Fed, ECB, BoE, BoJ, BoC, RBA, etc.)
- Organisations internationales (BIS, IMF, World Bank, OECD, IEA, OPEC)
- Régulateurs (AMF, SEC, FINRA, FCA, BaFin, ASIC, SEBI, MAS, JFSA)
- Exchanges officiels (CBOE, CME, ICE, LSE, Euronext)
- Données gov/agences (FRED, EIA, USDA, NOAA, USGS, FINRA, EDGAR)
- Académique peer-reviewed (NBER, BIS WP, Fed FEDS, ECB WP, IMF WP, ECB Research)
- Marchés prédictifs régulés (Polymarket, Kalshi CFTC-regulated)
- Sources institutionnelles vérifiées (Reuters, AP, FT, Bloomberg)

---

## CADRE LÉGAL

- **France (AMF)** : Ichor = information générale non personnalisée + disclaimer adéquat = pas du conseil au sens AMF (pas de CIF requis). Règle : Ichor montre la même chose à tous, jamais "Eliot, achète XAUUSD à 2654".
- **Malaisie (SC)** : Eliot sera résident MY <1 an. CMSA framework. À reconfirmer avocat MY 2-3 mois avant Phase 7 commercialisation membres.
- **Disclaimers obligatoires** : visible chaque vue + chaque export. "Information générale, ne constitue pas un conseil en investissement au sens de l'art. L.541-1 CMF. Ne tient pas compte de la situation personnelle de l'utilisateur. Performances passées ≠ performances futures."
- **Pas de personnalisation** par utilisateur (clé du non-conseil)
- **Pas de signaux BUY/SELL** tranchants (uniquement biais probabilistes %)

---

## RESSOURCES YONE DÉJÀ DISPONIBLES (vault USB E:)

### LLM disponibles
- Anthropic Claude Max 20x principal + clé API backup
- Gemini ⚠ **incident billing 2026-04** (95.67€ abusés Veo/Imagen, lockdown OK, dossier remboursement) → vigilance rotation clés
- Groq Cloud (free 14400 req/jour)
- Cerebras (free 60 req/min)
- NVIDIA NIM (free 1000 req/mo)
- HuggingFace (free inference + downloads)
- ⚠ **OpenAI INTERDIT** par règle interne L12

### Infra
- Serveur dédié Hetzner `root@178.104.39.201` (`fxmilyapp.com`)
- Cloudflare API token (Workers AI + Workers + Pages)
- Oracle Cloud Always Free Tier actif
- GitHub PAT (compte fxeliott)

### Data trading
- OANDA Practice API (forex/indices/métaux) — gratuit
- FRED API — clé valide
- Finnhub free tier — clé valide
- Twelve Data — clé valide
- MT5 bridge Wine + RPYC port 18812 (Blueberry Markets demo)

### Diffusion
- Telegram bots multiples (main, Yone formation, monitor)
- ElevenLabs TTS voix Brian (multilingual_v2) déjà configurée
- Simli avatar disponible

### Observabilité
- Langfuse local via SSH tunnel Hetzner port 13000
- n8n local port 5678

---

## PROCHAINE ÉTAPE

1. ✅ **Plan complet sauvegardé ici** (D:\Ichor\ICHOR_PLAN.md)
2. ⏭ **`/clear` la session courante** (saturée à ~150k tokens)
3. ⏭ **Nouvelle session** depuis D:\Ichor\
4. ⏭ **Lancer `/spec`** ou demander "fais le SPEC d'Ichor en relisant ICHOR_PLAN.md"
5. ⏭ Claude relit ICHOR_PLAN.md + interview ~20-30 questions tech précises (sources exactes Phase 1, schéma DB, structure features, choix charts, etc.) → écrit `SPEC.md`
6. ⏭ Validation SPEC.md
7. ⏭ Encore `/clear`
8. ⏭ **Phase 0 démarre** : repo git init, structure dossiers, SSH Hetzner setup propre, install Postgres+TimescaleDB+Redis, test clés API, archivage HY/IG OAS immédiat, persona Ichor v1, voix Brian setup

---

*Document maintenu par Claude. Mettre à jour à chaque évolution majeure du plan.*
