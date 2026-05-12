# Ichor — Architecture cible (Living Macro Entity 10 couches)

> Référence architecturale globale du système Ichor. Ratifié 2026-05-12
> session round 8 suite directive Eliot "revoit tout, construit
> architecture globale interconnectée, pas accumuler couches".
>
> Document **vivant** — sert de boussole pour toute extension future.
> Tout nouveau collecteur, agent, pass ou alert DOIT s'aligner sur une
> des 10 couches ci-dessous, sinon ADR de dérogation explicite.

## Principe doctrinal

Ichor n'est PAS une accumulation d'extensions ad-hoc. C'est un système
**stratifié 10 couches** où chaque couche consomme la précédente et
émet vers la suivante. **Tout est interconnecté à la perfection** via
des contrats Pydantic explicites + un Critic gate + source-stamping
intégral.

## Stratification 10 couches

```
┌─────────────────────────────────────────────────────────────────────┐
│ COUCHE 10 — ALERTS + EVENT-DRIVEN NOTIF                             │
│   27 catalog alerts + composite triggers + event-driven cards       │
│   (NFP / VIX spike / FOMC tone-shift / Polymarket whale / OFAC)     │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  9 — LEARN (auto-amélioration)                               │
│   Brier→weights optimizer + ADWIN drift→alert +                     │
│   post-mortem hebdo Claude Opus + méta-prompt tuning bi-mensuel    │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  8 — RAG + PERSISTENCE                                       │
│   session_card_audit + scenarios JSONB + scenario_calibration_bins +│
│   pgvector 5-ans (bge-small-en-v1.5) + DTW analogues retrieval      │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  7 — CRITIC GATE (rule-based + ADR-017 boundary)             │
│   Sentence-level scan + source-stamp verification + verdict gate    │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  6 — Pass-6 SCENARIOS (Sonnet 4.6 medium)                    │
│   7 buckets stratifiés (crash_flush..melt_up) + cap-95 + sum=1      │
│   + magnitudes pip/point empirical + mechanism plain-français       │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  5 — Pass-4 INVALIDATION (Tetlock pre-commitment)            │
│   N conditions numeric thresholds + sources + DTW analogues lookup  │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  4 — Pass-3 STRESS-TEST                                      │
│   Devil's advocate Claude Opus + 12 stress scenarios canoniques     │
│   (CPI surprise / NFP miss / FOMC hawkish / ECB cut / VIX spike /   │
│    geopol flash / OPEC+ / election / peg break / liquidity / etc.)  │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  3 — CONVERGENCE (Pass-2 bias_aggregator)                    │
│   Confluence weights Brier-optimized per asset×regime +             │
│   14 ML ensemble (HMM+FOMC-RoBERTa+FinBERT+VPIN+HAR-RV+DTW+ADWIN+   │
│    SABR-SVI+LightGBM+XGBoost+RF+Logistic+NumPyro+MLP)              │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  2 — INTELLIGENCE (Pass-1 + Pass-2 réflexion 12 moteurs)     │
│   Top-down macro | Bottom-up micro | Carry | Mean-reversion |       │
│   Momentum | Contrarian | Event-driven | Narrative |                │
│   Liquidity | Vol-regime | Cross-asset arb | Relative-value         │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  1 — SYNTHÈSE COUCHE-2 (7 agents on Claude Haiku low)        │
│   cb_nlp + news_nlp + sentiment + positioning + macro +             │
│   microstructure + geopolitics (agent dédié, GDELT par asset)       │
├─────────────────────────────────────────────────────────────────────┤
│ COUCHE  0 — INGESTION (200+ signaux temps réel)                     │
│   • Macro : 80+ FRED + ECB SDMX + BLS + BoE + BoJ + RBA + BoC       │
│   • Marché : Polygon FX 1-min + ticks + news + Stooq daily          │
│   • Calendar : ForexFactory + IFES + OPEC+JMMC + 8 CB + Mag-7       │
│   • Géopol : GDELT 15min + ACLED + OFAC daily + GPR Caldara/country │
│   • CB : 8 CBs speeches/minutes/dot plot                            │
│   • Position : COT/TFF + DIX/GEX + DTCC + TIC + RRP + TGA + ETFs   │
│   • Sentiment : AAII + II + NAAIM + Reddit + Twitter whitelist     │
│   • Vol : VIX family + RR25Δ × 8 + IV skew per asset                │
│   • Flow : ETF 50+ + Polymarket + Kalshi + Manifold                 │
│   • Microstructure : tick rule + VPIN + order flow + SMC OB/FVG     │
└─────────────────────────────────────────────────────────────────────┘
```

## Score brutal par couche (2026-05-12)

| #   | Couche                  | Score | Effectif                                                         | Gap                                                                                                                                                 |
| --- | ----------------------- | ----- | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0   | Ingestion               | 5/10  | ~95 signaux                                                      | 105 signaux manquants (G5/G7/G8/G9/G10 + 8 collectors planned)                                                                                      |
| 1   | Couche-2                | 6/10  | 5/7 agents                                                       | microstructure agent + geopolitics agent absents                                                                                                    |
| 2   | Intelligence 12 moteurs | 3/10  | 4 moteurs                                                        | 8 moteurs absents (carry, contrarian explicit, narrative tracker BERTopic, vol-regime, X-arb, RV pairs, liquidity-aware, event-driven systématique) |
| 3   | Convergence             | 3/10  | confluence_engine code OK                                        | 8/14 ML absents + Brier→weights OFF + bias_aggregator vide                                                                                          |
| 4   | Stress                  | 7/10  | Pass-3 LIVE                                                      | 12 stress scenarios pas explicitement listés                                                                                                        |
| 5   | Invalidation            | 6/10  | Pass-4 LIVE                                                      | **DTW analogues pas wired Pass-1/3**                                                                                                                |
| 6   | Pass-6 Scenarios        | 8/10  | LIVE prouvé EUR/USD `d2222ea2`                                   | Calibration empirique cold-start (W105b cron now active)                                                                                            |
| 7   | Critic                  | 7/10  | rule-based LIVE                                                  | Source-link verification + ML boundary check à renforcer                                                                                            |
| 8   | RAG Persistence         | 4/10  | session_card_audit + scenarios JSONB + scenario_calibration_bins | **pgvector 5-ans ABSENT**                                                                                                                           |
| 9   | Learn                   | 1/10  | 0 boucle active                                                  | 4 boucles dormantes : Brier→weights, ADWIN drift, post-mortem hebdo, méta-prompt                                                                    |
| 10  | Alerts/Event-driven     | 5/10  | 8/27 alerts LIVE + push notifs G2                                | event-driven cards = 0                                                                                                                              |

**Score global pondéré : 5.0/10**.

## Inventaire des 200+ signaux cibles (Couche 0)

### Macro fondamental (~80)

- US : FRED 30+ (DGS10, DFII10, T10Y2Y, NFCI, BAMLH0A0HYM2, CPI, PPI, PCE, NFP, ISM, PMI, Industrial Production, Retail Sales, Housing Starts, Unemployment, etc.)
- Zone Euro : ECB SDMX 15+ (Eonia, €STR, harmonised CPI, M3, GDP, unemployment, current account)
- UK : BoE IADB 10+ (Bank Rate, gilt yields, RPI, CPI)
- Japan : BoJ 8+ (call rate, JGB curve, CPI, Tankan)
- Canada : BoC 6+ (overnight, CAD-USD differential)
- Australia/NZ : RBA/RBNZ 6+
- Switzerland : SNB 4+
- China : PBoC 6+ (LPR, RRR, USDCNY fixings)
- **Cleveland Fed nowcasts** : 4×3 daily (CPI/Core/PCE/CorePCE × MoM/QoQ/YoY) ✅
- **NY Fed MCT** : monthly multivariate core trend ✅
- **NFIB SBET** : monthly Small Business Economic Trends ✅

### Marché spot/forward (~30)

- Polygon FX 1-min OHLCV (6 pairs primaires + 2 tracked)
- Polygon FX ticks (Phase 2 VPIN)
- Stooq daily 8 pairs + 4 indices + XAU/XAG/WTI/Brent/NatGas
- Polygon news (filter ticker-linked)
- Spot rates 8 majors

### Calendar événementiel (~20)

- ForexFactory weekly eco-calendar
- IFES élections (US + UK + EU + Asia)
- OPEC+ JMMC iCal
- 8 CB official calendars
- Mag-7 earnings dates
- Treasury auctions calendar
- US holidays

### Géopolitique (~25)

- GDELT 2.0 Events 15-min
- ACLED weekly
- OFAC SDN daily
- Caldara-Iacoviello GPR daily + country-specific
- Sanctions tracking (Russia/Iran/China)
- White House EO RSS
- Israel-Iran proximity index
- Taiwan Strait tension proxy
- Korea peninsula proxy

### Central Banks NLP (~15)

- FOMC speeches + minutes + dot plot
- ECB speeches + minutes
- BoE MPC minutes
- BoJ statements
- SNB / PBoC / RBA / BoC equivalents

### Positionnement (~25)

- CFTC TFF weekly (8 currency futures + ES + NDX) ✅ partial
- CFTC Disaggregated COT
- DTCC FX volume
- LSE forex daily
- MyFXBook Community Outlook ✅
- SqueezeMetrics DIX/GEX daily
- 0DTE charm flow
- FINRA Reg SHO short volume ✅
- Treasury TIC monthly ✅
- Reverse repo facility (RRP)
- TGA balance (Treasury Cash)
- M2 / monetary base / bank reserves
- ETF flows : SPDR (50+ ETFs), iShares, Vanguard daily fact sheets

### Sentiment retail (~20)

- AAII weekly Bull/Bear ✅
- Investors Intelligence
- NAAIM exposure
- Reddit WSB + r/forex + r/wallstreetbets + r/gold
- Twitter/X whitelist (8 CBs + Powell/Lagarde/Bailey + select macro voices)
- Bluesky + Mastodon (curated FX/macro)
- Google Trends watchlist
- News sentiment FinBERT-tone

### Vol surface (~25)

- VIX/VXN/VVIX/VIX9D/VIX3M/VIX6M/VXEEM
- Risk reversals 25Δ + 10Δ × 8 pairs ✅ partial RR25D
- IV skew + IV term structure per asset
- SKEW index ✅
- HAR-RV vol forecast ✅

### Microstructure (~20)

- VPIN BVC microstructure ✅ partial
- Tick rule trade classification
- Effective + quoted spreads
- Trade size distribution
- Realized vol HAR-RV ✅
- Liquidity heatmap
- Tokyo fix / London fix anomalies
- SMC (Order Block, FVG, BoS, CHoCH, liquidity sweep)
- Tape reading characteristics

### Cross-asset stress (~15)

- DOLLAR_SMILE_BREAK 5-of-5 ✅
- MACRO_QUINTET_STRESS ✅
- VIX_TERM_INVERSION ✅
- YIELD_CURVE_INVERSION_DEEP ✅
- TREASURY_VOL_SPIKE ✅
- HY_IG_SPREAD_DIVERGENCE ✅
- TERM_PREMIUM_REPRICING ✅
- REAL_YIELD_GOLD_DIVERGENCE ✅
- RISK_REVERSAL_25D ✅
- LIQUIDITY_TIGHTENING ✅

**Sommé : ~280 signaux cibles, ~95 effectifs au 2026-05-12 = 34% raw coverage**. La plupart des signaux cibles sont des extensions ou des feeds non encore branchés.

## Roadmap implementation par phase

Phases ordonnées par ROI × dépendance technique :

### Phase A — Monitoring + Auto-Recovery (1 dev-day)

**Pourquoi en premier** : sans visibility, les autres phases foirent silencieusement (vu aujourd'hui : tunnel CF zombi 18h non détecté).

- Tunnel CF probe + auto-restart cloudflared cron 5 min
- Claude CLI auth probe + notif Eliot si expiry
- End-to-end synthetic monitor (dry-run pre_londres simulé chaque heure)
- Pass failure retry 1× exponential backoff
- ichor-api `/healthz` end-to-end probe Hetzner

### Phase B — Cap5 Tools Activation Pass-6 (0.5 dev-day) ✅ ROUND 8

**Pourquoi rapide** : code wired depuis W83-W87, seul l'instanciation manque.

- ✅ `--enable-tools` CLI flag dans `run_session_card.py`
- ✅ ToolConfig instanciation avec `enabled_for_passes={regime, asset, scenarios}`
- ⏳ Smoke test single card EUR_USD `--enable-tools` post-batch
- ⏳ Cron flip ON after 3 successful smoke tests

### Phase C — RAG pgvector 5-ans (2-3 dev-days)

**Game-changer pour intelligence/precision** :

- Migration 0040 : extension pgvector + table rag_chunks_index
- bge-small-en-v1.5 self-host (HuggingFace transformers CPU)
- Embedding ingestion : every session_card_audit → vector
- Retrieval Pass-1 : top-5 similar past macro states + outcomes
- Inject as "## Historical analogues" in prompt

### Phase D — Auto-Improvement Loop (2-3 dev-days)

**Activate les 4 boucles dormantes** :

- Brier optimizer V2 promotion (after 30 cards holdout)
- ADWIN drift → BIAS_BRIER_DEGRADATION alert wire
- Post-mortem hebdo dimanche 18h Claude Opus auto + PR GitHub
- Méta-prompt tuning bi-mensuel PR auto (label `auto:meta-prompt-tuning`)

### Phase E — Data Coverage Push (5-8 dev-days)

- W108 FOMC/ECB tone activation Hetzner (30 min SSH `pip install transformers torch --cpu`)
- G5 USDCAD WTI + OPEC+ JMMC + Baker Hughes
- G7 ETF flows GLD/SPY/QQQ + 50 sector ETFs
- G8 Géopolitique mapped par asset (CAMEO codes → asset universe)
- G9 OFAC SDN + IFES élections
- G10 Twitter/X CB officials whitelist + Bluesky + Mastodon
- 6 ML planned : LightGBM, XGBoost, RF, Logistic, NumPyro, MLP
- 7 collectors `Planned` restants

### Phase F — Interconnection Architecture (3-5 dev-days)

- Causal propagation Bayesian graph (pgmpy) — event → secondary → tertiary impacts
- Bias aggregator avec 12 moteurs convergence
- DTW analogues retrieval Pass-1
- Cross-asset arbitrage detection live
- microstructure + geopolitics Couche-2 agents dédiés

### Phase G — Event-Driven Triggers (2-3 dev-days)

- NFP/CPI release → crisis card auto
- VIX spike threshold → crisis_mode briefing
- Polymarket whale → notif push
- FOMC tone-shift → notif push
- Sanctions OFAC update → notif if CAD/EUR exposure

**Total backend** : ~17-25 dev-days pour atteindre 95%+ coverage cible.

## Stratification de la décision : pourquoi 10 couches ?

Chaque couche **ajoute une dimension de fiabilité** :

- Couches 0-1 : _exhaustivité data_
- Couches 2-3 : _intelligence convergence_
- Couches 4-5 : _humilité (devil's advocate + Tetlock)_
- Couche 6 : _granularité probabiliste (7 buckets)_
- Couche 7 : _boundary respect (Critic gate)_
- Couche 8 : _mémoire historique (RAG)_
- Couche 9 : _apprentissage auto (Brier feedback loop)_
- Couche 10 : _réactivité temps réel (event-driven)_

Un système qui skip une couche est un système faible. Aujourd'hui Ichor
skip principalement la Couche 9 (apprentissage) — c'est pourquoi le
système ne s'améliore pas avec le temps.

## Interconnexions explicites (contrats Pydantic)

```
Couche 0 ──ingestion──> Couche 1 (Couche-2 agents)
                           │
                           ├──> couche2_outputs table
                           │
                           └──> data_pool `_section_couche2_*` sections
                                  │
                                  v
Couche 2 (Pass-1+Pass-2)  ──read──> data_pool + asset_data
   │
   ├──> RegimeReading (Pydantic) ──> Pass-3
   │
   └──> AssetSpecialization (Pydantic) ──> Pass-3 + Pass-4 + Pass-6

Pass-3 ──> StressTest (Pydantic) ──> Pass-4 + Pass-6
Pass-4 ──> InvalidationConditions (Pydantic) ──> Pass-6 + Critic
Pass-6 ──> ScenarioDecomposition (Pydantic) ──> Critic
Critic ──> CriticDecision (Pydantic) ──> SessionCard assembly
                                                   │
                                                   v
                                       Couche 8 persistence + RAG
                                                   │
                                                   v
                                       Couche 9 Learn (Brier+drift)
                                                   │
                                                   v
                                       Updates Couche 3 weights
                                                   │
                                                   └──> next session card
```

Cette boucle fermée est la définition d'une _Living Macro Entity_.

## Voie D respect (ADR-009)

Toutes les LLM calls routent via Claude Max 20× subprocess. **Aucun**
Anthropic SDK consumption. Cap5 tools accessent données via apps/api
HTTPS endpoints (audit-trail intégral) — pas de DB credentials sur
Win11.

## CI guards doctrinaux (ADR-081 + W91 + W105f)

9 invariants mécanisés à chaque commit :

1. No BUY/SELL signals (tokenize, ADR-017)
2. Voie D no `import anthropic` (ADR-009)
3. Couche-2 sur Haiku low (ADR-023)
4. Conviction cap-95 regex (ADR-022)
5. `audit_log` immutable trigger (ADR-029)
6. `tool_call_audit` immutable trigger (ADR-077)
7. Watermark single-source-of-truth (ADR-079/080)
8. Pure-data routes negative-guard (ADR-080)
9. Pass-6 BUCKET_LABELS canonical + CAP_95 unchanged (ADR-085)

## Références

- [ADR-017](decisions/ADR-017-reset-phase1-living-macro-entity.md) — Living Macro Entity boundary
- [ADR-082](decisions/ADR-082-w101-calibration-w102-cf-access-strategic-pivot.md) — Pre-trade discretionary toolkit reframe
- [ADR-083](decisions/ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md) — Ichor v2 manifesto + 7 décisions D1-D7
- [ADR-085](decisions/ADR-085-pass-6-scenario-decompose-taxonomy.md) — Pass-6 7-bucket taxonomy
- [ICHOR_PLAN.md](ICHOR_PLAN.md) — Roadmap originelle 8 phases (Phase 0..7)
- [SPEC.md](../SPEC.md) — Spec Phase 2 fondatrice 2026-05-04
- [SESSION_LOG_2026-05-12.md](SESSION_LOG_2026-05-12.md) — 7-rounds marathon LIVE proof Pass-6
