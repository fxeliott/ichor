# Ichor — "Rêve ultime du trader" target document

> Persistent canonical statement of what Ichor must become, as
> articulated by Eliot on 2026-05-11. This document is **immutable
> once accepted** ; subsequent reframes go in their own ADRs (see
> ADR-082 reframe rationale). When in doubt about scope or
> prioritisation, re-anchor here.

## Verbatim Eliot — 2026-05-11

> _"ichor je l'utilise pas car il est pas terminé mais l'objectif
> c'est qu'il soit au coeur de mes analyses. je trades scpécifiquement
> eurusd / gbpusd / usdcad / xauusd / nasdaq et sp500. moi en tant que
> trader je fais mon analyse trading view techique sur le graphique
> avec mes zones etc les différentes unité de temps ma compréhension
> des bougies ok mais ichor lui ça doit etre 90% de mon analyse et il
> doit tout couvrir que ça sois la fondamental la macroéconomie la
> géopolitique les corrélation le volume le sentiment tout tout …
> pas de signaux donc pas de tp sl etc mais des indication
> directionnel des % ce qui peut impacxter comment niveau clé … ça
> doit etre le reve ultime pour tout trader … ultra intelligent
> ultra performant ultra puissant ultra maniaque ultra omniscient …
> il doit couvrir tout le champ des évenement des possibilité des
> scénario en trading … tout doit etre fais en analyse avec claude
> dernier modèle exploiter au maximum avec les meilleurs outils
> skill tout. utiliser claude localement ici sur cette ordi de façon
> automatisé et automatique je veux pas d'api pour pas avoir de cout
> surprise faire avec mon abonnement claude max x20. et je me disais
> potentiellement prendre l'ia perplexity un truc comme ça pour les
> recherches pour ichor quand il devra en faire à chaque fois
> énormément pour toute la data tout en plus des api … pense à ne
> pas accumuler des couches je veux toute une structure et une
> architecture parfaitement horchestré plannifié etc."_

## Verbatim Eliot — 2026-05-04 (anchor of the vision, still valid)

> _"comme si toutes les meilleures institutions et hedge funds étaient
> rassemblé en ce système"_

## What the system must be (decomposed from the 2026-05-11 verbatim)

### 1. Trading scope (verrouillé)

- **Eliot is a discretionary FX/macro/equity-index trader**, sessions
  Londres + New York momentum-based.
- **Assets traded (the only 6 that matter)** : EURUSD, GBPUSD, USDCAD,
  XAUUSD, NAS100, SPX500.
- **Eliot's own contribution (10 %)** : technical analysis on
  TradingView — zones, multi-timeframe alignment, candle reading.
- **Ichor's contribution (90 %)** : everything else.

### 2. Six layers Ichor must cover (verbatim list)

1. **Fondamental** — earnings, macro releases, central-bank policy,
   rate decisions, dot plots, balance-sheet posture.
2. **Macroéconomie** — global cycles, growth/inflation/policy
   trinity, dollar smile state, financial conditions, recession
   nowcasting, surprise indices.
3. **Géopolitique** — sanctions, conflicts, elections, OPEC+ /
   energy-cartel decisions, central-bank intervention thresholds,
   event-driven calendars (FOMC, ECB, NFP, CPI, GDP).
4. **Corrélations** — cross-asset matrix, FX-bond-equity coupling,
   correlation regime shifts, decorrelation events.
5. **Volume / positionnement** — futures COT / TFF, retail crowd
   positioning (MyFXBook), ETF flows, dealer GEX, options
   open-interest, dark-pool ratios, FX positioning surveys.
6. **Sentiment** — news NLP, social-sentiment, FOMC/ECB tone shift,
   AAII bull-bear, options skew (CBOE SKEW, VVIX), tail-risk proxies,
   prediction markets (Polymarket).

### 3. Output contract (strict, ADR-017 boundary)

For each (asset, session), Ichor produces :

- **Direction** : `long | short | neutral`.
- **Probability** : `P(target_up=1) ∈ [0, 1]`, capped at 0.95 (ADR-022).
- **Catalyseurs** : what events / data / shifts could impact the bias
  in the next 4-24 hours (named, dated, sourced).
- **Niveaux clés** : NON-technical levels (gamma flip, peg break,
  TGA threshold, Polymarket decision threshold, VIX regime switch,
  HY OAS percentile). NEVER TP/SL/BUY/SELL.
- **Invalidation conditions** : explicit, Tetlock-style pre-commitment
  of what would falsify the bias.
- **Calibration footer** : Brier score and reliability for this
  (asset, session_type) over recent windows.

### 4. The 5 standard-setting adjectives

The system must be :

- **Ultra intelligent** — uses Claude latest model (Opus 4.7) at max
  effort + every skill + every tool available.
- **Ultra performant** — Brier-calibrated, beats naive baselines,
  measures itself daily.
- **Ultra puissant** — covers the entire space of plausible
  scenarios, not just modal outcomes.
- **Ultra maniaque** — exhaustive, source-stamped, audit-trailed,
  every claim verifiable (Critic Agent, ADR-029).
- **Ultra omniscient** — knows what is happening across the world
  (geopolitics, sanctions, central banks, conflicts, elections).
  Web research (SearXNG, ADR-084) is the omniscience substrate.

### 5. Hard technical constraints (Voie D — ADR-009)

- **Claude Max 20× subscription** is the only LLM compute budget.
  Zero Anthropic SDK consumption.
- **`claude` CLI subprocess locally on Win11** is the only LLM path
  (HttpRunnerClient → claude-runner → `claude -p`).
- **No metered API** — Perplexity rejected ($240/yr + bundles LLM),
  Anthropic web_search rejected ($10/1k), OpenAI banned globally,
  Google Custom Search banned ($5/1k).
- **No surprise cost** — every dependency must have $0 marginal cost
  per query (SearXNG self-host, Serper.dev free tier, GDELT free,
  FRED free, etc.).

### 6. Architectural directive (verbatim "ne pas accumuler des couches")

- **Single orchestrated structure**, not stacked-up layers.
- Each addition must close a documented gap, not invent new ones.
- Anti-tech-debt enforcement : every change reviewed by `code-reviewer`
  subagent ; doctrinal invariants CI-guarded (ADR-081) ; pre-commit
  hooks block silent regressions.
- ADRs are immutable once Accepted ; super-seded by new ADRs with
  explicit `Supersedes: ADR-NNN` header.

## Scope of what Ichor is NOT (contractual)

- **NOT an alpha-generator** — no proprietary information edge, no
  trade-flow tape, no L2 order book.
- **NOT a hedge-fund collective** — no cross-asset PnL attribution,
  no portfolio sizing, no risk-budget allocation.
- **NOT a signal generator** — never emits BUY / SELL / TP / SL /
  position size (ADR-017 contractual, CI-guarded).
- **NOT an auto-trader** — Eliot remains the only entity that opens
  positions.
- **NOT a coach** — does not interpret Eliot's psychology, does not
  recommend trade frequency or rest periods.

## Reframe in marketing copy (sustainable, defensible)

> _"Pre-trade context discretionary toolkit, calibrated against
> historical realized outcomes, with explicit invalidation conditions
> and full audit trail for MiFID-compliant reconstruction."_

Source : ADR-082 reframe rationale (2026-05-11).

## How we measure "are we there yet"

- **Brier score per (asset, session_type)** over rolling 30d / 90d /
  all-time, vs naive baseline (uniform 0.5 prior). Scoreboard live at
  `/calibration` (W101 shipped 2026-05-11).
- **Coverage** : % of realized closes within 80 % CI of magnitude_pips
  forecast.
- **Reliability** : deciles of predicted probability vs realized
  frequency (Murphy 1973 reliability diagram).
- **Skill** : `skill_vs_naive = 1 - Brier_ichor / Brier_naive`. Goal :
  `skill_vs_naive ≥ 0.05` (5 % improvement over uniform).
- **Eliot subjective** : "is Ichor at the heart of my analysis on
  trading days ?" (target : yes, on every trading day, by W112).

## Gap to reality (audit 2026-05-11)

12 gaps between current code and this target — see
`docs/audits/ICHOR_AUDIT_2026-05-11_12_GAPS.md`. Closure plan in
4-sprint roadmap W102 → W112 (ADR-083 + ADR-084 + RUNBOOK-018).

## Maintenance

This document is the canonical answer to "what is Ichor supposed to
be ?". Update it ONLY when Eliot re-articulates the vision in
substance ; minor clarifications go in commit messages or ADRs.

## References

- ADR-009 (Voie D — no Anthropic SDK consumption)
- ADR-017 (boundary — no BUY/SELL ever, contractual)
- ADR-022 (probability-only + conviction cap 95 %)
- ADR-023 (Couche-2 on Haiku low — not Sonnet)
- ADR-029 (audit_log immutable trigger)
- ADR-055 (DOLLAR_SMILE_BREAK 5-of-5)
- ADR-075 (cross-asset matrix v2)
- ADR-081 (doctrinal invariant CI guards)
- ADR-082 (W101 calibration + W102 CF Access strategic pivot ; reframe)
- ADR-083 (Ichor v2 trader-grade manifesto)
- ADR-084 (SearXNG self-hosted — omniscience substrate)
- RUNBOOK-018 (W102 CF Access service token wiring)
- `docs/SESSION_LOG_2026-05-11.md` (this session's chronicle)
- `docs/audits/ICHOR_AUDIT_2026-05-11_12_GAPS.md` (gap analysis)
