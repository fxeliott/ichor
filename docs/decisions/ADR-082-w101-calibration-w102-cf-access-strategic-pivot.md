# ADR-082 — W101 Calibration scoreboard + W102 CF Access service token + strategic pivot post-W100g audit

**Date** : 2026-05-11
**Status** : Accepted
**Wave** : W101+

## Context

After the W99 → W100g intensive batch (Cap5 STEP-6 e2e shipped,
Dependabot auto-merge w/ cooldown 7d, Socket.dev installed, CF API
token rotated, AGE key SPoF mitigated, HTML guide §8 corrected with
real CF dashboard data), Eliot asked for an honest top-down strategic
audit ("recul ultra-profond, pas de flatterie").

An `ichor-trader` subagent ran a doctrinal-canon audit against the 9
trading invariants. It surfaced findings that warrant a deliberate
strategic pivot in the W101+ roadmap.

## Decision

The next 5 waves (W101 → W105) are re-prioritised as follows :

### W101 — Calibration scoreboard (PRIORITY 0, blocker)

Build the `/v1/calibration/scoreboard` API endpoint + corresponding
`apps/web2/app/calibration/` page exposing :

- Brier score mean + median per (asset, session_type) over windows
  30 d / 90 d / all-time
- Reliability diagram (deciles of predicted probability vs realized
  frequency)
- Coverage (% of realized closes within 80 % CI of magnitude_pips)
- Count of cards generated vs reconciled (gap detection)

**Rationale** : without this surface, Ichor is **scientifically
unverifiable**. The pipeline can produce 32 cards/day but there is no
public way to ask "does it beat naive baseline + 5 %". ADR-017
capability #8 promised this surface ; it is not yet implemented.

Effort estimate : 3-4 dev days. Files :
`apps/api/src/ichor_api/services/calibration_dashboard.py`,
`apps/api/src/ichor_api/routers/calibration.py` (extend),
`apps/web2/app/calibration/page.tsx`,
`apps/api/tests/test_calibration_dashboard.py`.

### W102 — CF Access service token on claude-runner tunnel (PRIORITY 0, security)

`claude-runner.fxmilyapp.com` is currently public without CF Access
enforcement (`require_cf_access=false`). Anyone who guesses the URL
can spam the runner and burn Eliot's Claude Max 20x flat-fee quota.

Action : wire CF Access service token gate on the cfargotunnel ingress.
This was already documented as PRE-1 in ADR-071 (Capability 5 deferral
sequence) but never actioned. Now is the right moment because :

- W99/W100 just rotated the CF API token (W100f) — the new token is
  scoped to Pages:Edit only, so creating a CF Access service token
  needs to be done via dashboard manual.
- Manual creation = ~10 min. Wiring claude-runner config = 5 min
  Hetzner-side.

Effort estimate : 0.5 dev day + 15 min Eliot dashboard.

### W103 — FOMC/ECB tone-shift activation (PRIORITY 1, low-hanging fruit)

`services/cb_tone_check.py` + `cli/run_cb_tone_check.py` have been
shipped and registered as cron timers since 2026-05-06. They are
dormant pending `pip install transformers torch
--index-url https://download.pytorch.org/whl/cpu` in `/opt/ichor/api/.venv`
on Hetzner.

This is **money on the table** : 60+ days since the code was ready, 30
minutes of work to activate. The friction has been "I don't want to
install heavy ML libs on prod" — but FOMC tone is a top-3 signal for
the FX/macro pipeline. Activate it.

Effort estimate : 0.5 dev day (SSH Hetzner + pip install + verify
backfill + register notification).

### W104 — USDCNH PBOC peg proxy v2 (PRIORITY 1, doctrinal correctness)

The current `FX_PEG_BREAK` alert for USDCNH uses `rolling30` on 1-min
bars (`cli/run_collectors.py` L1885-1887), which is a **30-MINUTE**
moving average — NOT a 30-DAY mean as the doctrine prescribes. The
deviation threshold `peg_dev_pct = 1.0%` is absolute, not 1 σ. This
makes the alert silently dormant in practice (it never fires because
the proxy moves with spot).

Fix : either (a) implement 5-day rolling mean on daily bars OR
(b) scrape CFETS daily reference from `chinamoney.com.cn` (PBOC fix
proxy). Re-tune threshold from `1.0% absolute` to `1.0 σ
historical`.

Effort estimate : 2 dev days.

### W105 — Macro quintet PCA orthogonality audit (PRIORITY 2, scientific rigor)

ADR-042 (quartet) + ADR-051 (quintet) added DXY, US10Y, VIX, HY OAS,
MOVE realized vol to the macro stress signal. The "4-of-5 aligned"
threshold assumes axis independence — but these 5 series have
historical pairwise correlations of 0.4 → 0.7. The score
**overestimates** rarity (signal alignment by chance).

Fix : backfill 5 y daily of the 5 series, compute PCA loadings, refit
the threshold using a Mahalanobis-distance approach in 5-D rather
than a count-based 4-of-5. This is closer to how multi-factor risk
models (Barra, Axioma, AQR) actually compute "regime extremity".

Effort estimate : 3 dev days.

## Deferred (out of W101–W105 scope but tracked)

| Wave | Title                                        | Effort | Notes                                                    |
| ---- | -------------------------------------------- | ------ | -------------------------------------------------------- |
| W106 | yfinance redundancy (fallback Alpha Vantage) | 2 d    | Mitigate single-vendor risk on GEX + options + Mag-7     |
| W107 | Magnitude calibration via CRPS               | 2 d    | Beyond Brier — score the magnitude_pips range            |
| W108 | Capability 5 STEP-3..6 finish                | 2 d    | Already 8/8 e2e green (W100), polish only                |
| W109 | Trader-note → invalidation feedback loop     | 3 d    | Measure if Eliot's annotations improve Pass 4 conditions |
| W110 | Post-mortem auto on brier > p95 cards        | 2 d    | Learn from failures systematically                       |

## Dropped permanently

- **W75 WGC quarterly XLSX collector** : Eliot's explicit decision
  2026-05-11. Cadence mismatch (quarterly w/ lag vs Ichor's
  intraday-to-weekly) + existing gold signals already cover the
  actionable portion (FRED price + CFTC TFF + SKEW + DXY +
  real yields). Recorded in CLAUDE.md "Things subtly broken" section.
  Alternatives evaluated (IMF SDDS, CMX, GLD trust) also deferred —
  if the need re-emerges, those are the right re-entry points (free,
  no licensing).

## Reframe needed in marketing copy

The CLAUDE.md slogan **"comme si toutes les meilleures institutions et
hedge funds étaient rassemblé en ce système"** was flagged by the
ichor-trader audit as **over-sold**. Ichor is :

- An **aggregator** of public macro frameworks
- An **LLM synthesis** layer (4-pass orchestrator)
- A **calibration substrate** (Brier scoring against realized outcomes)

It is NOT :

- An alpha-generator (no trade-flow tape, no L2 order book, no
  cross-asset PnL attribution)
- A hedge-fund-collective (no proprietary information edge)

Future copy should describe Ichor as :

> _"Pre-trade context discretionary toolkit, calibrated against
> historical realized outcomes, with explicit invalidation conditions
> and full audit trail for MiFID-compliant reconstruction."_

This wording is honest, sustainable, and matches what the system
actually delivers.

## Open question to Eliot

> "Utilises-tu réellement Ichor pour tes décisions trading aujourd'hui ?"

The answer dictates whether W101 calibration scoreboard is :

- **(a) Critical blocker** — Eliot trades with Ichor but doesn't know
  if it beats gut-feeling → W101 is THE move.
- **(b) Quality-of-life** — Eliot has informal track-record awareness
  → W101 is still high-ROI but not blocker.
- **(c) Project-pivot signal** — Eliot doesn't actively trade with
  Ichor → reconsider whether Phase 2 features in the pipeline
  (collectors, Couche-2 agents, etc.) are polish of an unused
  product. Strategic pause warranted.

The answer is requested in the next conversation turn.

## Consequences

- Roadmap rationalised W101–W105 = 5 strategic moves vs 10+
  opportunistic "nice to have" candidates that were drifting in
  CLAUDE.md "Things subtly broken or deferred" section.
- Honest reframing of self-perception (toolkit, not hedge fund).
- WGC permanently dropped.
- Eliot is asked to honestly self-assess Ichor usage to recalibrate
  forward direction.

## References

- ichor-trader subagent audit 2026-05-11 (full output in conversation
  transcript)
- ADR-017 (boundary), ADR-022 (conviction cap), ADR-029 (audit log),
  ADR-071 (Capability 5 sequence), ADR-077 (MCP wire), ADR-079/080
  (disclosure surface)
- CLAUDE.md "Things subtly broken or deferred" (refactored
  2026-05-11)
