# ADR-109 — Phase 7 streaming-cadence verdict refresh

**Status** : Accepted (2026-06-02)

**Relates to** : ADR-106 (SessionVerdict contract + autonomous 24/7 system),
ADR-085 (Pass-6 scenario decomposition), ADR-017 (no BUY/SELL boundary),
ADR-009 (Voie D), ADR-030 (ResolveCron canonical timer pattern), ADR-108
(full-Opus everywhere).

## Context

Eliot's Prompt*Ichor §6.4 is explicit: Ichor must be **ultra-réactif en temps
réel** — *« Quand un résultat tombe, sort, est publié ou intervient — Ichor
doit réagir immédiatement, prévenir, analyser, mettre à jour »_ — and the
analyses must be _« continues, vivantes … jamais statiques »\_.

Before this ADR, the verdict that the trader looks at was refreshed only by
the **4×/day batch** (`ichor-session-cards@.service`, ~06/12/17/22 Paris) plus
Phase 1's 60 s client-poll (which re-reads the latest card but cannot create a
newer one). So a market-moving event landing at 14:40 — squarely inside
Eliot's 14h-20h NY execution window — would not move the verdict until the
next batch at 17:00. The reasoning cadence, not the ingestion cadence, was the
bottleneck (data is ingested every 1-30 min; the card is regenerated 4×/day).

The 2026-06-02 audit catalogued this as **gap 9** (`ichor_audit_2026-06-02.md`)
and the quantum-leap plan scoped it as **Phase 7**, the only remaining piece.

## Decision

Add a **light, additive, flag-gated, reversible watcher** that runs every
~12 minutes and, for each asset, detects whether a **NEW strong event** has
fired **since that asset's last card** and — if so — regenerates **only that
asset's** card (full 4-pass + Pass-6 Opus, identical to a batch card) and
pushes a notification. It **never touches the 4×/day batch path**.

### Detection — reuse, don't reinvent

Detection reuses `services/session_verdict_builder._assemble_live_triggers`
**verbatim** as the single source of truth for the three event sources and
their gates:

- economic releases with a published `actual` in the last 12 h
  (high/medium impact, asset-relevant currency),
- central-bank speeches in the last 12 h,
- strong-tone news in the last 6 h (FinBERT `|tone_score| ≥ 0.85`).

The watcher post-filters that output to `fired_at_utc > last_card.generated_at`
→ _"a NEW strong event since the asset's last card"_. Zero query duplication;
the currency-relevance map, freshness windows, strong-tone threshold and
ADR-017 description validation all stay in one place.

### Regeneration — reuse the batch path

The regen reuses `cli/run_session_card._run` (`run_one_card`) **verbatim** —
the exact path the batch uses: 4-pass + Pass-6 **Opus** + safety gate +
coherence reconciliation + persist to `session_card_audit` + Redis publish.
The streaming card is byte-for-byte the same shape as a batch card. The regen
window (`session_type`) is the asset's **latest** card window, so the refresh
updates exactly the card `build_session_verdict` (and the Phase 1 60 s poll)
reads.

### Notification

On a successful regen the watcher pushes an **event-keyed** notification via
`push.send_to_all`, mirroring `alerts_runner._maybe_notify`'s contract
(`is_adr017_clean` re-check + `url=/briefing/{asset}` + fail-soft). The body is
the triggering `LiveTrigger.description`, which is already ADR-017-validated.

### Bounding — stateless, durable

- **Per-asset cooldown** (default 45 min): skip an asset whose last card is
  younger than the cooldown. Because every regen **and** every batch advances
  `generated_at`, this self-limits re-fires and respects a just-run batch — no
  cross-fire state required.
- **Per-fire cap** (default 3): at most _N_ assets regenerated per tick; the
  overflow (most-recent-event-first priority) is **logged as a drop** and
  picked up next tick. Never a silent cap.

With a 12-min cron + 45-min cooldown over 6 assets, the system tops out at
~`6 × (60/45) ≈ 8` streaming regens/hour — a deterministic ceiling with no
counter to drift or fail.

### Flagging & cadence

Gated by feature flag `streaming_refresh_enabled` (**default absent → fail-
closed**). CLI `cli/run_streaming_refresh` (exit 0/1/3, `--dry-run`,
`--asset`, `--cooldown-minutes`, `--max-per-fire`). Cron
`register-cron-streaming-refresh.sh` installs a systemd timer
`OnCalendar=*-*-* *:0/12:00 Europe/Paris`, `SuccessExitStatus=0 1`,
`TimeoutStartSec=600`, `Persistent=true`.

## Consequences

- **Voie D preserved**: the regen routes through the Win11 runner; detection +
  push are pure DB reads / web-push. Zero Anthropic API spend. Most ticks find
  no new event and exit having done nothing → **zero marginal Opus** on quiet
  hours; a handful of regens on a high-impact day (NFP/CPI/FOMC).
- **ADR-017 preserved**: the regen reuses the safety-gated card path; the push
  copy is the already-validated trigger description, re-checked defensively.
- **No new schema, no migration, no new dependency.** Bounding is stateless.
- **Opus-budget aware**: the per-asset cooldown + per-fire cap bound the extra
  Opus load; a runner throttle just makes a regen fail (logged drop) and the
  next batch refreshes the card anyway — graceful degradation.
- **Reversible**: flip `streaming_refresh_enabled` to false (or never seed it)
  and the watcher is fully inert; `disable` the timer to stop the cron.

## Alternatives considered

- **Increase `news_nlp` / batch frequency** — blunt, multiplies Opus cost
  across all assets even when nothing happened, and still batch-shaped.
- **WebSocket/SSE push of intra-card deltas** (ADR-106 Stride 7) — larger
  surface, real-time transport; deferred. Phase 7 delivers the reactive
  _content_ (a fresh verdict) first; the live transport is orthogonal.
- **Redis hourly hard-cap counter** — rejected in favour of the stateless
  cooldown+cap composition: fewer moving parts, no Redis-outage failure mode,
  and a deterministic derived ceiling.
- **A dedicated `event_driven` session_type for the regen** — rejected;
  regenerating in the asset's _current_ window keeps the verdict surface
  (which reads the latest card by `generated_at`) consistent and avoids
  introducing a session type that other surfaces may not handle.

## Invariants

- Voie D: no `import anthropic` in the new service/CLI (CI-guarded by
  `test_invariants_ichor.py`).
- ADR-017: the push body passes `is_adr017_clean`; the regen reuses the
  safety-gated persist path.
- Fail-closed: absent/false `streaming_refresh_enabled` ⇒ the CLI returns 1 and
  performs **no** regen and **no** push (pinned by
  `test_streaming_refresh.py::test_cli_flag_off_is_zero_diff`).
- No silent cap: every cooldown/cap/failure decision yields an explicit
  `RefreshOutcome` + structured log line.
