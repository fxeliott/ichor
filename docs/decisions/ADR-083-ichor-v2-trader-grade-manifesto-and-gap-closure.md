# ADR-083 — Ichor v2 : trader-grade manifesto + gap closure roadmap (W101-W112)

**Date** : 2026-05-11
**Status** : Accepted
**Wave** : W101+ — supersedes ADR-082 (extends, not contradicts)

## Context

After the 2026-05-11 strategic-pivot ADR-082 was committed, Eliot
clarified his exact use case and trading scope in conversation. Key
revelations (verbatim) :

- Ichor is **not currently used** because not finished. Objective :
  Ichor must become **90 % of trading analysis** (the 10 % technical
  remains Eliot on TradingView).
- Specific traded assets (NEW info 2026-05-11) : **EURUSD, GBPUSD,
  USDCAD, XAUUSD, NAS100, SPX500** (6 assets).
- The system must cover all of : **fondamental + macroéconomie +
  géopolitique + corrélations + volume + sentiment** with explicit
  output shape **"indications directionnelles + % + impact +
  niveaux clés"** — NEVER signals (no TP/SL/BUY/SELL).
- Vision : "the ultimate dream tool for any trader". Honest, but the
  ADR-082 reframe holds : Ichor = pre-trade context discretionary
  toolkit, not alpha-gen / hedge-fund collective.

A 2-pronged audit was commissioned :

1. **Vision historical audit (researcher subagent)** — reconstructed
   the 2026-05-04 verbatim quote and tracked the asset universe
   drift, dimension coverage, output format gap.
2. **Perplexity vs alternatives audit (researcher subagent)** —
   evaluated web-research automation options compatible with Voie D
   (ADR-009).

Findings consolidated below ; 8 gaps surfaced + clear backend choice.

## Decisions

### D1. Asset universe rationalised : 6 cards (was 8)

**Before (ADR-017)** : 8 session-cards (EUR, GBP, JPY, AUD, CAD, XAU,
US30, US100) + 8 tracked-no-card (incl. SPX500, DXY, VIX, …).

**After (ADR-083 supersedes for trade prioritisation)** :

- **6 active cards** (Eliot's actual trade list) : EURUSD, GBPUSD,
  USDCAD, XAUUSD, NAS100, **SPX500** (promoted from tracked to
  carded).
- **2 deprioritised** : USDJPY, AUDUSD → kept in tracked-no-card if
  cheap, else dropped (cost-benefit per W104).
- **Tracked-no-card (data context only)** : DXY, VIX, 10Y/2Y, TIPS,
  WTI, BTC, EUR/GBP — unchanged.

Rationale : avoid over-coverage on assets Eliot doesn't trade ;
include SPX500 which currently has no card despite being a top-6 traded
asset. Pipeline cost saving (~25 % fewer LLM calls) + better fit to
real use case.

### D2. 7-scenario probabilistic output (Pass 6 NEW)

**Promise (ICHOR_PLAN.md:209-217, never delivered)** : per asset,
output 7 probability-weighted scenarios with triggers + targets +
invalidation per scenario : `crash_flush / strong_bear /
mild_bear / base / mild_bull / strong_bull / melt_up`.

**Current state** : `session_card_audit` carries 1 `bias_direction` +
1 `conviction_pct` + 1 `magnitude_pips`. Single-scenario view.

**Decision** : add **Pass 6 — Scenario Decomposition** to the
orchestrator. Each session-card now persists a JSONB column
`scenarios[7]` with shape :

```json
[
  {"name": "crash_flush", "p": 0.05, "trigger": "...", "target_pips": -250, "invalidation": "..."},
  ...
  {"name": "melt_up", "p": 0.03, "trigger": "...", "target_pips": +300, "invalidation": "..."}
]
```

Sum of probabilities = 1.0 (CI-guarded ADR-081 extension). Base case
`p` weighted toward median magnitude. Cap-95 on conviction still
applied (the `bias_direction` is derived from argmax of scenarios).

**Wave** : W105 (5-7 days dev).

### D3. "Niveaux clés" non-technical surface (NEW)

**New requirement 2026-05-11** : output must include "niveaux clés".

**Interpretation** : NOT technical analysis levels (Eliot does that
on TradingView). Instead, **non-technical / fundamental price
levels** that act as macro/microstructure switches :

- **Option gamma flip levels** (SqueezeMetrics dealer GEX) — already
  collected per ADR-066 `gex_yfinance` for NAS100/SPX500. Surface
  the flip price.
- **Peg break thresholds** : HKMA hard 7.80 ; PBOC daily fix
  (CFETS) ± 2 σ band per W104 fix.
- **Liquidity gates** : Fed TGA / RRP balance thresholds (FRED
  WTREGEN, RRPONTSYD), W2W changes.
- **Polymarket decision thresholds** : binary contract resolution
  prices for monitored macro events.
- **VIX / SKEW regime switches** : per ADR-044 + ADR-055 thresholds.
- **HY OAS regime switches** : BAMLH0A0HYM2 historical percentiles
  (90 %, 99 %).

**Output shape** : new `key_levels[]` array per session-card
JSONB :

```json
[
  {"asset": "NAS100", "level": 19850, "kind": "gamma_flip", "side": "above_long_below_short", "source": "SqueezeMetrics 2026-05-11"},
  {"asset": "USDCNH", "level": 7.245, "kind": "pboc_fix_+2sigma", "source": "CFETS 2026-05-11"},
  ...
]
```

**Wave** : W106 (4-5 days dev).

### D4. Living Analysis View frontend (NEW)

**Problem** : `session_card_audit` is JSON, not human-consumable.
`apps/web2` has 41 routes but no single dashboard that gives a
trader the gestalt view : _"what should I know before opening
positions for the EUR/USD London-Open session today ?"_

**Decision** : `apps/web2/app/analysis/[asset]/[session]/page.tsx`
new route showing :

1. **Header** : asset, session type, generated_at, conviction_pct
   (color-coded), bias_direction.
2. **7-scenario probability bars** : visual stacked bar with each
   scenario's `p` weighted, hover for trigger/target/invalidation.
3. **Drivers/mechanisms** : Pass 2's `mechanisms[]` rendered as
   bullet list with source attribution.
4. **Key non-technical levels** : `key_levels[]` rendered as
   horizontal lines on a small price strip (last 24 h spot price
   from Polygon WS).
5. **Invalidation conditions** : Pass 4's
   `InvalidationConditions.conditions[]` as a checklist with
   horizons.
6. **Cross-asset matrix snapshot** : ADR-075 6-dim macro state
   summary, color-coded.
7. **Polymarket implied probabilities** : top 3 monitored events
   most relevant to this session.
8. **Calibration footer** : link to W101 scoreboard for this
   (asset, session_type) — "your Brier over last 90 d : 0.18 ;
   reliability : 78 %".

**Tech stack** : Next.js 15 RSC + motion 12 + Tailwind v4 (existing).
Server-side data fetch from `/v1/sessions/<asset>/<session>/latest`

- `/v1/calibration/scoreboard?asset=…`.

**Wave** : W107 (5-7 days dev).

### D5. Web-research backend : SearXNG self-hosted (NOT Perplexity)

**Audit findings (researcher subagent 2026-05-11)** :

| Option                          | Annual cost   | Voie D             | Volume capacity         |
| ------------------------------- | ------------- | ------------------ | ----------------------- |
| **SearXNG self-host Hetzner**   | $0 marginal   | ✅                 | Unlimited               |
| **Serper.dev free tier**        | $0 ≤ 2 500/mo | ✅ if free         | 30 % of need            |
| **Perplexity Pro**              | $240          | ❌ ambiguous       | 200-500/mo insufficient |
| **Anthropic `web_search` tool** | metered       | ❌ violates Voie D | —                       |

**Decision** : Deploy **SearXNG Docker** on Hetzner. Expose via new
MCP tool `web_search_searxng` on `apps/api` + claude-runner. Plug into
Couche-2 agents (cb_nlp, news_nlp, sentiment, positioning, macro)
and W105 Pass 6 scenario_decompose.

**Architecture** :

```
Couche-2 agent / Pass 6
  → MCP tool web_search_searxng (Cap5 pattern, ADR-077)
    → apps/api /v1/tools/web_search (NEW endpoint, audit-first per ADR-077)
      → SearXNG Docker (Hetzner, behind Redis cache)
        → 70+ search engines (DDG, Brave, Bing, arXiv …)
```

**Wave** : W103 (2 days dev). Includes :

- Ansible role `searxng` (mirror of `n8n` / `langfuse` patterns).
- Redis caching (24 h TTL per query) to dedupe.
- Rate-limit + circuit-breaker (max 5 concurrent per agent).
- Audit row in `tool_call_audit` per call (ADR-077).
- Fallback Serper.dev free if SearXNG returns CAPTCHA (rare under
  500 req/d).

### D6. Vision reframe : keep ADR-082 wording

Stick with ADR-082's honest reframe :

> _"Pre-trade context discretionary toolkit, calibrated against
> historical realized outcomes, with explicit invalidation conditions
> and full audit trail for MiFID-compliant reconstruction."_

But add the **6-dimension coverage promise** to the public
description : fondamental + macroéconomie + géopolitique +
corrélations + volume + sentiment. Each dimension must have at least
one named data source feeding the data_pool (current state confirmed
in the audit : all 6 have at least partial coverage).

### D7. Deferred decisions

- **Fundamental entreprises NAS/SPX** (per-company SEC EDGAR, earnings,
  insiders) — remains ICHOR_PLAN.md Phase 4. Re-evaluate after W107
  Living View ships and Eliot has tactile feedback on what's
  missing.
- **CB intervention probability** (VISION_2026.md delta D) — keep
  in W112 backlog.
- **BERTopic narrative tracker** (VISION_2026.md delta J) — backlog,
  not blocking.

## Revised W101-W112 roadmap

| Wave     | Title                                                                 | Effort               | Owner      | Status                                                    |
| -------- | --------------------------------------------------------------------- | -------------------- | ---------- | --------------------------------------------------------- |
| W101     | Calibration scoreboard                                                | 3-4 d                | Claude     | from ADR-082, P0                                          |
| W102     | CF Access service token (`*.fxmilyapp.com`)                           | 0.5 d + 15 min Eliot | joint      | from ADR-082, P0                                          |
| **W103** | **SearXNG MCP web_search backend**                                    | **2 d**              | Claude     | **NEW ADR-083, P1**                                       |
| **W104** | **Asset universe align : 6 cards (add SPX500, deprio USDJPY/AUDUSD)** | **1 d**              | Claude     | **NEW ADR-083, P1**                                       |
| **W105** | **Pass 6 scenario_decompose (7 scenarios)**                           | **5-7 d**            | Claude     | **NEW ADR-083, P0**                                       |
| **W106** | **`key_levels[]` non-technical surface**                              | **4-5 d**            | Claude     | **NEW ADR-083, P0**                                       |
| **W107** | **Living Analysis View frontend**                                     | **5-7 d**            | Claude     | **NEW ADR-083, P0**                                       |
| W108     | FOMC/ECB tone-shift activation                                        | 0.5 d                | Claude+SSH | from ADR-082, P1                                          |
| W109     | USDCNH peg proxy v2                                                   | 2 d                  | Claude     | from ADR-082 — DEPRIORITISED (Eliot doesn't trade USDCNH) |
| W110     | Volume microstructure expansion (Lee-Ready, Kyle, Amihud)             | 5 d                  | Claude     | NEW ADR-083, P2                                           |
| W111     | Macro quintet PCA orthogonality                                       | 3 d                  | Claude     | from ADR-082, P2                                          |
| W112     | CB intervention probability                                           | 4 d                  | Claude     | NEW ADR-083, P2                                           |

**Total** : ~35-45 dev days Claude autonomous + ~30 min Eliot dashboard
(CF Access + Hetzner SSH triggers).

## Consequences

- **Roadmap clarity** : 12 waves with explicit Eliot deliverable per
  wave. Trader-grade output by W107.
- **Cost** : $0 incremental (Voie D respected). Hetzner VPS already
  budgeted.
- **Risk** : Pass 6 + Pass 4 + Pass 5 may push the 4-pass pipeline
  beyond CF Tunnel 100 s edge cap (ADR-023 Haiku low constraint).
  Mitigation : Pass 6 runs as **async polling** (ADR-053 pattern
  already deployed).
- **Vision honesty** : Ichor stops being "hedge fund collective" in
  marketing copy and becomes "trader-grade pre-trade analysis tool"
  — accurate, sustainable, defensible.
- **Backward compat** : `session_card_audit` schema extended with
  `scenarios JSONB`, `key_levels JSONB` (nullable) — old cards stay
  readable, migrations non-blocking (migration 0039 candidate).

## Open question

The W101-W112 plan is dense (~35-45 days). Eliot should confirm :

- **Order of waves W101-W107** : default order is the priority
  matrix above (P0 = W101+W102+W105+W106+W107 ; P1 = W103+W104+W108 ;
  P2 = W110+W111+W112).
- **Start point** : recommend W102 (CF Access — 15 min real work + 0.5 d
  Claude) FIRST because it closes a security risk (claude-runner
  public exposure), then W103 (SearXNG — unblocks Couche-2 web
  research without Voie D violation), then W101 (calibration —
  measures everything that comes after).

## References

- Verbatim Eliot 2026-05-04 quote : `D:\Ichor\docs\SESSION_LOG_2026-05-04.md:42-81`
- Verbatim Eliot 2026-05-11 clarification : in-conversation,
  archived per session backup hook.
- ADR-009 Voie D, ADR-017 boundary, ADR-023 Couche-2 Haiku,
  ADR-071 Cap5 deferral, ADR-077 MCP wire, ADR-081 invariants,
  ADR-082 strategic pivot.
- ICHOR_PLAN.md:209-217 (7 scenarios promise).
- VISION_2026.md:34-78, 136-145 (deltas A, D, J).
- 2 researcher subagent audits 2026-05-11 (full output in conversation
  transcript).
