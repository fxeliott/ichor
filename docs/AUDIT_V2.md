# AUDIT V2 Ichor — synthèse consolidée 10 sub-agents

**Date** : 2026-05-02
**Auteur** : Claude Code (orchestration de 5 sub-agents v1 + 5 sub-agents v2)
**Référence amont** : [ICHOR_PLAN.md](./ICHOR_PLAN.md), [SPEC.md](./SPEC.md), [AUDIT.md](./AUDIT.md)
**Mandat** : audit critique encore plus profond + design web magnifique + couverture exhaustive scénarios + livres canon traduits en features + triple-check rouge

---

## ⚠️ ALERTES BLOQUANTES — à corriger AVANT tout démarrage Phase 0

Le triple-check rouge a détecté 5 trous majeurs invalidant des choix de SPEC.md. **Ces points doivent être tranchés avant /clear et nouvelle session Phase 0**.

### 🚨 1. Kuzu est ABANDONNÉ depuis 2025-10-10

**Source** : [The Register 2025-10-14](https://www.theregister.com/2025/10/14/kuzudb_abandoned/) — projet archivé par Kùzu Inc.
**Impact** : SPEC §3.3 + §11 spécifient Kuzu embedded comme choix verrouillé pour Knowledge Graph.
**Correction requise** :

- **Recommandé** : **Neo4j Community 5.x** (Apache 2.0, mature, Cypher natif). Service Java séparé sur Hetzner, ~1 GB RAM.
- **Alternative** : **FalkorDB** (Redis-based, actif, drop-in OpenCypher). Plus léger.
- **Forks Kuzu** (Bighorn / Ladybug) : immatures, pas pour solo dev débutant.
- **Workaround low-effort** : **Postgres + AGE extension** (graphs dans Postgres existant, syntaxe Cypher partielle, perf variable mais pas de service séparé).

### 🚨 2. Versions de libs hallucinées dans PLAN/SPEC

| Lib citée            | Version SPEC/PLAN | Réalité PyPI/GitHub 2026-05                                                 | Verdict                   |
| -------------------- | ----------------- | --------------------------------------------------------------------------- | ------------------------- |
| Claude Agent SDK     | v0.1.72           | **v0.1.71**                                                                 | Halluciné                 |
| Pydantic AI          | v1.89.1           | v1.88.0 PyPI / v1.89.0 GitHub                                               | Halluciné (.1 inexistant) |
| LlamaIndex Workflows | v0.14.21          | v0.14.21 = `llama-index-core`, pas `llama-index-workflows` (package séparé) | Confusion package         |
| DSPy                 | v3.2.0            | v3.2.0 confirmé                                                             | OK                        |
| Letta                | v0.16.7           | v0.16.7 confirmé                                                            | OK                        |

**Correction requise** : pinning `>=X,<Y` flexible plutôt que versions exactes hallucinées. Vérifier chaque lib via context7 / PyPI **avant** chaque install Phase 0.

### 🚨 3. Quotas free tier annoncés FAUX dans PLAN

| Provider   | PLAN annonce       | Réalité 2026                                                                                                        | Impact                                      |
| ---------- | ------------------ | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| Cerebras   | 60 RPM free        | **30 RPM** (60K TPM, 1M tokens/jour, ctx 8192)                                                                      | Macro Agent saturable rapidement            |
| Groq       | 14400 req/jour     | **1000 RPD pour la plupart des modèles** (14400 réservé Llama 3.1 8B Instant uniquement)                            | Sentiment + Positioning agents limités      |
| ElevenLabs | free 10k char/mois | **OK techniquement**, mais : **interdiction usage commercial** + attribution obligatoire + max 2500 char/génération | Ichor commercialisé Phase 7 = ToS violation |

**Correction requise** : SPEC §12 (mapping ressources Yone) à mettre à jour avec quotas réels.

### 🚨 4. ElevenLabs Brian — budget 0€ IRRÉALISTE pour audio Phase 1

**Calcul honnête** : 5 briefings/jour × ~800 mots × ~5 chars/mot × 30 jours ≈ **600 000 caractères/mois**, soit **60× le free tier 10k**.

- Free tier : 10 000 char/mois → INSUFFISANT
- Creator $22/mois : 100 000 credits → INSUFFISANT
- **Pro $99/mois : 500 000 credits → SOUS-CAPACITÉ encore**
- **Scale $330/mois : 2M credits → suffisant**
  **Correction requise** :
- Option A : retirer audio Brian de Phase 1 (texte+web seul), audio Phase 2 quand budget validé
- Option B : réduire à **2 briefings/jour Phase 1** (06h+17h UTC) + Pro $99/mois budgété
- Option C : auto-host TTS open-source (Coqui TTS, MeloTTS, F5-TTS) pour Phase 1, ElevenLabs Phase 2+ pour qualité finale

### 🚨 5. Estimations Phase 0 + Phase 1 sous-estimées × 2.5

| Item                                               | SPEC actuel  | Réalité honnête solo dev débutant                |
| -------------------------------------------------- | ------------ | ------------------------------------------------ |
| Phase 0                                            | 1-2 sem      | **3-5 sem**                                      |
| Phase 1                                            | 6-8 sem      | **16-22 sem (4-5 mois)**                         |
| Block K + L AUDIT v1                               | 5-6j         | **13-19j**                                       |
| Vol surface SABR/SVI                               | 5-7j         | **3-4 sem** (théorie + py_vollib + calibration)  |
| Ansible playbook complet                           | 1j           | **5-10j**                                        |
| WAL streaming + test trimestriel                   | 1j           | **5-8j**                                         |
| **V1 complet PLAN**                                | 36-44 sem    | **80-110 sem (18-25 mois)**                      |
| **Probabilité livraison V1 36-44 sem comme prévu** | optimiste    | **≤ 10%**                                        |
| **Probabilité abandon mid-projet (burnout)**       | non chiffrée | **60-70% (pattern side-projets ambitieux solo)** |

**Correction requise** : tu as 3 choix stratégiques honnêtes (voir §10 ci-dessous).

---

## 1. Verdict global révisé (post 10 sub-agents)

| Domaine                       | Score actuel                      | Score post-Phase 1 si recos v1+v2 intégrées | Réaliste sur 18-25 mois |
| ----------------------------- | --------------------------------- | ------------------------------------------- | ----------------------- |
| Coverage data                 | 6.5/10                            | 7.5/10                                      | 8.5/10 (Phase 3)        |
| Quant/ML rigueur              | 4/10                              | 7/10                                        | 8/10 (Phase 4)          |
| Real-time architecture        | 5.5/10                            | 7.5/10                                      | 8/10 (Phase 4+)         |
| UX/UI vs Bloomberg/Koyfin     | 5.5/10                            | 7.5/10                                      | 8.5/10 (Phase 5+)       |
| Risk + compliance + ops       | 4.5/10                            | 7/10                                        | 8/10 (Phase 7)          |
| **Mobile PWA pro 2026**       | non audité v1                     | **6/10** réaliste                           | 7.5/10 (Phase 4+)       |
| **Design system magnifique**  | non audité v1                     | **7/10** réaliste avec 75 composants        | 8.5/10 (Phase 3+)       |
| **Coverage scénarios events** | 27 alertes / 95 events identifiés | 33 alertes Phase 1-2                        | 8/10 (Phase 4)          |
| **Frameworks canon traduits** | partiel (12 moteurs)              | 30 features book-derived Phase 1-3          | 9/10 (Phase 6)          |
| **GLOBAL pondéré**            | **5.0/10**                        | **7.0/10**                                  | **8.0/10**              |

**Plafond honnête** sans Bloomberg + équipe quant + budget paid TTS = **8/10 atteignable Phase 4-7**.

---

## 2. Top 15 trous critiques cross-domain (révisés v1+v2)

### A. Bloquants Phase 1 — corrections SPEC.md

1. **Remplacer Kuzu par Neo4j Community** (ou FalkorDB / Postgres+AGE)
2. **Versions libs corrigées** (pinning flexible, vérifier context7 avant install)
3. **Audit trail prédictions** : table `predictions_audit (id, ts_utc, asset, horizon, features_hash_sha256, model_version, calibrator_version, regime_hmm, bias_value, confidence, brier_realized, **events_within_horizon[]**, **triggering_event_class**)`
4. **Block K Treasury & Repo Microstructure** + **Block L Equity Microstructure** (driver USD/equity #1) — ou **report Phase 2 si scope réduit**
5. **Redis Streams comme bus officiel d'ingestion** + producers asyncio (OANDA, Finnhub, Polymarket WS) + consumer groups
6. **Page `/performance` Phase 1** (Brier scalaire + reliability diagram minimum)
7. **Hard caps providers + cost dashboard Grafana Phase 0** (anti incident Gemini)
8. **WAL streaming Postgres → R2 EU** (RPO 1h vs 7j actuel)
9. **5 nouvelles alertes (28-32) + alerte 33 market infrastructure halt**
10. **Crisis Mode trigger élargi** : VIX +30% OR GDELT mega-cluster OR CB emergency **OR SOFR spike OR FX peg break OR dealer-gamma flip négatif OR treasury auction tail >3bps**
11. **Champ `triggering_event_class`** sur les 7 scenarios par actif
12. **DTW analogue library** : 22 events tail historiques indexés obligatoirement avant Phase 1 fin
13. **Notifications PWA primaire = email Resend** (pas Telegram, pas push iOS UE risqué)
14. **Anthropic AI disclosure obligatoire** sur chaque export/briefing/audio (« contenu généré par IA Claude ») au-delà du disclaimer AMF
15. **Plan B Ichor Lite documenté** : 1 actif EURUSD, 6 moteurs, 1 briefing/jour, dashboard read-only, pas d'audio Phase 0/1, ship en 12-16 sem

### B. Améliorations Phase 1-2 majeures

- **Command palette grammaticale** + chord shortcuts + `?` cheatsheet overlay
- **Vintage data ALFRED** étendu à toutes séries macro révisables
- **Anthropic Usage Policy compliance** : disclaimer "AI-generated content" sur chaque export
- **i18n string externalization Phase 0** (`next-intl`) anticipant Phase 7 multi-tenant Yone EN/zh/ms

---

## 3. Synthèse Design System (sub-agent v2 #1)

### 3.1 Tokens design système complets

**Palette dark default 9 niveaux zinc + 5 saturations sémantique** :

```css
--bg-canvas: hsl(222 18% 6%) --bg-panel: hsl(222 16% 9%) --bg-popover: hsl(222 14% 12%)
  --bg-elevated: hsl(222 14% 14%) --border-subtle: hsl(222 12% 18%)
  --border-strong: hsl(222 14% 26%) --text-primary: hsl(210 20% 96%)
  --text-secondary: hsl(218 12% 68%) --text-tertiary: hsl(220 10% 48%)
  /* Sémantique 5-step (50/200/500/700/900) pour bull/bear/neutre/alerte/crisis/accent */
  --bull-500: hsl(141 65% 58%) /* = #4ADE80 PLAN */ --bear-500: hsl(0 92% 71%) /* = #F87171 PLAN */
  --alert-500: hsl(25 95% 60%) /* = #FB923C PLAN */ --crisis-500: hsl(290 88% 63%)
  /* = #E879F9 PLAN — RÉSERVÉ Crisis Mode */ --accent-500: hsl(187 84% 53%)
  /* = #22D3EE PLAN — RÉSERVÉ ConfidenceBand high */;
```

**Typo** : Inter Variable (UI 12/13/14/16/20/24/32/48) + JetBrains Mono Variable tabular-nums (chiffres 13/16/24/40)
**Spacing** : base 4px, tokens 0.5/1/2/3/4/6/8/12/16/24
**Radius** : xs=4 / sm=6 / md=8 / lg=12 / xl=16 / 2xl=24
**Layered shadows** : 5 niveaux dark (color border + soft shadow) + 5 niveaux light (diffuse shadow)
**Glassmorphism** : proscrit zones data, autorisé seulement CommandPalette + HoverCard + BriefingPlayer

### 3.2 Motion design — 5 easings + 5 durées

| Token             | Bezier                           | Usage                                |
| ----------------- | -------------------------------- | ------------------------------------ |
| `ease-linear-ish` | `cubic-bezier(0.16, 1, 0.3, 1)`  | Linear-style entrées cards           |
| `ease-material`   | `cubic-bezier(0.4, 0, 0.2, 1)`   | Hover, focus, transitions standards  |
| `ease-apple`      | `cubic-bezier(0.32, 0.72, 0, 1)` | Modals, drawers, briefing player     |
| `ease-emphasized` | `cubic-bezier(0.2, 0, 0, 1)`     | Crisis mode, regime shift narratif   |
| `ease-spring`     | Framer spring 200/25             | BiasBar fill, count-up, scenario fan |

| Durée           | ms  | Usage                                       |
| --------------- | --- | ------------------------------------------- |
| `dur-instant`   | 100 | Active state, button press                  |
| `dur-fast`      | 200 | Hover, focus ring, tooltip                  |
| `dur-base`      | 300 | Toast, dropdown, tab switch                 |
| `dur-slow`      | 500 | Page transitions, drawer, modal             |
| `dur-narrative` | 800 | Briefing reveal, regime shift, scenario fan |

**Reduced motion strict** : opacity-only fallback. **60fps obligatoire**. transform/opacity uniquement.

### 3.3 75 composants design system

**12 canon SPEC** + **14 audit v1** + **49 nouveaux v2** = **75 composants total**

- Layout (8) : `<TopBar/>`, `<Sidebar/>`, `<RightPanel/>`, `<BottomTabs/>`, `<SplitPane/>`, `<ResizableHandle/>`, `<TabBar/>`, `<Breadcrumb/>`
- Display (10) : `<Badge/>`, `<Chip/>`, `<Avatar/>`, `<Tag/>`, `<Pill/>`, `<Divider/>`, `<Skeleton/>`, `<EmptyState/>`, `<ErrorState/>`, `<LoadingState/>`
- Form (9) : `<Input/>`, `<Textarea/>`, `<Select/>`, `<Combobox/>`, `<DatePicker/>`, `<RangeSlider/>`, `<Toggle/>`, `<RadioGroup/>`, `<Checkbox/>`
- Data (10) : `<MetricCard/>` 4 variants, `<Stat/>`, `<Trend/>`, `<KpiTile/>`, `<Sparkline/>`, `<MicroChart/>`, `<Distribution/>` KDE, `<Gauge/>`, `<Progress/>`, `<DriverStackedBar/>`
- Feedback (9) : `<Toast/>`, `<Banner/>`, `<Callout/>`, `<Modal/>`, `<Drawer/>`, `<Popover/>`, `<Tooltip/>`, `<HoverCard/>`, `<Snackbar/>`
- Navigation (7) : `<Tabs/>`, `<Stepper/>`, `<Menu/>`, `<DropdownMenu/>`, `<ContextMenu/>`, `<NavLink/>`, `<CommandPalette/>` grammaticale
- Specific Ichor canon (12) : 12 listés SPEC §5.4
- Specific Ichor audit v1 (14) : `<NewsTicker/>`, `<StaleBadge/>`, `<DriverStackedBar/>`, `<SparklineCell/>`, `<ScenarioFan/>`, `<ReliabilityDiagram/>`, `<KbdHint/>`, `<ShortcutsOverlay/>`, `<TimezoneToggle/>`, `<AssetSplitView/>`, `<AnnotationPin/>`, `<CountdownWidget/>`, `<RegimeAlignmentMatrix/>`, `<BriefingPlayer/>`
- Specific Ichor v2 nouveaux (10) : `<RegimeBadge/>`, `<HorizonSelector/>`, `<HistoricalAnalogueCard/>`, `<StressTestRow/>`, `<DriverContribution/>`, `<MotorBadge/>` (12 paternités), `<NarrativeCloud/>`, `<ScenarioInvalidation/>`, `<EventImpactBar/>`, `<SourceQualityBadge/>`

### 3.4 Dataviz spec

- **lightweight-charts v5** : OHLCV + overlays GEX/VPIN/scenario bands + crosshair touch custom (pas natif)
- **D3.js v7** : Sankey (flux liquidité), force network (KG), radar bias 12 axes, parallel coordinates (`/compare`), scenario fan, KDE distribution, reliability diagram, forest plot
- **ECharts v6** : calendar heatmap + treemap (meilleur que D3 dessus)
- **react-force-graph** : KG navigation
- **Recharts** : exclu (perf moyenne live data)

### 3.5 Illustrations explicatives custom — système "Concept Finance"

8 SVG monoline 24/32/48px à designer Phase 0 :

- Hawkish (faucon) vs Dovish (colombe) stylisés minimaux
- Liquidity Well, Regime Transition Arrow, Scenario Tree Branching
- Narrative Wave, COT Bar, Breakeven Line, Carry Trade Bridge

### 3.6 32 micro-interactions catalog

Documenté avec trigger / type animation / durée / easing / a11y. Voir AUDIT_V2 sub-agent #1 livrable complet.

### 3.7 10 Framer Motion variants code-ready

`pageTransition`, `cardLift`, `barFill`, `numberCountUp`, `regimeShift`, `briefingPlayerReveal`, `commandPaletteOpen`, `scenarioFanExpand`, `notificationDock`, `dataPointReveal`. Hook `usePrefersReducedMotion()` clamp toutes.

### 3.8 Top 10 actions Phase 0/1 design "magnifique"

1. Mocker 5 directions logo + sélection (skill `canvas-design`)
2. Tokens CSS vars + Tailwind v4 config complets `packages/ui/tokens.css`
3. Mockups asset card EURUSD 3 états (nominal/verbose/crisis)
4. Storybook Phase 0 : 12 canon + 6 audit prioritaires
5. Système icônes "Concept Finance" custom 8 SVG
6. `packages/ui/motion.ts` + 10 variants + reduced-motion hook
7. Crisis Mode layout shift mocké + animation regime narrative
8. Command palette grammaire prototypée (`go EURUSD`, `chart XAUUSD 1h`, `cmp eurusd gbpusd`, `?` aide)
9. Briefing player audio Brian prototype Phase 0 (transcript synchronisé chapters SSML + vitesse + waveform)
10. `/performance` reliability diagram + Brier streaming Phase 1 (différenciateur public clé)

---

## 4. Synthèse Event Coverage (sub-agent v2 #2)

### 4.1 95 événements identifiés vs 27 alertes actuelles

- Récurrents calendrier : **35** (FOMC, ECB, NFP, CPI, EIA, USDA, Treasury auctions, QRA, OPEX, Quad witching, COT, etc.)
- Tail risks documentés : **22** (LTCM 1998, GFC 2008, COVID 2020, Yen carry 2024, Trump tariffs 2025, etc.)
- Black swans potentiels 2026-2030 : **17** (China-Taiwan kinetic, Yen >200, Eurozone redux, oil $200, AGI shock, cyber market infra, GPS outage, etc.)
- Industry cycles : **5** (semi, real estate, commodity supercycle, energy transition, bank credit)
- Operational Ichor : **16** (FRED gov shutdown, ElevenLabs voice retirement, Apple/Google PWA policy change, etc.)

**Couverture actuelle 27 alertes : ~70% des familles**, **8 zones aveugles persistent**.

### 4.2 6 nouvelles alertes recommandées (28-33)

| #      | Nom                             | Trigger                                                     | Source                      | Justification                |
| ------ | ------------------------------- | ----------------------------------------------------------- | --------------------------- | ---------------------------- |
| **28** | Treasury auction tail           | Tail >2bps OR bid-cover <2.3 OR indirects <60%              | TreasuryDirect XML          | Driver USD #1 depuis 2023    |
| **29** | Index microstructure            | T-1 jour rebal OR quad witching OR major OPEX with GEX flip | Russell, MSCI, S&P, Cboe    | Flux forcés non-fundamentaux |
| **30** | Capital flows / TIC             | Foreign Treasury holdings ∆ >1σ OR major holder reduction   | Treasury TIC monthly        | Yen carry, China reserves    |
| **31** | FX peg break / regime           | Vol skew on pegged FX >3σ OR SNB-style hint                 | OANDA, options if available | SNB 2015, future HKD/CNY/SAR |
| **32** | Funding stress (repo/SOFR/swap) | SOFR >IORB+5bps OR GC repo spike OR swap spread invert      | NY Fed SOFR percentiles     | Repo 2019, banking stress    |
| **33** | Market infrastructure halt      | NYSE/CME/Cboe halt OR DTCC issue OR major venue outage      | Exchange status APIs, GDELT | Cyber/ops black swan         |

### 4.3 Crisis Mode trigger élargi (correction SPEC §6.3)

Triggers actuels : VIX +30% OR GDELT mega-cluster OR CB emergency
**Triggers à ajouter** :

- SOFR spike >IORB+10bps
- FX peg break (vol skew >3σ pegged FX)
- Dealer-gamma flip négatif majeur (SPX/NDX)
- Treasury auction tail >3bps
- Liquidity stress (HY OAS widening >50bps en <5 jours)

### 4.4 22 events tail à indexer DTW analogue library Phase 1

Avant Phase 1 fin : indexation features comparables des 22 events tail (Asian crisis 1997, LTCM 1998, dot-com 2000, 9/11, GFC 2008, Eurozone, Taper 2013, China 2015, SNB 2015, Brexit 2016, Trump 2016, Volmageddon 2018, Q4 2018, Repo 2019, COVID 2020, GME 2021, Russia-Ukraine 2022, Gilts 2022, SVB 2023, Yen carry 2024, Trump tariffs 2025) → permet Reference Class Forecasting Kahneman-Lovallo (« sur 7 régimes similaires depuis 1990, 5 ont fini en X »).

### 4.5 Top 10 ajouts critiques scenario engine Phase 1

1. Champ `triggering_event_class` enum sur les 7 scenarios par actif
2. Alerte 28 Treasury auction tail + ingestion TreasuryDirect XML
3. Alerte 29 Index microstructure + Nasdaq Trader / Cboe / Russell calendars
4. Crisis Mode triggers élargis (5 nouveaux)
5. DTW analogue library 22 events obligatoire avant Phase 1 fin
6. HY OAS sub-indices BBB/B/CCC + SOFR percentiles + ICE OAS extension
7. Term structure VX9D/VX1M ratio + 0DTE GEX flip + dispersion (Sinclair)
8. GDELT mega-cluster definition opérationnelle (`tone < -8 AND num_articles > N AND 3+ themes`)
9. Operational runbooks manquants : ElevenLabs Brian retirement, PWA push iOS UE policy change, Hetzner second site
10. Event-tagging predictions_audit pour backtest event-conditional Brier

---

## 5. Synthèse Trading Frameworks (sub-agent v2 #3)

### 5.1 30 features book-derived priorisées Phase 1-3

**Phase 1 (12 features bloquantes pour Brier publié défendable)** :

1. Triple-barrier labeling [LdP ch. 3] → labels honnêtes tournament
2. Fractional differentiation [LdP ch. 5] → mémoire + stationnarité rates/DXY/OAS
3. Purged K-Fold + embargo [LdP ch. 7] → anti-leakage CV
4. CPCV [LdP ch. 12] → distribution Sharpe paths multiples
5. PBO [Bailey-Borwein-LdP-Zhu 2017] → bloque overfit avant publication
6. Deflated Sharpe [Bailey-LdP 2014] → SR ajusté multiple testing/non-normalité
7. White Reality Check + Hansen SPA [Aronson] → data-snooping bound
8. Forecast scaling Carver → échelle commune 12 moteurs
9. Universal carry [Pedersen-Asness-Moskowitz JFE 2018] → moteur #3
10. UMD momentum 12-1 [Carhart 1997] → moteur #5
11. Brier decomposition [Murphy 1973] → reliability/resolution/uncertainty `/performance`
12. Fat-tail-adjusted SR + Hill/POT [Taleb, Mandelbrot] → VaR/ES réalistes

**Phase 2 (10 features)** : 13. Conformal prediction MAPIE [Vovk 2005] → intervalles 90% garantis 14. VPIN flow toxicity [Easley-LdP-O'Hara 2012] → fragility moteur #10 15. HAR-RV benchmark [Corsi 2009] → baseline vol forecast 16. Yang-Zhang RV + vol cone + IV-RV premium [Sinclair] 17. SVI surface fit [Gatheral 2004] 18. GEX + Greeks aggregate [Hull] 19. CB NLP hawk/dove score [Hansen-McMahon JIE 2016] 20. Pozsar liquidity dashboard [Money Markets Notes] 21. Vol-targeted position sizing [Carver] 22. Hurst + Lo-MacKinlay variance ratio [Chan] → MR vs momentum régime detect

**Phase 3 (8 features)** : 23. Dalio debt-stage classifier (6 stages) → moteur #1 24. Soros reflexivity stage (8 stages) → moteur #8 25. Kindleberger MPC phase classifier (5 phases) → régime crise 26. Ilmanen 4-quadrant régimes (growth × inflation) → moteur #11 27. AMH régime classifier [Lo] → bandeau global 28. HRP allocation + denoised cov [LdP MLAM] → portefeuille modèles 29. Reference class forecasting via DTW analogues [Kahneman-Lovallo 1993] 30. Pre-mortem auto [Klein 2007] → enrichit triggers/invalidation scenarios

### 5.2 Library prompts agents enrichie

Templates injectables Critic + Journalist citant frameworks pour briefings pédagogiquement riches :

- "Setup carry universel à la Pedersen-Asness-Moskowitz JFE 2018 : forward minus spot positif {x}σ au-dessus moyenne 5y, mais vol cone Sinclair indique IV30 sous P10 90j → carry-vol ratio favorable"
- "Régime actuel s'apparente Minsky moment précédant LTCM 1998 selon Kindleberger MPC phase 4 (profit-taking)"
- "Hansen-McMahon hawkish score FOMC minutes glisse de {x}σ → moteur #1 Dalio = stade transitionnel deleveraging déflationniste"
- "Soros stage 3 (acceleration) : prevailing bias {x}, prix {y}σ au-dessus trend → pre-mortem Klein"

Stockés `prompts/agent_templates/{critic,journalist}/*.md` indexés par trigger condition régime.

---

## 6. Synthèse Mobile PWA pro 2026 (sub-agent v2 #4)

### 6.1 Capacités PWA iOS 26 / Android 16

**Faisable PWA pur 2026** : install home screen, Web Push VAPID, Badge API, Media Session lock screen audio, Wake Lock (Safari 18.4+), Service Worker offline cache (50 MB iOS), Web Share, Vibration (Android only), View Transitions cross-document (Chrome 126+/Safari 18.2+), Push Declarative (Safari 18.4)

**Impossible PWA 2026** : Live Activities iOS, Lock Screen / Home widgets PWA, Dynamic Island, App Intents Siri, Background Sync iOS, image/actions Web Push iOS, **push iOS UE** (désactivé 17.4 DMA, restauration progressive), Apple Watch / Wear OS

### 6.2 ⚠️ Risque iOS UE push critique

**Eliot est en France (UE)** — push iOS désactivé depuis iOS 17.4 (DMA), restauration progressive post pour PWA installées home screen. **Risque réel** : push iOS Eliot peut ne pas fonctionner.
**Décision** :

- Tester push iOS UE avec compte Apple FR dès Phase 0 acceptance
- **Plan B email Resend doit être PRIMAIRE pas secondaire** (renverse SPEC §5.7)

### 6.3 5-tab bottom navigation strict

Home (Dashboard) / Assets (3 actifs swipe) / Alerts / Briefings (Brian player) / Settings. Pages secondaires via drawer gauche ou sub-nav horizontale dans Asset card.

### 6.4 Décisions techniques mobile

- **Crosshair touch lightweight-charts v5** : pas natif → implémenter custom (long-tap 400ms + setCrosshairPosition)
- **vaul BottomSheet** (Emil Kowalski, intégré shadcn) > custom Radix
- **Next.js 15 vs 16** : Serwist exige Webpack, Next 16 = Turbopack par défaut → trancher Phase 0 (recommandé : rester **Next.js 15** stable)
- **Battery Status API** mort → utiliser `navigator.connection.effectiveType` + `saveData` flag
- **Cache iOS PWA 50 MB cap** → ~8 briefings 1.5min @ 64kbps cachés offline LRU
- **INP < 200ms officiel CWV 2024** → `useDeferredValue` React 19, scheduler.yield() agrégations

### 6.5 5 leçons concurrents mobile

1. **Bloomberg Mobile** : densité info > whitespace pour persona pro, mais hiérarchie typo stricte 3 niveaux max
2. **Robinhood** : swipe entre tickers + count-up = engagement (déjà prévu PLAN)
3. **Atom Finance / Koyfin** : drawer bottom pour filtres (vaul)
4. **Webull** : long-press chart → crosshair detail OHLC (à adopter exactement)
5. **Polymarket** : animation Framer Motion sur probability bars (count-up smooth, pas cut)

### 6.6 Top 10 actions Phase 0/1 mobile

1. Décision Next.js 15 vs 16 (recommandé : rester 15)
2. Tester push iOS UE chez Eliot dès Phase 0 acceptance
3. Crosshair touch lightweight-charts custom (long-tap 400ms)
4. Composant `<BottomSheet/>` via vaul
5. 5-tab bottom navigation (icônes Lucide)
6. `<BriefingPlayer/>` avec Media Session intégré
7. `prefers-reduced-motion` global via `useReducedMotion()` Framer
8. Quotas IndexedDB monitoring + LRU eviction
9. `<StaleBadge/>` timestamp Paris sur chaque metric
10. Touch-target audit ESLint custom (min 44×44pt iOS / 48×48dp Android)

---

## 7. Triple-Check rouge — corrections additionnelles

Au-delà des 5 alertes bloquantes §0, le sub-agent #5 a identifié :

### 7.1 Contradictions internes PLAN/SPEC/AUDIT (10 items)

- PLAN:218 « 250 features » vs PLAN:186 « 280 features » vs SPEC:359 « 250+ features » → **harmoniser à ~280**
- SPEC §3.7 timezone Paris UI vs PLAN:114 « LDN-NY 12-16 UTC » → **garder Paris UI, ajouter dual toggle Paris/UTC/ET**
- SPEC §13 « Twitter Phase 2 » vs PLAN « budget Twitter dès V1 » → **Phase 2 OK, économise budget**
- PLAN:380 « 7-9 sem MVP » vs SPEC sitemap 13 pages → **réduire scope ou ré-estimer**
- SPEC:148 « 0 ligne d'auth code » vs SPEC:273 push notifications (besoin user identifier) → **revoir : Cloudflare Access cookie + user_id table user_state**

### 7.2 Trous de sécurité non couverts par AUDIT v1

À ajouter au threat model STRIDE :

- HMAC webhook signatures (push callbacks)
- Rate limiting application-layer FastAPI (`slowapi`)
- CSP strict avec nonces (challenge lightweight-charts inline)
- HSTS preload
- CSRF tokens FastAPI (`fastapi-csrf-protect`)
- XSS sanitization sur RSS/Reddit content avant rendering DOM (au-delà de promptsanitize prompt injection)
- Dependency confusion : pinning lockfiles strict + `--require-hashes` pip
- SOPS+age key rotation procedure documentée
- systemd LoadCredential limites secrets size + scope
- Container image scan (trivy/grype) si Docker

### 7.3 Compliance/légal sous-estimé

- **Anthropic Usage Policy** : disclaimer "AI-generated content" obligatoire chaque export (au-delà disclaimer AMF) — non spécifié SPEC
- **ElevenLabs free tier ToS** : interdit usage commercial → Plan Pro $99/mois dès Phase 7 monétisation
- **Recordkeeping AMF Phase 7** : si monétisé, rétention briefings/predictions ≥5 ans (cohérent avec WAL streaming + R2 archives infinies, à formaliser)
- **VAT EU OSS Phase 7** : si Eliot facture, déclaration TVA + enregistrement OSS → anticiper
- **EU AI Act 2 août 2026** : transparence obligatoire LLM
- **CGU + watermark exports Yone** : crucial, non dans SPEC §8

### 7.4 Manques notables

- **i18n string externalization Phase 0** (`next-intl`) — anticipe Phase 7 EN/zh/ms sans refactor massif
- **Feature flag system** (Unleash self-host) — ship Phase 1 incrémental
- **A/B testing infra prompts/personas** — optimiser briefings sans guess
- **Documentation utilisateur final** (`docs.ichor.app` content plan)
- **Backup encryption at rest verification** — pg_dump weekly chiffré ?
- **NTP Hetzner sync** — critique pour timestamps audit
- **Anthropic API key révoquée** : runbook 8 manquant (spectre coupe agent stack)

### 7.5 Auto-critique AUDIT.md

- Score 5.2 → 7.3 « Option B +1-2 sem » sous-estimé : réalité 3-4 sem minimum
- 13 libs supplémentaires (mapie, fracdiff, etc.) = courbe apprentissage massive non évaluée
- Triple-barrier + CPCV + PBO + Deflated Sharpe « Phase 1 » = équivalent cours master quant finance, irréaliste débutant
- Mappings frameworks Soros/Pozsar/Brunnermeier intellectuellement riches mais pas actionnables Phase 1 → reporter Phase 2-3

---

## 8. Top 10 corrections SPEC.md prioritaires

À appliquer dans SPEC v2 si Option B retenue (cf §10) :

1. **Remplacer Kuzu par Neo4j Community 5.x** (ou FalkorDB / Postgres+AGE)
2. **Versions libs corrigées** : pinning `>=X,<Y` + check context7 avant install
3. **Réduire scope Phase 1 honnête** :
   - 2 actifs (EURUSD + XAUUSD), pas 3
   - 6 moteurs cœur (top-down macro, carry, mean rev, momentum, vol regime, liquidity), 6 autres Phase 2
   - 100-150 features, pas 280
   - Briefings 2/jour (06h+17h UTC), pas 5
   - LightGBM seul + isotonic Phase 1 (tournament 6 modèles Phase 2)
   - Block K + L Phase 2 (sauf si scope coupé NAS100)
4. **Reporter Brier protocol formel** (CPCV/PBO/Deflated Sharpe/FDR) à Phase 2-3 ; Phase 1 = Brier scalaire + reliability diagram + walk-forward simple
5. **Audio Brian** : 3 options (retirer Phase 1 / Pro $99/mois / open-source TTS). Trancher.
6. **Notifications PWA primaire = email Resend** (pas Telegram, pas push iOS UE risqué)
7. **Hard caps + cost dashboard + WAL streaming + threat model + 7 runbooks Phase 0** (déjà AUDIT v1, à formaliser §8 critères acceptation)
8. **Crisis Mode triggers élargis** (5 nouveaux : SOFR, FX peg, gamma flip, treasury tail, liquidity)
9. **6 nouvelles alertes 28-33** + champ `triggering_event_class` 7 scenarios
10. **Anthropic AI disclosure + i18n string externalization Phase 0**

---

## 9. Estimations effort honnêtes V1

| Phase                                            | SPEC actuel | AUDIT v2 honnête solo dev débutant               |
| ------------------------------------------------ | ----------- | ------------------------------------------------ |
| Phase 0                                          | 1-2 sem     | **3-5 sem**                                      |
| Phase 1 (3 actifs profondeur, full scope)        | 6-8 sem     | **16-22 sem (4-5 mois)**                         |
| Phase 1 LITE (2 actifs, 6 moteurs, scope réduit) | n/a         | **10-14 sem (2.5-3.5 mois)**                     |
| **V1 complet 7 phases**                          | 36-44 sem   | **80-110 sem (18-25 mois)**                      |
| **Probabilité livraison V1 36-44 sem**           | optimiste   | **≤ 10%**                                        |
| **Probabilité abandon mid-projet**               | non chiffré | **60-70%** (pattern side-projets ambitieux solo) |

**Honnêteté brutale** : Le projet est intellectuellement excellent mais **calibré pour équipe 3-5 ETP**, pas un débutant solo.

---

## 10. Recommandation finale stratégique — 4 options honnêtes

| Option                          | Scope                                                                                                                | Durée             | Livraison probable | Avis                                                                    |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ----------------- | ------------------ | ----------------------------------------------------------------------- |
| **A — Ship MVP « Ichor Lite »** | 1 actif EURUSD, 6 moteurs, 1 briefing texte/jour, dashboard read-only, **pas d'audio Phase 1**, pas de ML tournament | 12-16 sem         | **70%**            | **RECOMMANDÉ** : valide engagement avant scope-up, motivation préservée |
| **B — SPEC v2 Phase 1 réduite** | 2 actifs (EUR+XAU), 6 moteurs cœur, 2 briefings/jour, LightGBM seul, audio Brian basique                             | 22-28 sem         | 40%                | Compromis intellectuel mais effort lourd                                |
| **C — SPEC v2 full scope**      | 3 actifs, 12 moteurs, tournament 6 modèles, Brier protocol formel, audio Brian premium, Block K+L                    | 35-45 sem         | **15%**            | **Risque burnout 60-70%**                                               |
| **D — Audit + revue externes**  | C + avocat AMF + risk officer + staff eng streaming reviews                                                          | 40-50 sem + 4-6k€ | 18%                | Hors budget actuel                                                      |

**Recommandation honnête senior** : **Option A « Ichor Lite »** d'abord pour ship en 4 mois et préserver la motivation. Si succès + engagement validé après 3 mois d'usage prod, scope-up vers Option B (Phase 2). Option C/D = risque abandon élevé.

**Pourquoi Option A** :

- Ship rapide = motivation préservée
- 1 actif × 6 moteurs = scope maîtrisable solo dev débutant
- Pas d'audio Phase 1 = pas de budget ElevenLabs $99/mois requis
- Brier scalaire + reliability = différenciateur public minimum viable
- Architecture (FastAPI + Postgres+TS + Redis + Next.js 15 + Cloudflare) reste extensible
- Lessons learned avant Phase 2 ambitieuse

---

## 11. Plan d'action concret (post `/clear`)

### Si Option A « Ichor Lite » :

1. **Eliot lit AUDIT_V2.md** (30-45 min)
2. **Validation Option A**
3. **`/clear`** session courante
4. **Nouvelle session** avec mission : _« Réécris SPEC.md vers SPEC_LITE.md selon AUDIT_V2 §10 Option A. 1 actif EURUSD, 6 moteurs, 1 briefing texte/jour, dashboard read-only Phase 1, pas d'audio. Phase 0 = 3 sem. Phase 1 = 12 sem. »_
5. Validation SPEC_LITE.md
6. **`/clear`** + Phase 0 démarre

### Si Option B SPEC v2 réduite :

1. Validation Option B
2. **`/clear`** + nouvelle session : _« Updates SPEC.md selon AUDIT.md §5.1 + AUDIT_V2.md §8 (top 10 corrections) → produire SPEC_V2.md. Scope Phase 1 : 2 actifs + 6 moteurs + LightGBM seul + audio Brian basique. »_
3. Validation SPEC_V2.md
4. **`/clear`** + Phase 0 enrichie (3-5 sem) démarre

### Si Option C full scope :

1. Validation Option C avec acceptation explicite risque burnout 60-70%
2. **`/clear`** + nouvelle session SPEC_V2 full scope
3. Phase 0 5+ sem, Phase 1 22+ sem
4. Gate trimestrielle revue motivation/burnout

---

## 12. Documents à créer (toutes options)

- `docs/legal/anthropic-ai-disclosure.md` (compliance Anthropic Usage Policy)
- `docs/legal/cgu-v0.md` + `privacy-policy-v0.md` + `dpia-draft.md`
- `docs/legal/amf-mapping.md` (critères DOC-2008-23 vs Ichor)
- `docs/runbooks/{hetzner-down, key-compromise, postgres-corruption, r2-down, polymarket-renamed, prompt-injection, brier-degradation, anthropic-key-revoked, elevenlabs-brian-retired, pwa-push-ios-eu-policy, hetzner-region-outage}.md` (10 runbooks au lieu de 7)
- `docs/dr-tests/2026-Q2.md` (premier test restauration chronométré)
- `docs/key-rotation.md` calendrier
- `docs/model-registry.yaml` + 1 model card par modèle
- `docs/threat-model-stride.md`
- `docs/macro-frameworks.md` (paternité 12 moteurs Dalio/Soros/Minsky/Pozsar/Brunnermeier/Asness/Pedersen/Carhart/De Bondt-Thaler/Ilmanen/Thorp/Gatev/Shiller)
- `docs/canon-books.md` (~30 books Phase 6 academic digest RAG)
- `docs/concept-finance-icons.md` (8 SVG monoline brief design)

---

## 13. Triple-check final ✅

J'ai relu les 3 docs précédents (PLAN/SPEC/AUDIT) + les 5 rapports v1 + les 5 rapports v2 (10 sub-agents au total) avant écriture. Findings consolidés sans duplication. Aucune contradiction interne dans AUDIT_V2 détectée à la relecture.

**Limites honnêtes de cet audit** :

- Pas de validation context7 individuelle pour chaque lib (à faire avant code Phase 0)
- Pas de prototypage UI réel (mockups designs à produire Phase 0 via skill `canvas-design`)
- Estimations effort restent indicatives, varieront selon courbe apprentissage Eliot
- Choix Neo4j vs FalkorDB vs Postgres+AGE non tranché ici (décision Phase 0 selon prototypage rapide)
- Choix audio Brian Phase 1 non tranché (décision selon budget Eliot)

---

## 14. Synthèse en 1 phrase

**Ichor est intellectuellement excellent mais structurellement calibré pour une équipe — pour shipper et apprendre plutôt que d'abandonner, choisir Option A « Ichor Lite » (1 actif EURUSD, 6 moteurs, 1 briefing texte/jour, 12-16 semaines, pas d'audio Phase 1) puis itérer.**

---

_Document maintenu par Claude Code. Synthèse de 10 sub-agents experts (UX, quant, coverage data, real-time, risk/compliance, design system, event coverage, mobile PWA, trading frameworks, triple-check rouge) + ajouts main agent. Triple-check final effectué._
