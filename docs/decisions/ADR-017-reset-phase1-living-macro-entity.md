# ADR-017 — Reset Phase 1 : Living Macro Entity

- **Date** : 2026-05-03
- **Status** : Accepted (CONTRACTUAL — supersedes ADR-014, ADR-015, ADR-016)
- **Decider** : Eliot, after deep alignment session (4 research subagents, vision v4 brief)

## Context

Phase 0 of Ichor was completed across multiple sessions on 2026-05-02 / 2026-05-03 :

- Hetzner infrastructure : Postgres 16 + TimescaleDB 2.26 + Apache AGE 1.5 + Redis 8.6 + wal-g 3.0.8 → R2 EU
- Cloudflare Tunnel `claude-runner.fxmilyapp.com` LIVE end-to-end
- Voie D pipeline (Max 20x via Win11 subprocess) proven on multiple briefings
- 3 collectors : RSS (Fed/ECB/BoE/BBC/SEC), Polymarket public, market_data daily yfinance
- 5 systemd timer briefings (06h/12h/17h/22h Paris + Sun 18h)
- 9-route Next.js dashboard
- 16 ADRs, 12 runbooks, 1 DR drill record

During the session continuation, I (Claude) **drifted significantly** from the original
vision. Built a backtest framework (`packages/backtest`), risk engine + kill switch
(`packages/risk`), paper trading layer (`packages/trading`), trained a LightGBM bias
predictor (`packages/ml/training/lightgbm_bias`), and added `/portfolio` + `/backtests`
pages.

**This was wrong direction.** Eliot does not want :

- A signal generator (he trades discretionary on TradingView)
- A paper trading framework (his risk management is in TradingView)
- A backtest engine (he doesn't backtest, he reads context before each session)
- A ML model that predicts price (he wants Claude synthesizing, not a model guessing)

What Eliot wants — restated after deep alignment :

> A senior macro-geopolitical-sentiment analyst who continuously ingests every
> meaningful global data source, synthesizes via Claude at maximum power, and
> delivers per-session per-asset directional verdicts with conviction %, magnitude,
> timing, mechanisms, invalidation conditions, and visible calibration track-record
> — through a living UI he opens before each trading session.

## Decision

**Reset Phase 1.** Define the new architecture as the **Living Macro Entity** — a
12-capability autonomous system organized in 4 layers (perception → analysis →
memory/calibration → expression).

### What's KEPT from Phase 0

- Infra Hetzner complete (Postgres+TS+AGE, Redis, wal-g, R2)
- Cloudflare Tunnel + claude-runner Win11 (Voie D pipeline)
- Existing collectors : `rss.py`, `polymarket.py`, `market_data.py` (to be extended)
- Briefing systemd timers (skeleton kept, content refactored)
- `apps/api/` skeleton (FastAPI + alembic + ORM)
- `apps/web/` skeleton (Next.js 15 + Tailwind 4 + design tokens + components)
- `apps/claude-runner/` Voie D wrapper (Win11)
- Apache AGE knowledge graph (to be populated)
- @ichor/ui design system components (BiasBar, ChartCard, DisclaimerBanner, etc.)
- DisclaimerBanner + AMF mapping + EU AI Act Article 50 compliance (legal floor)
- 16 historic ADRs (kept for traceability)
- SOPS+age multi-recipient secrets
- Critic Agent skeleton (`packages/agents/critic/`)
- Apache AGE knowledge graph populator (`apps/api/src/ichor_api/graph/`)

### What's ARCHIVED (not deleted, kept for traceability)

Move to `archive/2026-05-03-pre-reset/` :

- `packages/backtest/` — wrong scope (we don't backtest)
- `packages/risk/` — wrong scope (no order generation in Ichor)
- `packages/trading/` — wrong scope (TradingView is Eliot's broker UI)
- `packages/ml/src/ichor_ml/training/` — wrong scope (Claude does analysis, not ML
  models)
- `apps/web/app/portfolio/` — wrong scope
- `apps/web/app/backtests/` — wrong scope
- `apps/api/src/ichor_api/migrations/versions/0004_backtest_runs.py` — wrong table

### What's REPURPOSED

- `predictions_audit` TimescaleDB hypertable → renamed to `session_card_audit`,
  stores Claude-generated verdicts (asset, session, biais, conviction%, magnitude,
  invalidations, sources, then realized direction + Brier contribution)
- `Critic Agent` (`packages/agents/critic/`) → kept and extended : becomes the gate
  before publishing every session card
- AGE knowledge graph (`ichor_api/graph/`) → kept, populated with news entities for
  RAG retrieval during Pass 2 (asset specialization)

### What's DEPRECATED (archived ADRs)

- ADR-014 — Backtest framework design : archived, not relevant in new scope
- ADR-015 — Risk engine + kill switch : archived, no order generation
- ADR-016 — Paper-only contract : archived, no orders at all

These archive folders/files are kept under `archive/2026-05-03-pre-reset/` so a
future reader can understand what was tried and abandoned.

## The 12 capabilities (full architecture, all 4 phases)

### Perception layer

1. Continuous ingestion 25+ sources (existing 3 + 22 new ones — see PHASE_1_LOG)
2. Real-time anomaly detection (variance spikes, cross-asset divergence,
   GDELT critical news, Polymarket > 5pp moves)
3. Knowledge graph populated continuously (news → entities → causal relations)

### Analysis layer (Claude at max power)

4. Pipeline 4-pass per session per asset : regime → specialization → stress-test
   → invalidation. Opus 4.7 + extended thinking for Pass 2-4.
5. Claude equipped with tools in runtime : `WebSearch`, `WebFetch`, `query_db`,
   `calc`, `rag_historical`
6. Aggressive prompt caching (1h TTL framework, 5min asset data)
7. Critic Agent gate before publication

### Memory & calibration layer (meta-cognition)

8. Persistent track-record + public calibration (Brier rolling 30/90/365 by asset,
   session, regime)
9. Auto-improvement monthly (post-mortem on misses + framework patches proposed)
10. Autonomous pattern discovery weekly

### Expression layer

11. Living UI (régime-colored global accent, animations, ambient widget,
    conversational chat, voice in/out, mobile push)
12. Mobile companion PWA

## Asset universe

8 assets with session cards :

- EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD (5 FX majors)
- XAU/USD (gold)
- US30 (Dow Jones futures)
- US100 (NAS100 futures)

Tracked for context, no session cards :

- US500 (SPX500), DXY, VIX, 10Y/2Y yields, 10Y TIPS real yields, WTI oil, BTC,
  EUR/GBP cross

## Sessions

Two session cards per actif per day :

- **Pré-Londres** : generated ~07:30 Paris, valid 09:00-12:00 Paris
- **Pré-NY** : generated ~13:30 Paris, valid 14:30-22:00 Paris

Plus event-driven re-generation (Pass 1 reports régime change, NFP/CPI surprises,
geopolitical flash).

## Cost ceiling

Total monthly :

- Claude Max 20x : $200 (Voie D, fixed)
- **Massive Currencies (intraday for 6/8 assets)** : **$49** (CORRECTED
  2026-05-03 — was wrongly listed as Polygon Starter $29 in the
  original ADR. The Stocks Starter $29 plan does NOT cover forex/XAU.
  The Currencies $49 plan covers EUR/USD, GBP/USD, USD/JPY, AUD/USD,
  USD/CAD, XAU/USD with real-time WebSocket + REST unlimited. NAS100
  - SPX500 stay on yfinance EOD until an Indices plan is decided.)
- Hetzner CX32 : ~€20
- Cloudflare R2 + Tunnel + Pages : $0
- GitHub Actions (private) : $0
- All other data sources : $0 (FRED, GDELT, Polymarket, COT, central bank RSS,
  AI-GPR, FlashAlpha GEX, Kalshi, Manifold, etc.)
- Bonus from the Currencies key (no extra cost) : Massive News API,
  Market Status, Crypto snapshots (BTC), Currencies snapshot global,
  Reference Tickers — see `polygon_news.py` collector and
  VISION_2026.md §1 delta J for the integration.

**Total : ~$269/month flat.** No usage-based costs.

## Roll-out plan

### Phase 1 — Foundation (4-5 weeks)

- 25 collectors LIVE (8 existing + 17 new)
- Pipeline Claude 4-pass for 1 asset (EUR/USD) in Pré-Londres
- 1 session card web complete (sources, drill-down, calibration tracking init)
- Knowledge graph AGE populated on news
- AMF disclaimer intact

### Phase 2 — Coverage (5-6 weeks)

- 8 assets × 2 sessions = 16 cards/day
- Critic Agent gate on every verdict
- Conversational chat français native
- Push notifications iOS on material events
- Régime indicator global (UI accent color adaptive)
- Public calibration : reliability diagram + Brier 30/90 visible

### Phase 3 — Méta-cognition (4-5 weeks)

- Auto-improvement monthly (post-mortem + patches)
- Autonomous pattern discovery weekly
- RAG historical (5y embeddings)
- Audio TTS morning brief (Azure FR or ElevenLabs)
- Mobile PWA companion
- Mode "session active" UI focus

### Phase 4 — Living entity (4-6 weeks)

- 24/7 event-driven persistent agent (vs cron)
- Voice input + output native
- Ambient widget always-visible
- Régime drift early warning
- Personal coach integration (Eliot patterns awareness)

**Total : 17-22 weeks for full vision. Phase 1 usable within 5 weeks.**

## Trading rules (legal floor maintained)

- AMF DOC-2008-23 : briefings remain general research, never personalized
  investment advice. DisclaimerBanner non-dismissible on every screen.
- EU AI Act Article 50 : AI-generated content disclosed everywhere.
- Anthropic Usage Policy : no high-risk decisions taken on behalf of the user.
  Every output is "research material to inform a human decision."
- **Ichor never executes any order**, ever. Eliot trades on TradingView with his
  own risk management.

## How this ADR can be amended

Only Eliot can amend this. The 12-capability architecture, the 8-asset universe,
the Voie D constraint, and the legal floor are all part of this ADR's contract.
Any direction change requires a new ADR (ADR-018+) explicitly superseding this one.

## References

- v4 brief in this conversation (Eliot OK go 2026-05-03)
- 4 research reports : `docs/research/{macro-tools-landscape,data-sources,macro-frameworks,claude-orchestration-patterns}-2026.md`
- Phase 0 retrospective : `docs/PHASE_0_LOG.md`
- New live log : `docs/PHASE_1_LOG.md`
