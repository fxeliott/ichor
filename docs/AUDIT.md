# AUDIT Ichor — synthèse senior multi-domaine

**Date** : 2026-05-02
**Auteur** : Claude Code (orchestration de 5 sub-agents experts) + ajouts main agent
**Référence amont** : [ICHOR_PLAN.md](./ICHOR_PLAN.md), [SPEC.md](./SPEC.md)
**Mandat** : audit critique honnête « qu'est-ce qui manque pour qu'Ichor soit le meilleur outil pré-trade institutionnel possible (hors AT) »

---

## 1. Verdict global

| Domaine | Score actuel | Score post-Phase 1 si recos intégrées | Plafond honnête atteignable solo dev 0€ |
|---|---|---|---|
| Coverage data & sources | **6.5/10** | 7.5/10 | 8.5/10 (Phase 3) |
| Quant/ML rigueur | **4/10** | 7/10 | 8/10 (Phase 4) |
| Real-time architecture | **5.5/10** (« partiellement ») | 7.5/10 | 8/10 (Phase 4+) |
| UX/UI vs Bloomberg/Koyfin | **5.5/10** | 7.5/10 | 8.5/10 (Phase 5+) |
| Risk + compliance + ops | **4.5/10** | 7/10 | 8/10 (Phase 7) |
| **GLOBAL pondéré** | **5.2/10** | **7.3/10** | **8.2/10** |

**Plafond 10/10 inatteignable** sans Bloomberg Terminal + CME DataMine + ICE Connect + équipe quant 5 ETP + bureau légal AMF dédié. C'est par construction du budget 0€ + solo dev.

**Honnêteté brutale** : le plan + spec actuels sont **au-dessus de 90% des retail tools** mais ont **3 trous structurels** qui empêchent d'atteindre le niveau institutionnel revendiqué :

1. **Le « plafond honnête Brier <0.20 »** est revendiqué **sans protocole d'évaluation hold-out** (CPCV, PBO, Deflated Sharpe, Reality Check). Tel quel, **non défendable** face à un risk officer SR 26-2.
2. **Treasury auctions / repo / equity microstructure / vol surface niveau pro** sont des moteurs n°1 du USD/rates/equity depuis 2023 — **absents** structurellement. Le plan compense par sentiment + macro top-down mais rate l'essentiel intraday.
3. **DR/BCP, model risk governance, audit trail prédictions** sont **inexistants**. En cas d'incident technique ou question régulateur AMF, **rien à montrer**.

Les 4 autres dimensions (UX, real-time, frameworks macro canon) sont **améliorables sans refonte** : ajouts ciblés.

---

## 2. Top 10 trous critiques cross-domain (par impact x effort)

### A. Bloquants Phase 1 (à intégrer SPEC.md avant code)

1. **Protocole d'évaluation Brier formalisé** *(quant)* : triple-barrier labeling + Purged K-Fold + embargo + CPCV (≥10 paths) + PBO + Deflated Sharpe + reality check vs baseline naïf + multiple testing FDR. **Sans ça, /performance = marketing.** Ref López de Prado *Advances in FML* ch. 3-7-12-14.

2. **Audit trail prédictions** *(risk)* : table `predictions_audit (id, ts_utc, asset, horizon, features_hash_sha256, model_version, calibrator_version, regime_hmm, bias_value, confidence, brier_realized_when_known)`. **Indispensable** pour défendre toute prédiction rétroactivement.

3. **Block K data « Treasury & Repo Microstructure »** *(coverage)* : QRA + auctions calendar (2y/5y/7y/10y/20y/30y/TIPS hebdo) + bid-to-cover/tail/stop-through + SOFR percentiles NY Fed + dealer positioning hebdo. **Driver USD/rates dominant depuis 2023 (Yellen issuance shift).** Effort 3-4j Phase 1 sem 2-3.

4. **Block L data « Equity Microstructure & Calendar »** *(coverage)* : index rebalancings (Russell/MSCI/S&P) + OPEX/quad witching + ETF flows daily (XLK/QQQ/SPY/SPDR Gold) + S&P 500 + Nasdaq 100 earnings calendar **complet** (pas 7 noms). Effort 2j.

5. **Redis Streams comme bus officiel d'ingestion** *(real-time)* : SPEC §3.3 + §3.4 à updater. Conventions `prices:oanda:eurusd`, `news:rss`, `sentiment:polymarket`, `events:macro:fred`. AOF `appendfsync everysec`. Producers asyncio par source streamable + consumer groups (`bias-cg`, `nlp-cg`, `archiver-cg`). Replace cron OAS 30min naïf par event-driven.

6. **WAL streaming Postgres → R2 EU bucket** *(risk)* : `pgbackrest` ou `wal-g`. Cible **RPO 1h** (vs 7j actuel via pg_dump weekly). Test restauration trimestriel chronométré commité `docs/dr-tests/`.

7. **Page `/performance` Phase 1** *(UX)* — pas Phase 2+ : Brier scores live + reliability diagram + ECE + hit rate by confidence bucket + worst calls explained + regime-conditional perf. **C'est le moat de confiance vs Koyfin/Atom qui ne publient JAMAIS leurs erreurs.**

8. **Hard caps providers + cost dashboard** *(risk)* : Anthropic API key backup monthly cap $50 + alerts 50/80/100% + ElevenLabs hard cap caractères + Cloudflare R2 alert >5GB + Hetzner traffic >10TB. **Non-négociable post-incident Gemini 2026-04 (95€ abusés).**

### B. Améliorations majeures Phase 1-2 (impactantes)

9. **Command palette grammaticale + chord shortcuts + cheatsheet `?`** *(UX)* : `go eurusd`, `chart spx 3m`, `cmp gold dxy`, `news fed`, `cal 2026-05-15`. Sans ça, Cmd+K reste un fuzzy-finder banal. Bloomberg-essentiel.

10. **Vintage data ALFRED + lineage point-in-time** *(quant)* : étendre la colonne `vintage_at` (déjà prévue pour OAS) à **toutes** séries macro révisables (GDP, NFP, CPI, NFP). Sans ça, look-ahead bias systématique sur révisions.

---

## 3. Liste exhaustive des gaps par domaine (référence)

### 3.1 Coverage data — gaps détaillés

**Critique Phase 1** :
- Treasury auctions cycle (TreasuryDirect API) — Block K
- SOFR percentiles NY Fed — Block K
- Index rebalancings + OPEX + quad witching — Block L
- ETF flows daily complet (XLK/QQQ/SPY/USO/UNG) — Block L
- S&P 500 + Nasdaq 100 earnings calendar complet (Nasdaq Trader CSV) — Block L
- 0DTE gamma flip level + dealer hedge flow — Block C upgrade
- SABR/SVI vol surface fitting (lib `py_vollib` + Gatheral SVI) — Block C upgrade
- Dispersion (NAS100 IV vs constituent IVs top 10) — Block C upgrade
- TIPS breakeven curve granularité 1Y/2Y/7Y/20Y/30Y (FRED `T7YIE`/`T20YIEM`/`T30YIEM`) — Block A étendu
- Term structure VX9D/VX1M ratio explicite (contango stress signal Sinclair) — Block C
- ICE BofA OAS sub-indices (BBB only, B only, CCC only) — Block A étendu

**Important Phase 2-3** :
- EM cross-region (CNY PBoC fix, Caixin PMI, Japan Tankan, BTP-Bund, OAT-Bund spreads)
- Sector rotation ETF (XLF/XLK/XLE/XLV/XLP/XLY/XLU/XLB/XLI/XLRE/XLC)
- NAAIM exposure index, ICI fund flows weekly (complète AAII/Sentix/ZEW déjà prévus)
- Securities lending rates / borrow fees (FINRA Reg SHO daily CSV + S3 freemium)
- 13D activist + Form 144 sales (EDGAR direct)
- AIS shipping raw (MarineTraffic free / VesselFinder free / AISHub académique)
- Sentinel-2 ESA Copernicus (oil tank Cushing imagery)
- Beneish M-score + Piotroski F-score + accruals (forensic accounting via 10-K)
- NY Fed Primary Dealer Statistics (XLS hebdo)
- FFIEC Call Reports (banques US trimestriel)
- OFR Financial Stress Index (proxy CISS US daily JSON)
- NY Fed Corporate Bond Market Distress Index (CMDI weekly)
- CME FedWatch tool (proxy implied Fed-cut prob, complémentaire Polymarket)

**Sources gratuites manquantes que TOUS les pros utilisent** :
- TreasuryDirect API XML (auctions)
- NY Fed SOFR percentiles JSON daily
- FINRA Reg SHO daily short sale CSV
- Nasdaq Trader earnings/IPO/secondary calendars CSV
- CBOE settlement values + expiration calendar CSV
- OFR Financial Stress Index daily JSON

**Risques sources actuelles du plan** :
- Polymarket Gamma API non-documenté officiellement → rate limit silencieux + breaking changes possible. Mitigation : cache local + fallback Kalshi + CME FedWatch.
- COT release vendredi 15:30 ET = 3j retard → ne pas surpondérer en horizons intraday.
- HY/IG OAS rolling 3 ans depuis avril 2026 → archivage J0 critique (déjà bien identifié SPEC §3.4) **mais étendre à TOUTES séries FRED critiques** (T5YIE, T10YIE, THREEFYTP10, SAHMREALTIME, USEPUINDXD).
- OpenInsider scraping fragile (pas d'API, parsing HTML cassable) → backup Quiver Free Visitor + sec-api.io 13F direct.
- Tradier free 5 req/jour FlashAlpha **insuffisant pour GEX intraday** — à requalifier ou plan payant accepté Phase 2.

### 3.2 Quant/ML rigueur — gaps détaillés

**Critique avant Phase 1** (sans ça, Brier publié non-défendable) :
- Triple-barrier labeling par actif×horizon (López de Prado ch. 3)
- Purged K-Fold avec embargo = max(horizon labels) (ch. 7)
- CPCV (Combinatorial Purged CV) génération N≥10 paths backtest (ch. 12)
- PBO < 0.5 sur tournament avant promotion (Bailey-Borwein-LdP-Zhu JCF 2017)
- Deflated Sharpe Ratio + PSR (Bailey-LdP J Portfolio Mgmt 2014)
- Walk-forward analysis (anchored vs unanchored, refit cadence)
- Reality Check (White) ou SPA test (Hansen) vs baseline naïf (random walk + carry FX, momentum 12-1 equities)
- Multiple testing correction (Bonferroni / FDR Benjamini-Hochberg) sur 6 modèles × 12 moteurs × 15 actifs × 3 horizons ~3000 strategies évaluées

**Probabilistic forecasting** :
- Reliability diagram + ECE + MCE par actif/horizon/régime (pas que Brier scalaire)
- CRPS (Continuous Ranked Probability Score) pour distribution 7 scenarios
- Pinball loss / quantile evaluation pour `<ConfidenceBand>`
- Conformal prediction (Vovk) via lib `mapie` (BSD-3) — standard distribution-free 2024-2026
- Comparaison calibration isotonic vs Platt vs beta vs spline (isotonic over-fit notoirement sur petits datasets)

**Feature engineering / data leakage** :
- Vintage ALFRED point-in-time pour TOUTES séries macro révisables (pas que OAS)
- Stationarity tests ADF, KPSS, PP avant tout modèle linéaire (lib `statsmodels`)
- Fractional differentiation (López de Prado ch. 5 ; lib `fracdiff` MIT)
- Feature selection : MRMR, Boruta, mutual information (sur 280 features × 12 moteurs, redondance massive)
- SHAP / PDP / ALE pour explainability (lib `shap` + `interpret` Microsoft InterpretML MIT) — sinon `<ContributionList />` non auditable
- Survivorship bias documenté (NAS100 mega-cap 7 noms = survivor-biased par construction)
- News timestamps avec publication delay réel (RSS Reuters timestamp ≠ tradeable timestamp — critique pour event studies)
- HAR-RV (Corsi 2009) + GARCH/EGARCH/GJR-GARCH (lib `arch` Sheppard) pour vol forecasting
- Copulas pour dépendance + EVT POT pour tails (lib `pyextremes` MIT) — nécessaire pour stress tests + crisis mode

**Model risk governance (SR 26-2 inspired)** :
- Tier per model (Tier 1 critique HMM + aggregator, Tier 2 secondaire tournament 6, Tier 3 LLM agents Langfuse-only)
- Lifecycle gates écrits : dev → validation → deploy → monitor → retire
- Champion/challenger discipline avec shadow window N=20 jours min avant promotion
- PSI (Population Stability Index) + KS test sur features et prédictions (lib `evidently` Apache 2.0)
- Model card par modèle (Mitchell et al FAccT 2019)
- Datasheet par dataset (Gebru et al 2021)
- Revue trimestrielle écrite signée (commit `docs/model-reviews/`)
- Experiment tracking (lib `mlflow` Apache 2.0 ou `aim`)
- Distinction retrain (refit features) vs recalibrate (isotonic only) — triggers explicites

**Libs additionnelles obligatoires à ajouter à SPEC §3.5** :
- `mapie` (BSD-3) — conformal prediction
- `fracdiff` (MIT) — fractional differentiation
- `properscoring` ou `scoringrules` — CRPS/pinball/energy score
- `arch` — GARCH family + HAR-RV
- `statsmodels` — ADF/KPSS/cointegration
- `shap` + `interpret` (MIT) — explainability
- `mlflow` ou `aim` (Apache 2.0) — experiment tracking
- `feast` (Apache 2.0) — feature store si scaling Phase 2+
- `evidently` (Apache 2.0) — PSI/KS drift dashboards
- `dowhy` + `econml` (MIT) — causal inference (CBN mentionné plan)
- `pyextremes` (MIT) — EVT POT pour tails
- `py_vollib` + SVI Gatheral — vol surface fitting

### 3.3 Real-time architecture — gaps détaillés

**Verdict honnête** : « tout temps réel tout le temps » est **physiquement impossible** pour macro (FRED daily, EIA weekly, NBER PDF). Pour ticks prix + Polymarket + news ingestion, c'est **faisable et différenciant**.

**Refonte recommandée** : **hybride autour de Redis Streams** (déjà en stack), pas Kafka/Flink/Materialize.

**Architecture cible** :
```
producers asyncio (par source) ─XADD→ Redis Streams (per-source key)
                                           │
                                           ▼ XREADGROUP consumer-groups
                       ┌───────────────────┼──────────────────┐
                       ▼                   ▼                  ▼
                feature-builders     news-nlp/cb-nlp     bias-aggregator
                (rolling, GEX,       (FinBERT, Haiku,    (regime-aware,
                 VPIN, corrs)         sanitize)           Brier-weighted)
                       │                   │                  │
                       └─── Postgres+TimescaleDB (hypertables, cont. agg) ──┘
                                           │
                              LISTEN/NOTIFY on table updates
                                           │
                                           ▼
                              FastAPI WebSocket fan-out
                                           │
                                           ▼
                           Next.js (TanStack Query subscribe)
```

**Cartographie sources** :
| Source | Stream gratuit ? | Latence cible | Mécanisme |
|---|---|---|---|
| OANDA prix | Oui (HTTP stream chunked) | <500ms | Stream → Redis Stream `prices:oanda` |
| Finnhub WS | Oui (free 50 symbols) | <500ms | WS → `prices:finnhub` |
| Polymarket | Oui (`wss://ws-subscriptions-clob.polymarket.com`) | <1s | WS → `sentiment:polymarket` |
| Tradier options | Streaming = paid (sandbox 15min delay free) | 30-60s | Polling REST 1/min |
| Reddit | REST 100/min | 30-60s | Polling adaptatif |
| FRED/EIA/ECB | REST seul | 5-15min après publication | Polling cron aligné release calendar |
| RSS | Atom polling | 1-5min | Polling 60-120s |
| GDELT | Pseudo-stream 15min | 15min | Polling 15min |

**Latency budgets réalistes** (single-user prod Hetzner) :
- Tick FX OANDA → UI : **<500ms p95**
- Polymarket move → alert UI : **<1s p95**
- News RSS → alert UI : **<2min p95**
- FRED CPI release → impact biais : **<60s p95**
- Crisis Mode briefing audio dispo : **<2min**

**Risques temps-réel sous-estimés** :
- Pas de DLQ ni replay → perte silencieuse possible (XPENDING + XCLAIM répare)
- Backpressure si Polymarket spike 10k msg/s → consumer groups + decouplage
- Heartbeat OANDA stream non spécifié (stale stream silencieux)
- Redis durabilité : default RDB only → activer **AOF `appendfsync everysec`**
- TimescaleDB continuous aggregates lag (refresh policies ≠ temps réel)
- Polymarket WS limite 5 connexions/IP
- Cloudflare WS idle timeout 100s → keepalive ping front obligatoire

**SLO temps-réel à formaliser** dans SPEC nouvelle §3.10 : `stream_lag_seconds`, `consumer_pending_count`, `producer_reconnects_total` exposés Prometheus + dashboards Grafana.

### 3.4 UX/UI — gaps détaillés

**Bloquants Phase 1** :
- Command palette grammaticale (verb subject modifier) — `go {symbol}`, `chart {symbol} {tf}`, `cmp {a} {b}`, `news {topic}`, `cal {date}`, `?` aide
- Function-key chord shortcuts spécifiés (`e e` → EURUSD, `x a u` → XAUUSD, `g k` → goto knowledge graph) + cheatsheet `?` overlay
- Stale data badge couleur + tooltip "last update HH:MM Paris (Xmin ago)" sur **chaque** metric
- Confidence band visualisation contractualisée (gradient ? IQR shaded ? scenario fan ?)
- Asset card progressive disclosure (12 moteurs collapsed = bias + weight + 1-line ; expanded = features + sparkline + sources)
- Driver decomposition stacked bar (chaque moteur = segment proportionnel à |contribution|, signé couleur)
- Dual-timezone toggle Paris/UTC/ET footer card (pour cohabitation avec workflow Londres/NY)
- Crisis Mode UI layout shift détaillé (quels widgets remontent, lesquels masqués, animation)
- Empty/loading skeletons par carte avec last-update badge

**Composants à AJOUTER design system (au-delà des 12 actuels)** :
- `<CommandPalette />` avec grammaire (au-delà de cmdk brut)
- `<NewsTicker />` marquee top-bar + click → assets impactés
- `<StaleBadge />` timestamp + couleur fresh/stale/dead
- `<DriverStackedBar />` décomposition signée 12 moteurs
- `<SparklineCell />` mini-chart 30j inline
- `<ScenarioFan />` arbre temporel 7 scenarios + proba bands (Polymarket meets Metaculus)
- `<ReliabilityDiagram />` calibration plot pour `/performance`
- `<KbdHint />` + `<ShortcutsOverlay />` (`?` overlay GitHub/Linear pattern)
- `<TimezoneToggle />` ou `<DualTimeRow />`
- `<AssetSplitView />` split-screen 2-4 cards comparées
- `<AnnotationPin />` note datée persistée carte/chart
- `<CountdownWidget />` T-minus prochain event high-impact
- `<RegimeAlignmentMatrix />` grille assets × régime
- `<BriefingPlayer />` audio Brian + transcript synchronisé + chapters SSML + vitesse

**Pages à AJOUTER au sitemap** :
- `/performance` **dès Phase 1** (pas Phase 2+)
- `/replay` (Phase 3+) time-travel slider + saved snapshots
- `/compare?a=eurusd&b=gbpusd` split asset cards
- `/search` résultats universels Cmd+K
- `/shortcuts` cheatsheet keyboard chords
- `/news` feed brut + filtres + impact mapping
- `/journal` annotations agrégées par asset (léger, pas trader journal)
- `/onboarding` Phase 7 multi-tenant — scaffolder dès Phase 1 placeholder

**Top 5 features différenciantes vs Koyfin/Atom** :
1. Calibration publique live (`/performance` reliability + Brier streaming) — Koyfin/Atom ne publient JAMAIS leurs erreurs
2. Briefings audio FR Brian + transcript synchronisé + chapters SSML — pipeline ElevenLabs avec lexique phonétique custom unique
3. Driver decomposition transparente 12 moteurs + sources cliquables jusqu'à donnée brute
4. Scenario tree probabilisé 7 paths + triggers + invalidation
5. Crisis Mode reorganisation auto du dashboard — aucun concurrent grand public ne fait de layout shift conditionnel

### 3.5 Risk + compliance + ops — gaps détaillés

**Critique avant Phase 1 prod** :
- Model inventory (`docs/model-registry.yaml`) + 1 model card par modèle (HMM, isotonic, 6 tournament, aggregator)
- Table `predictions_audit` pour reproducibilité point-in-time
- Threat model STRIDE écrit
- MFA hardware key (YubiKey) sur Cloudflare/Hetzner/GitHub/Anthropic
- Dependabot + pip-audit + npm audit dans CI
- Cloudflare R2 bucket **`eu` jurisdiction obligatoire** (irreversible après création)
- WAL streaming Postgres → R2 (RPO 1h vs 7j actuel)
- Test restauration trimestriel chronométré commit `docs/dr-tests/`
- Account recovery printout papier (Cloudflare/Hetzner/GitHub/Anthropic) cold storage
- Hard caps providers + cost dashboard Grafana (anti-incident Gemini 2026-04)
- AOF `appendfsync everysec` Redis (sinon crash = perte messages non consommés)

**Model risk governance (SR 26-2, 17 avril 2026)** :
- Tier per model (1/2/3 selon matérialité)
- Lifecycle gates documentés
- Champion/challenger shadow window N≥20j avant promotion
- PSI/KS test formels sur features + prédictions
- Continuous monitoring thresholds **calibrés** (pas 0.25 arbitraire — référencer baseline naïve 3-class ≈ 0.222)
- Annual review formelle = revue trimestrielle écrite signée pour solo dev

**AMF / juridique France** :
- **Critère décisif** = recommandation **personnalisée** sur instrument **précis identifié** (Position DOC-2008-23). Ichor = biais par actif identifié → le caractère **non personnalisé** est l'unique rempart, doit être **technically enforced**.
- **Risque glissement** Phase 7 si annotations perso, watchlists user-specific, alertes config par user → bascule potentielle vers conseil. Séparation stricte « contenu identique pour tous » vs « préférences UI cosmétiques ».
- **Disclaimer seul ne suffit pas** : ajouter (i) CGU signées au modal initial avec horodatage + IP + hash, (ii) mention « non-CIF, non-PSI » footer, (iii) **NE PAS publier de performances historiques** sans track record audité (plus prudent V1).
- **Republication Yone** : si Eliot screenshot + diffuse à Yone, devient diffuseur → risque qualification CGP/démarchage. **Watermark utilisateur sur exports + interdiction CGU.**
- **Phase 7 Malaisie** : Eliot opérateur français → AMF reste compétente sur l'éditeur. Si users MY → CMSA framework + LASR potentiellement applicable. Avocat MY indispensable **dès le scaffold Phase 7 démarre**, pas 2-3 mois avant.
- **Documents juridiques** à rédiger : CGU + Politique de confidentialité + DPIA draft + mention non-CIF/non-PSI — **avocat fintech AMF (~500-1500€) avant ouverture multi-tenant Phase 7**.

**GDPR Phase 7 prérequis** :
- DPIA obligatoire (art. 35) car traitement automatisé pouvant influencer décisions financières
- Registre des traitements (art. 30) à initier dès Phase 0
- Right to be forgotten process documenté
- DPA à signer avec : Cloudflare, Hetzner, ElevenLabs, Anthropic, Groq, Cerebras, HuggingFace
- Sub-processors register public Phase 7
- Schrems II / TIA pour Anthropic, Groq, Cerebras, ElevenLabs (US transferts)

**DR / RPO/RTO cibles** :
| Composant | RPO cible | RTO cible | Gap actuel |
|---|---|---|---|
| Postgres OAS archive | 30min | 4h | OK si WAL streaming |
| Postgres features/predictions | 1h | 4h | **WAL streaming absent** |
| R2 archives | 24h | 24h | OK (sync hebdo, bumper daily) |
| Cloudflare Pages | 0 (idempotent) | 1h | OK |
| Hetzner serveur | N/A | 24h | **Pas de second Hetzner ni Oracle Free chaud** (déjà dispo `ICHOR_PLAN.md:474`) |

**Cost monitoring (anti incident Gemini)** :
- Anthropic backup key monthly cap $50 + alerts 50/80/100%
- ElevenLabs hard cap caractères/mois
- Cloudflare R2 alert >5GB stockage ou >1M class-A ops
- Hetzner alert traffic >10TB/mois
- Daily cost dashboard Grafana via Anthropic Usage API + Cloudflare Billing API + Hetzner Robot API
- Kill switch automatique si cap atteint
- Rotation policy 90j calendrier `docs/key-rotation.md`

**7 incident runbooks à créer Phase 0** :
1. Hetzner injoignable
2. Clé API compromise
3. Postgres corruption
4. R2 inaccessible (incident Cloudflare)
5. Polymarket API renamed/deprecated
6. Prompt injection détecté en prod
7. Brier score hors seuil 60j

---

## 4. Mes ajouts (angles non couverts par les 5 sub-agents)

### 4.1 Frameworks macro canon à mapper aux 12 moteurs

Les 12 moteurs actuels sont pertinents mais gagnent à être nommés par leurs paternités intellectuelles, ce qui structure la pédagogie + le knowledge base + la légitimité auprès d'un user pro :

| Moteur Ichor | Paternité intellectuelle | Concept clé | Reference book |
|---|---|---|---|
| Top-down macro (#1) | **Ray Dalio** Big Cycle | Long-term debt cycle, productivity, internal/external order | *Big Debt Crises* (2018), *Principles for Dealing with Changing World Order* (2021) |
| Liquidity-driven (#9) | **Zoltan Pozsar** Money Markets | Shadow banking, dollar funding, collateral, FX swaps | *Global Money Notes* series (Credit Suisse 2018-2022) |
| Liquidity-driven (#9) bis | **Hyman Minsky** | Hedge → speculative → Ponzi finance, Minsky moment | *Stabilizing an Unstable Economy* (1986) |
| Narrative-driven (#8) | **George Soros** reflexivity | Boom-bust feedback cognitive function ↔ price | *The Alchemy of Finance* (1987) |
| Narrative-driven (#8) bis | **Robert Shiller** | Narrative economics, viral stories drive markets | *Narrative Economics* (2019) |
| Vol-regime (#10) | **Markus Brunnermeier** | Liquidity spirals, fire sales, leverage cycle | *The I-Theory of Money* WP series, BIS lectures |
| Mean reversion (#4) | **AQR Asness** | Value, profitability, defensive (QMJ) | *Quality Minus Junk* (2013) |
| Carry (#3) | **Pedersen-Asness-Moskowitz** | Carry returns across asset classes | *Carry* (2018, J Financial Economics) |
| Momentum (#5) | **Carhart-Fama** + **Asness** | 12-1 month momentum equity, currency, commodity | *On Persistence in Mutual Fund Performance* (1997) |
| Contrarian (#6) | **De Bondt-Thaler** | Long-term reversal 3-5y | *Does the Stock Market Overreact?* (1985) |
| Cross-asset (#11) | **Antti Ilmanen** | Risk premia harvesting, regime conditioning | *Expected Returns* (2011), *Investing Amid Low Expected Returns* (2022) |
| Pairs/RV (#12) | **Ed Thorp** + **Gatev-Goetzmann-Rouwenhorst** | Statistical arbitrage convergence | *Beat the Market* (1967), *Pairs Trading* (RFS 2006) |

**Action** : enrichir SPEC §4 « Architecture multi-agent » avec un tableau de paternité par moteur. Ça aide aussi le Critic agent à challenger le model en référençant des frameworks établis.

### 4.2 Books canon à indexer dans le knowledge base academic digest (Phase 6)

Pour la Phase 6 « Recherche académique synthesizer » du plan original, le pipeline RAG doit indexer les **books canon trading systématique** suivants (chunks + embeddings, recherche sémantique) :

**Trading systématique & ML quant** :
- López de Prado, *Advances in Financial Machine Learning* (Wiley 2018)
- López de Prado, *Machine Learning for Asset Managers* (Cambridge 2020)
- López de Prado, *Causal Factor Investing* (Cambridge 2023)
- Carver, *Systematic Trading* (Harriman House 2015)
- Chan, *Quantitative Trading* (Wiley 2008) + *Algorithmic Trading* (Wiley 2013)
- Aronson, *Evidence-Based Technical Analysis* (Wiley 2006) — méta sur biais

**Volatilité & options** :
- Hull, *Options, Futures, and Other Derivatives* (10th ed) — bible
- Natenberg, *Option Volatility & Pricing* (2nd ed)
- Sinclair, *Volatility Trading* (2nd ed) + *Option Trading*
- Gatheral, *The Volatility Surface* (Wiley 2006)
- Rebonato, *Volatility and Correlation* (Wiley 2nd ed)

**Macro & risk premia** :
- Ilmanen, *Expected Returns* (2011) + *Investing Amid Low Expected Returns* (2022)
- Dalio, *Principles for Dealing with the Changing World Order* (2021) + *Big Debt Crises* (2018)
- Cochrane, *Asset Pricing* (2005)
- Pedersen, *Efficiently Inefficient* (Princeton 2015)

**Comportements de marché** :
- Lo, *Adaptive Markets* (Princeton 2017)
- Bookstaber, *A Demon of Our Own Design* (2007) + *The End of Theory* (2017)
- Soros, *The Alchemy of Finance* (1987)
- Shiller, *Narrative Economics* (2019)
- Mandelbrot, *The (Mis)Behavior of Markets* (2004)
- Taleb, *Dynamic Hedging* (1997) + *Statistical Consequences of Fat Tails* (2020)

**Forecasting & cognition** :
- Tetlock, *Superforecasting* (2015)
- Mauboussin, *More Than You Know* (2006) + *The Success Equation* (2012)
- Silver, *The Signal and the Noise* (2012)

**Méta / classique** :
- Schwager, *Market Wizards* series
- Kindleberger, *Manias, Panics, and Crashes* (8th ed)

**Action Phase 6** : pipeline `academic-digest` ingère ces ~30 books + arXiv q-fin + NBER + Fed FEDS + BIS WP + IMF WP + ECB WP + SSRN q-fin → embeddings (OpenAI proscrit ; alternative : `bge-large-en-v1.5` ou `nomic-embed-text-v1.5` HF gratuits) → Kuzu graphe (déjà SPEC §3.3) + recherche sémantique pour Critic + Journalist agents qui peuvent référencer livres pendant briefings.

### 4.3 Research feeds publics gratuits manquants

À ajouter au Block G news/academic (Phase 1-2) :
- **Pozsar Money Markets notes** (depuis indépendant post-CS) — substack si dispo
- **Macro Compass** (Alfonso Peccatiello) — substack
- **Bianco Research** — blog public partial
- **Renaissance Macro (RenMac)** — public excerpts
- **13D Research weekly** — partial public
- **Calculated Risk** (Bill McBride) — blog gratuit fondamentaux US housing/employment
- **The Macro Compass** déjà mentionné plan (`ICHOR_PLAN.md:138`)
- **Daily Speculations** (Niederhoffer héritage) — pour reflexivity perspectives
- **FT Alphaville free articles** — sélection
- **Marc to Market** (Marc Chandler) — FX framework
- **Brad Setser** CFR blog — flows globaux
- **Daniel Lacalle** — macro européen contrarian

### 4.4 Frameworks méthodologiques manquants au plan

- **Probability calibration training** Tetlock-style : Eliot devrait s'entraîner à donner des estimations probabilistes **avant** de lire Ichor → comparer convergence/divergence → Self-Reflection hebdo intègre cette boucle (super-forecaster discipline). Page `/calibration-training` Phase 5+.
- **Pre-mortem** sur chaque scenario (Klein 2007) : avant de produire 7 scenarios, agent simule « si scenario X se réalise dans 4 semaines, quels signaux on aurait dû voir today ? » → enrichit triggers/invalidation.
- **Reference class forecasting** (Kahneman-Lovallo) : pour chaque biais émis, trouver les 3-5 régimes historiques DTW les plus proches **avec leur outcome réalisé** → base rate explicite (déjà partiellement dans plan via DTW analogues, à expliciter).
- **Brier decomposition Murphy 1973** : reliability + resolution + uncertainty séparées sur `/performance`. Sharpness vs calibration tradeoff visible.

---

## 5. Plan d'action recommandé (priorité × effort)

### 5.1 Updates SPEC.md immédiates (avant Phase 0 démarre)

À ajouter aux sections existantes ou en sections nouvelles. Ordre de priorité :

1. **§3.5b nouvelle « Protocole d'évaluation Brier »** : triple-barrier + Purged K-Fold + embargo + CPCV + PBO + Deflated Sharpe + reality check + FDR. Bloquant Phase 1.
2. **§3.10 nouvelle « Real-time architecture & SLOs »** : Redis Streams bus, producers asyncio, consumer groups, AOF activé, LISTEN/NOTIFY, latency budgets, SLI/SLO Prometheus.
3. **§3.11 nouvelle « Model Risk Governance »** : tiers, model cards, model registry, champion/challenger shadow N=20j, retrain vs recalibrate triggers.
4. **§3.12 nouvelle « DR / BCP »** : RPO/RTO cibles, WAL streaming, R2 EU jurisdiction, test restauration trimestriel, account recovery printout, Oracle Free Tier en chaud.
5. **§3.13 nouvelle « Cost monitoring & guardrails »** : hard caps, alerts, kill switches, rotation 90j.
6. **§3.14 nouvelle « Audit trail prédictions »** : table `predictions_audit` schéma complet.
7. **§5 update « Composants design system »** : passer de 12 à ~26 composants (ajouter les 14 manquants identifiés).
8. **§5 update « Sitemap »** : ajouter `/performance` Phase 1, `/compare`, `/search`, `/shortcuts`, `/news`, `/journal`.
9. **§9 update « Sources Phase 1 priorisées »** : ajouter Block K (Treasury & Repo) + Block L (Equity Microstructure) + upgrade Block C (vol surface SABR/SVI + dispersion + 0DTE gamma).
10. **§3.5 update libs ML** : ajouter mapie, fracdiff, scoringrules, arch, statsmodels, shap, interpret, mlflow, evidently, dowhy, econml, pyextremes, py_vollib.
11. **§4 update « Architecture multi-agent »** : ajouter tableau paternité 12 moteurs (Dalio/Soros/Minsky/Pozsar/Brunnermeier/Asness/Pedersen/Carhart/De Bondt-Thaler/Ilmanen/Thorp/Gatev).
12. **§5.7 update « Notifications »** : préciser kill switch / DLQ / replay policy.
13. **§7 update « Edge cases »** : ajouter 7 scenarios (Hetzner injoignable, clé compromise, Postgres corruption, R2 inaccessible, Polymarket renamed, prompt injection prod, Brier hors seuil).
14. **§8 update « Critères acceptation Phase 0 »** : ajouter critères pour les nouveaux livrables (model registry, predictions_audit table, WAL streaming, cost dashboard, threat model STRIDE, YubiKey MFA, R2 EU bucket, account recovery printout).
15. **§13 update « Risques »** : retirer ce qui est résolu, ajouter SR 26-2 / EU AI Act compliance review trimestrielle.

### 5.2 Phase 0 enrichie (au-delà de SPEC §14)

**Semaine 1 — Infrastructure** (inchangée principalement) :
- Achat ichor.app Cloudflare Registrar **+ R2 bucket EU jurisdiction obligatoire**
- Backup Hetzner pre-wipe
- Wipe + Ubuntu 24.04
- Ansible playbook (avec Redis AOF activé, WAL streaming Postgres)
- Repo Turborepo init
- CI GitHub Actions verte **+ Dependabot + pip-audit + npm audit configurés**
- SOPS+age secrets
- Cloudflare Access **+ YubiKey MFA Cloudflare/Hetzner/GitHub/Anthropic**

**Semaine 2 — Foundation critique** :
- **Cron archiver HY/IG OAS J0** + **étendu à toutes séries FRED critiques**
- **WAL streaming Postgres → R2 EU**
- **Redis Streams setup + 3 producers stub** (OANDA, Finnhub, Polymarket)
- **Table `predictions_audit` schéma + migrations**
- **Model registry stub `docs/model-registry.yaml`** + 1 model card template
- **Threat model STRIDE écrit**
- **Hard caps + cost dashboard Grafana** branchés sur Anthropic Usage API + Cloudflare Billing
- **7 incident runbooks templates** dans `docs/runbooks/`
- FastAPI minimal `/healthz` deploy
- Next.js minimal Cloudflare Pages deploy
- Service worker PWA + VAPID push test
- Logo + palette + mockups asset cards (canvas-design)
- ElevenLabs Brian FR test 10 phrases finance + lexique phonétique v0
- Persona Ichor v1 prompt
- Script `check_api_keys.py`

**Semaine 3 — Test restauration + DR** :
- **Premier test restauration Postgres chronométré** → résultat commité
- **Account recovery printout papier** (codes Cloudflare/Hetzner/GitHub/Anthropic) cold storage
- **DPA template ouverts** avec providers (Cloudflare, Hetzner, ElevenLabs, Anthropic, Groq, Cerebras, HuggingFace)
- **CGU + Politique confidentialité v0 draft** (rédaction interne, validation avocat différée Phase 7)

**Gate Phase 0 → Phase 1 enrichi** : 16 critères SPEC §8 + 9 critères additionnels (model registry, predictions_audit, WAL streaming testé, threat model, YubiKey MFA, R2 EU bucket, cost dashboard, restauration test, runbooks templates).

### 5.3 Documents à créer hors SPEC.md

- `docs/model-registry.yaml` + 1 model card par modèle
- `docs/threat-model-stride.md`
- `docs/runbooks/{hetzner-down,key-compromise,postgres-corruption,r2-down,polymarket-renamed,prompt-injection,brier-degradation}.md`
- `docs/dr-tests/2026-Q2.md` (premier test)
- `docs/key-rotation.md` calendrier
- `docs/cgu-v0.md` + `docs/privacy-policy-v0.md` + `docs/dpia-draft.md`
- `docs/legal-amf-mapping.md` (mapping critères AMF DOC-2008-23 vs Ichor)
- `docs/macro-frameworks.md` (paternité 12 moteurs)
- `docs/canon-books.md` (~30 books pour Phase 6 academic digest)

---

## 6. Honnêteté finale — ce qui restera trop ambitieux pour solo dev 0€

Même avec toutes les recommandations intégrées, certaines choses **ne seront pas atteignables**. Mieux vaut le savoir :

- **Latence sub-100ms** type HFT — impossible sur Hetzner standard. Cible <500ms pour ticks UI réaliste.
- **Bloomberg Terminal coverage 100%** — impossible (Bloomberg = ~$24k/an, contient des feeds privés non-réplicables).
- **Vol surface complète tous strikes/expiries** — Tradier free limité, sandbox 15min delay. Pour temps-réel options chains complets = subscription paid.
- **CDX IG/HY 5Y feed propre** — Bloomberg/Markit only. Proxy via OAS uniquement.
- **Cross-currency basis FX swaps** — Bloomberg only. SOFR-OIS spread calculable manuellement, pas de proxy clean.
- **Microstructure tick-data history** — coût massif (CME DataMine ~$500-5000/an). Limitation acceptée.
- **Track record audité performances** — exige tiers indépendant (KPMG, Mazars). Hors scope V1, attendu Phase 7+.
- **Multi-tenant scaling >100 users** — l'architecture single-Hetzner Phase 1-6 ne tient pas. Refonte prévue Phase 7.
- **Compliance Malaisie complète** — exige avocat MY local, ~3-5k€. À provisionner Phase 7.
- **Conformité EU AI Act** (entrée 2 août 2026 articles obligations LLM) — Ichor probablement « limited risk » mais review juridique nécessaire Phase 7.

---

## 7. Recommandation finale — choix stratégique

Eliot, tu as 3 options :

### Option A — « Ship MVP plus vite » (pragmatique)
Garder SPEC.md actuel. Démarrer Phase 0 selon SPEC §14. Intégrer recommandations critiques (top 8) en cours de Phase 1 quand tu en croises le besoin réel.
- **Pour** : tu codes vite, MVP Phase 1 en 7-9 sem comme prévu
- **Contre** : tu vas devoir refactorer Real-time architecture + protocole Brier rigueur en cours de route, friction
- **Score post-Phase 1** : ~6.5/10

### Option B — « SPEC v2 complet avant code » (rigoureux) — **RECOMMANDÉ**
Updater SPEC.md avec les 15 modifications listées §5.1. Délai +1-2 semaines. Phase 0 enrichie selon §5.2. Phase 1 plus solide.
- **Pour** : architecture cohérente dès J1, pas de refactor majeur en cours, défendable face à risk officer / régulateur
- **Contre** : +1-2 semaines avant de coder
- **Score post-Phase 1** : ~7.3/10

### Option C — « Audit + revue avec experts externes » (paranoïa)
Avant Phase 0, faire revue de SPEC v2 par : avocat fintech AMF (1500€), risk officer freelance (1-2k€), staff engineer streaming (1-2k€).
- **Pour** : robustesse maximale dès J1
- **Contre** : 4-6k€ + 4-6 semaines avant Phase 0. Hors budget actuel.
- **Score post-Phase 1** : ~7.8/10

**Recommandation honnête** : **Option B**. Le coût ~1-2 semaines vaut largement la dette technique évitée + la crédibilité externe (régulateur, futurs membres Yone, démonstrateurs publics).

---

## 8. Prochaine action concrète

**Si tu choisis Option B**, je propose ce flux :
1. Tu lis ce AUDIT.md (15-30 min)
2. Tu valides Option A / B / C ou hybride
3. Si B : on `/clear`, nouvelle session avec mission **« Update SPEC.md selon AUDIT.md §5.1 — produire SPEC v2 »**. Travail dans une session vierge avec contexte propre.
4. Validation SPEC v2
5. Encore `/clear`
6. **Phase 0 enrichie démarre** (SPEC v2 §14 + AUDIT §5.2)

Je suis prêt à enchaîner. Dis-moi.

---

*Document maintenu par Claude. Synthèse de 5 sub-agents experts (UX, quant, coverage data, real-time, risk/compliance) + ajouts main agent (frameworks canon + books + research feeds). Mis à jour à chaque évolution majeure.*
