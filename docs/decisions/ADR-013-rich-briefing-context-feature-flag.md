# ADR-013 — Rich briefing context behind ICHOR_RICH_CONTEXT feature flag

- **Date** : 2026-05-03
- **Status** : Accepted
- **Decider** : autonomous BLOC B (Eliot validated v2 plan)

## Context

The Phase 0 cron-fired briefing path is LIVE end-to-end and proven on
multiple runs. The legacy
[`_assemble_context()`](../../apps/api/src/ichor_api/cli/run_briefing.py)
function pulls only :

- Latest `BiasSignal` per asset (24 h horizon)
- Open warning + critical alerts
- Three TODO placeholder lines

Meanwhile the system has been quietly accumulating real data that the
briefing ignores :

- 160+ `news_items` from RSS (Fed, ECB, BoE, BBC, SEC) — 24/7
- 7+ `polymarket_snapshots` from gamma-api
- 20 556 `market_data` daily bars over the 8 Phase-0 assets, going back
  to 2016 — landed in commit `af38760` (BLOC A)

Wiring all of this into the briefing prompt makes the next briefing
materially better. But the LIVE path is precious — a regression on the
context shape (token overflow, malformed Markdown, schema drift) would
break every cron until we notice.

## Decision

Two-track delivery :

1. **Build a separate context assembler**
   [`apps/api/src/ichor_api/briefing/context_builder.py`](../../apps/api/src/ichor_api/briefing/context_builder.py)
   that pulls bias + alerts + market_data + news + polymarket, with a
   priority-based **token budget** (default 12 000 tokens, ~48 KB) and
   graceful degradation (lowest-priority sections dropped first).
2. **Gate it behind a feature flag** `ICHOR_RICH_CONTEXT=1` :
   - Default OFF → existing legacy assembler runs unchanged. Zero risk
     to the LIVE chain.
   - Per-systemd-unit opt-in : Eliot toggles ON one briefing type at a
     time (`Environment=ICHOR_RICH_CONTEXT=1` in the timer's drop-in)
     after manually inspecting a sample run.
   - When ON, the assembler logs `context.rich_used` with chars +
     token estimate so we can monitor budget adherence.

Section priorities (lower = drop first under budget pressure) :

| Priority | Section                     |
| -------- | --------------------------- |
| 10       | Bias signals (never drop)   |
| 9        | Active alerts               |
| 8        | Market data (close + D/D %) |
| 5        | News                        |
| 4        | Polymarket                  |

## Alternatives considered

- **Replace the legacy assembler outright** — too risky on a LIVE chain
  Eliot depends on. Rejected.
- **Build it but always run it (no flag)** — same problem; flagged so a
  bad day on the new code path doesn't take down briefings.
- **Build a separate "rich" briefing type** — would split the persona,
  the prompt, and the cron timers. Too much surface for marginal value.
- **Use Redis-stored toggle** — overkill for a per-process env var.
- **Token budgeting via tiktoken** — adds a 5 MB dep just for the
  estimate. The 4-chars/token rule is accurate within ±15% on FR/EN
  prose and ±5% on Markdown tables ; good enough for budget planning.

## Consequences

Positive :

- Zero LIVE-path risk : default OFF.
- When ON : Claude sees real news headlines, real polymarket odds, real
  D/D moves on the actual assets — a much richer prompt than today.
- Modular : adding more sources later (FRED via paid key, OANDA M1) is
  one new `_format_*` + one `_fetch_*` away.
- Observable : `context.rich_used` log line carries `chars`, `tokens_est`,
  `briefing_type` for Grafana to scrape.

Negative :

- Two code paths to maintain. Mitigated by promoting rich → default
  once it's been proven for 2 weeks.
- Token budget enforcement could drop a section silently — observable
  via the `context_builder.drop_section` warning log line.
- News content is attacker-influenced (RSS prompt injection) — already
  covered by [RUNBOOK-006](../runbooks/RUNBOOK-006-prompt-injection.md).

## Verification

- 13 unit tests on the format helpers + render
  ([`apps/api/tests/test_context_builder.py`](../../apps/api/tests/test_context_builder.py)).
- All 59 api tests still green (was 46, +13).
- Deployment dry-run : enable on `pre_londres` first
  (lowest-frequency timer), inspect Postgres `briefings.context_markdown`
  for the resulting blob, then promote.

## How to enable

On Hetzner :

```bash
sudo systemctl edit ichor-briefing@pre_londres.service
# Add:
[Service]
Environment="ICHOR_RICH_CONTEXT=1"
```

Then `sudo systemctl daemon-reload`. Next 06:00 Paris fire will use the
rich path. Grep `journalctl -u 'ichor-briefing@pre_londres.service'` for
`context.rich_used` to verify.

## References

- [`apps/api/src/ichor_api/briefing/context_builder.py`](../../apps/api/src/ichor_api/briefing/context_builder.py)
- [`apps/api/src/ichor_api/cli/run_briefing.py`](../../apps/api/src/ichor_api/cli/run_briefing.py)
- BLOC B in [`docs/SESSION_HANDOFF.md`](../SESSION_HANDOFF.md)
