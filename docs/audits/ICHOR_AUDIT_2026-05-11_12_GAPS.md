# Ichor coverage audit — 2026-05-11 (12 gaps across the 6-asset universe)

> Read-only audit cristallisé. Source : 3 parallel subagents
> (`ichor-navigator` + `ichor-trader` + `researcher`) commissioned on
> 2026-05-11 night to map the gap between the current code reality and
> the "rêve ultime du trader" standard Eliot articulated for the
> EURUSD / GBPUSD / USDCAD / XAUUSD / NAS100 / SPX500 universe.

## Scope of the audit

- **Assets** : the 6 Eliot actually trades (EURUSD, GBPUSD, USDCAD,
  XAUUSD, NAS100, SPX500). USDJPY + AUDUSD deprioritised per
  ADR-083 D1.
- **Layers required (Eliot verbatim 2026-05-11)** : (1) fondamental,
  (2) macroéconomie, (3) géopolitique, (4) corrélations, (5) volume /
  positionnement, (6) sentiment.
- **Output contract** : direction + probability + catalyseurs +
  niveaux clés. NEVER TP/SL/BUY/SELL (ADR-017 boundary).
- **Constraints** : Voie D (ADR-009, no metered API) ; Couche-2 on
  Haiku low (ADR-023) ; cap-95 conviction (ADR-022).

## Matrix layer × asset (today's coverage)

| Layer                   | Sections data_pool                                                                                                                                                                                                                                                 | 6-asset coverage status                                                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Fondamental             | `_section_calendar` (FOMC/ECB/BoE/BoJ static), `_section_nfib_sbet`, `_section_cleveland_fed_nowcast`, `_section_nyfed_mct`                                                                                                                                        | US-centric. EUR/GBP/CAD = zero earnings, zero CB direct beyond static calendar. XAU/NAS/SPX OK.                             |
| Macroéconomie           | `_section_macro_trinity`, `_section_dollar_smile`, `_section_executive_summary` (7-bucket), `_section_cross_asset_matrix` (W79 ADR-075), `_section_oecd_cli`, `_section_labor_uncertainty`, `_section_fed_financial`, `_section_yield_curve`, `_section_rate_diff` | 5/6 covered. NAS100/SPX500 no rate_diff (`_RATE_DIFF_PAIRS` only 5 FX pairs).                                               |
| Géopolitique            | `_section_geopolitics` (AI-GPR + GDELT 5 events 24 h global), `services/geopol_flash_check.py`, `services/geopol_regime_check.py`, `services/tariff_shock_check.py`                                                                                                | Global, not per-asset. Mapping conflict → pair missing. Sanctions / elections / OPEC+ all absent.                           |
| Corrélations            | `_section_correlations` + `_section_cross_asset_matrix` (data_pool.py:1403-1613, 6-dim macro state + asset-hints qualitatifs)                                                                                                                                      | 6 assets have asset_hints hardcoded ; EUR_USD = GBP_USD logic à 90 % (data_pool.py:1561) — peu différencié.                 |
| Volume / positionnement | `_section_cot`, `_section_tff_positioning` (covers all 6), `_section_myfxbook_outlook` (FX), `_section_polymarket_impact`, `gex_persistence` (NAS/SPX only)                                                                                                        | SPX500 sans COT ; XAU sans MyFXBook ni GEX. Dealer-GEX manque EUR/GBP/CAD/XAU.                                              |
| Sentiment               | `_section_tail_risk_skew` (SKEW/GVZ/OVX), `_section_narrative`, agent `sentiment.py` (AAII + Reddit wsb/forex/stockmarket/Gold), `_section_news`                                                                                                                   | AAII = US equities only. EUR/GBP/CAD sans flux Twitter/X (Bluesky/Mastodon dormants, `mastodon_followed_feeds=""` default). |

## 12 gaps — par-gap

### G1 — GBPUSD + USDCAD reçoivent 3 cards/jour au lieu de 4

- **Sévérité** : HIGH
- **Asset impacté** : GBP, CAD
- **Fichier** : `apps/api/src/ichor_api/config.py:120-123` (split
  `briefing_assets_p1` / `briefing_assets_p2`).
- **Diagnostic** : `run_briefing.py:60-64` inclut EUR/XAU/NAS/USDJPY/
  SPX500 sur `pre_londres` ; GBP/AUDUSD/CAD ajoutés seulement aux 3
  autres windows. Donc GBP et CAD n'ont que 3 cards/jour (12 h / 17 h /
  22 h, pas 06 h).
- **Effort** : 0.5d. Retirer la séparation P1/P2 → un seul array de 6
  assets pour les 4 windows.
- **Wave** : W104a.

### G2 — Push notifications jamais déclenchées

- **Sévérité** : HIGH (Eliot ne reçoit rien quand pre_londres est prêt
  à 06:30 Paris)
- **Asset impacté** : tous (UX)
- **Fichier** : `apps/api/src/ichor_api/services/push.py` orphelin de
  `run_briefing.py`. VAPID + service worker existent côté web2.
- **Diagnostic** : infrastructure complète (`services/push.py` +
  `routers/push.py` + service worker `apps/web2/public/sw.js`) ; aucun
  call à `push.send_to_all()` à la fin de `run_briefing.py`. Eliot
  n'est jamais notifié.
- **Effort** : 1d. Trigger push en fin de batch + payload "Pre_londres
  ready : EUR long 62 %, GBP neutral 51 %, …".
- **Wave** : W112.

### G3 — Dollar smile classifier = label sans algo

- **Sévérité** : HIGH
- **Asset impacté** : XAU, EUR, indices (regime-dependent)
- **Fichier** :
  `apps/api/src/ichor_api/services/session_scenarios.py:34`
  (`RegimeQuadrant`).
- **Diagnostic** : invariant doctrinal #3 mentionne dollar smile state
  classifier (`usd_complacency` vs `funding_stress`) mais aucun
  algorithme ne calcule l'état explicitement à partir de
  DFII10 + BAMLH0A0HYM2 + NFCI + DXY. C'est juste un label déclaratif.
  Pass 1 hallucine la classe régime.
- **Effort** : 1d. Implémenter algo classifier 4-quadrant from realised
  z-scores des 4 inputs + threshold doctrine.
- **Wave** : W104c.

### G4 — `aaii.py` collector ORPHELIN du data_pool

- **Sévérité** : HIGH
- **Asset impacté** : NAS, SPX (framework cite contexte vide)
- **Fichier** : `apps/api/src/ichor_api/collectors/aaii.py` existe ;
  `services/data_pool.py` ne contient AUCUN `_section_aaii`.
- **Diagnostic** : NAS100/SPX500 frameworks asset.py:130-149 citent
  AAII bull-bear comme driver ; le data pool ne livre pas le contexte
  → Pass 2 cite mécanismes vides ou hallucine la valeur AAII.
- **Effort** : 0.5d. Ajouter `_section_aaii` dans data_pool.py +
  source-stamper.
- **Wave** : W104b.

### G5 — USDCAD = asset le plus mal servi

- **Sévérité** : HIGH
- **Asset impacté** : CAD
- **Fichier** : aucun `_section_oil` dans `services/data_pool.py`.
- **Diagnostic** : framework `asset.py:111-118` décrit WTI comme
  primary driver USDCAD ; aucune section ne le surface au pipeline.
  OPEC+ JMMC calendar absent. Baker Hughes rig count weekly absent.
  WCS-WTI spread absent. CAD = asset le plus mal servi des 6.
- **Effort** : 2-3d. Collector WTI from FRED `DCOILWTICO` + Baker
  Hughes weekly RIG_COUNT scrape + OPEC+ JMMC iCal scrape + section
  `_section_oil` dans data_pool.py.
- **Wave** : W110 (consolidée avec géopolitique pour cohérence).

### G6 — SPX500 sans COT

- **Sévérité** : MED
- **Asset impacté** : SPX
- **Fichier** : `services/data_pool.py:1787` (`_COT_MARKET_BY_ASSET`).
- **Diagnostic** : `_COT_MARKET_BY_ASSET:167` commenté
  ("code not in collectors/cot.py yet"). TFF wired FX only. SPX500
  ES futures CME COT (CFTC weekly) absent.
- **Effort** : 1d. Collector CFTC weekly TFF for E-mini S&P 500 (code
  ES) + wire dans `_COT_MARKET_BY_ASSET`.
- **Wave** : W104d (avec asset universe align).

### G7 — ETF flows GLD/SPY/QQQ manquent

- **Sévérité** : MED
- **Asset impacté** : XAU, NAS, SPX
- **Fichier** : aucun collector ETF flows.
- **Diagnostic** : SPDR/iShares ont daily fact sheets téléchargeables
  (basket files free). Indique flows entrée/sortie → leading indicator
  pour gold + indices. Couvre le gap "ETF positioning" de l'invariant
  Easley-LdP-O'Hara VPIN.
- **Effort** : 2d. Collector daily fact sheets SPDR (GLD) + iShares
  (QQQ, SPY si présent) ou State Street + persistence hypertable.
- **Wave** : W111.

### G8 — Géopolitique non-mappée par asset

- **Sévérité** : MED
- **Asset impacté** : tous
- **Fichier** : `services/data_pool.py:2073` (`_section_geopolitics`).
- **Diagnostic** : retourne 5 GDELT events globaux flat. Jamais filtré
  par exposition CAD/oil, EUR/sanctions Russie, XAU/conflits, indices/
  US politics. Donc Pass 2 cite contexte non pertinent.
- **Effort** : 3d. Mapping `theme → asset` (CAMEO topic codes →
  asset universe) + filtre dans `_section_geopolitics` per asset card.
- **Wave** : W110.

### G9 — OFAC sanctions + OPEC+ JMMC + IFES élections = ZERO feed

- **Sévérité** : MED
- **Asset impacté** : CAD, EUR (sanctions Russie), tous (US 2026
  cycle)
- **Fichier** : aucun feed.
- **Diagnostic** : sources gratuites identifiées par researcher
  (OFAC SDN list daily, OPEC iCal monthly, IFES Election Guide
  continu) mais zéro collector dans `apps/api/src/ichor_api/
collectors/`.
- **Effort** : 2d. 3 collectors light + sections data_pool.
- **Wave** : W110.

### G10 — Aucun feed Twitter/X live

- **Sévérité** : MED
- **Asset impacté** : tous (sentiment temps réel)
- **Fichier** : `apps/api/src/ichor_api/config.py:131`
  (`mastodon_followed_feeds=""` default).
- **Diagnostic** : `collectors/bluesky.py` + `collectors/mastodon.py`
  existent dormants. Configuration vide → aucune ingestion. Pas de
  Twitter/X (API payante).
- **Effort** : 1d. Liste curatée de comptes Mastodon FX/macro/CB +
  activation collector via Ansible role config.
- **Wave** : W110.

### G11 — `/today/page.tsx` checklist hardcodée + pas de "what changed overnight"

- **Sévérité** : MED
- **Asset impacté** : UX morning ritual
- **Fichier** : `apps/web2/app/today/page.tsx:39-101`.
- **Diagnostic** : checklist 5-lignes hardcodée, `MOCK_TRIGGERS` (39-64)
  figés. Pas de diff vs J-1 ("what changed overnight"). Pages
  individuelles existent par asset mais pas de vue gestalt.
- **Effort** : 2d. Server-side diff endpoint `/v1/today/diff` (J vs J-1)
  - redesign page avec deltas highlighted.
- **Wave** : W112 (consolidé avec G2 push notifs).

### G12 — Pass 4 ≠ 7 scenarios (factuellement 3)

- **Sévérité** : HIGH
- **Asset impacté** : tous (output exhaustive)
- **Fichier** :
  `packages/ichor_brain/.../session_scenarios.py:38-50` (3 scenarios :
  Continuation / Reversal / Sideways) + `invalidation.py:24` ("at
  least one condition, three sweet spot").
- **Diagnostic** : ICHOR_PLAN.md:209-217 promet 7 scénarios
  probability-weighted (`crash_flush / strong_bear / mild_bear / base
/ mild_bull / strong_bull / melt_up`). Code actuel = 3. Pass 6 NEW
  (ADR-083 D2) ajoute les 7 stratifiés avec
  `scenarios JSONB` column dans session_card_audit + sum p = 1.0
  (CI-guarded ADR-081 extension).
- **Effort** : 5-7d. Pass 6 implementation + migration 0039 candidate
  - frontend rendering (W107 Living Analysis View).
- **Wave** : W105.

## Synthèse — 3 gaps les plus dangereux (verdict ichor-trader)

1. **G3 Dollar smile state classifier explicite** — invariant
   doctrinal #3 sans algorithme = Pass 1 hallucine la classe régime.
2. **G4 + G7 ETF flows + AAII + breadth pour indices** — frameworks
   NAS100/SPX500 citent du contexte que le data pool ne livre pas =
   Pass 2 cite mécanismes vides.
3. **G5 OPEC+ + WTI daily + Baker Hughes pour USDCAD** — framework
   asset.py:111-118 décrit WTI primary driver mais zéro section oil.
   USDCAD = asset le plus mal servi.

## Méthodologie de l'audit

- **Subagents lancés en parallèle** (single message, multi tool use
  blocks) :
  - `ichor-navigator` — read-only topology mapping (data_pool sections
    × 6 assets × 6 layers) + frontend usabilité.
  - `ichor-trader` — verdict trader-grade sur les 6 paires + 9
    invariants check + Pass 4 ≠ 7 scenarios correction factuelle.
  - `researcher` — WebSearch 2026 macro frameworks + sources free
    event/data macro tabulées.
- **Fichiers critiques lus en parallèle** :
  - `docs/decisions/ADR-082-w101-calibration-w102-cf-access-strategic-pivot.md`
  - `docs/decisions/ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md`
  - `C:\Users\eliot\.claude\projects\D--Ichor\memory\ICHOR_SESSION_PICKUP_2026-05-09_v3_POST_W85.md`
  - `apps/claude-runner/src/ichor_claude_runner/main.py`
  - `apps/claude-runner/src/ichor_claude_runner/auth.py`
  - `apps/claude-runner/src/ichor_claude_runner/config.py`
  - `packages/ichor_brain/src/ichor_brain/runner_client.py`
- **Mode** : ultrathink + maximum-mode (Eliot directives) ; full
  autonomy ratified.

## Références ADR

- ADR-017 (boundary)
- ADR-022 (conviction cap)
- ADR-023 (Couche-2 Haiku)
- ADR-055 (DOLLAR_SMILE_BREAK 5-of-5)
- ADR-068 (cb_nlp redesign content refusal)
- ADR-074 (MyFXBook replaces OANDA)
- ADR-075 (cross-asset matrix v2)
- ADR-076 (frontend MOCK pattern)
- ADR-077 (Cap5 MCP server wire)
- ADR-078 (Cap5 query_db excludes trader_notes)
- ADR-081 (doctrinal invariant CI guards)
- ADR-082 (W101 calibration + W102 CF Access strategic pivot)
- ADR-083 (Ichor v2 trader-grade manifesto)
- ADR-084 (SearXNG self-hosted web research — sequel of ADR-083 D5)

## Wave allocation

| Gap | Wave        |
| --- | ----------- |
| G1  | W104a       |
| G2  | W112        |
| G3  | W104c       |
| G4  | W104b       |
| G5  | W110 / W111 |
| G6  | W104d       |
| G7  | W111        |
| G8  | W110        |
| G9  | W110        |
| G10 | W110        |
| G11 | W112        |
| G12 | W105        |

Total effort to close 12 gaps : ~25-35 dev-days (sprints 2 + 3 + 4 of
the W102 → W112 roadmap).
