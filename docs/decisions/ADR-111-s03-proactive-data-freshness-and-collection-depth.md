# ADR-111 — S03: proactive data-freshness monitoring + collection depth (per-asset GDELT, newsletters, pre-announcement sentinel)

**Status** : Accepted (2026-06-11)

**Extends** : ADR-110 (which killed the silent-outage class for the
RUNNER — this ADR kills it for the DATA layer), ADR-105 (market-closed
gates, reused as the monitor's false-alarm killer), ADR-104/S03
newsletters layer (expanded), ADR-106 §Carry-forward r166 (whose
3-session validation becomes actually runnable).

## Context

Session-03 re-fire (owner, 2026-06-11). PLAN_DIRECTEUR v4.1 §5 maps it to
**Chantier D (+ newsletters expansion)**. Ground truth audited at source
the same day (7 fresh read-only agents + live prod witness):

1. The collection layer is broad and ALIVE (47 collectors, 102 timers,
   polymarket 9,747 rows/24h, gdelt 1,842/24h, fx_ticks/polygon < 1 min,
   12/12 flags ON) — but **nothing alerts when a table stops moving**.
   The dead-collector class fired repeatedly (COT silently empty for
   weeks; ecb_sdmx/bls/eia persist crashes with clean-looking timers;
   crypto_fear_greed stopped 05-05; live specimens in prod today:
   nyfed_mct 13d, treasury_tic 34d — benign publication lags, but
   nothing could TELL benign from broken).
2. Per-asset geopolitics differentiation (S04, 06-09) is DATA-GATED on
   GDELT density: global-only queries yield 0-1 affinity matches per
   asset per 24h → systematic global fallback. The fix was explicitly
   deferred to S03.
3. The newsletters layer (11 feeds, 06-06) is thin per §5ter-bis; no CAD
   central bank, no official statistics, no energy, no geopolitics feed.
4. "Être prévenu de TOUTES les annonces" (spec S03 verbatim) was
   reactive-only — nothing warned BEFORE a high-impact print.
5. `scenario_invalidation_monitor_enabled` (the one un-armed flag) is
   gated on a ≥3-session empirical validation that could never start:
   the flag check ran before the `--dry-run` branch.

## Decision

Five shippable slices, all Voie-D (zero LLM call added):

1. **Proactive data-freshness monitor** —
   `services/collector_freshness.py` (29-source registry: table,
   timestamp column, expected max-age, criticality tier, ADR-105 market
   gate) + `cli/run_data_freshness_check.py` on a 5-min timer. Emits
   `COLLECTOR_STALE` / `COLLECTOR_ABSENT` / `RSS_FEED_SILENT` through
   the canonical alerts pipeline; exits 2 on the healthy→degraded
   TRANSITION (state file, mirrors runner-health-check) →
   `OnFailure=ichor-notify@`. Market-gated sources are evaluated only
   when their market was open over the entire lookback window (kills
   weekend + Monday-reopen false alarms). **Exit-code policing on
   collector units was rejected**: benign empty sources legitimately
   exit 1; destination-table freshness is the outcome that matters.
   Detection budget: 5-min timer + ≤15-min fast-tier max-age ⇒ a killed
   fx/polygon/polymarket collector alerts ≤ 15 min (Chantier D gate).
2. **Per-asset GDELT slices** — 6 new collector queries (eurozone, UK
   economy, BoC/Canada, RBA/China, S&P, Nasdaq/tech) whose labels carry
   `NEWS_KEYWORDS` vocabulary so `filter_rows_by_asset_affinity`
   crosses `min_required` on real density (the gate itself is NOT
   loosened). Concurrency 4→2 + 2 s politeness delay (GDELT serves real
   429s — verified live 2026-06-11; ~672 req/day total, well under
   observed tolerance).
3. **Newsletter depth pass** — +10 fetch-verified feeds (BoC, SNB, BEA,
   StatCan, ONS, FXStreet, EIA, CNBC economy, OilPrice, Crisis Group)
   - RSS 1.0/RDF parser branch (BoC requires it) + ForexLive
     post-rebrand canonical URL. Rejected after LIVE checks, never
     guessed: BLS/ReliefWeb/Foreign Affairs (403), Treasury (timeouts),
     Reuters/AP (no public RSS), Fed press_monetary (dedup-duplicate of
     press_all), Eurostat news (empty skeleton).
4. **Pre-announcement sentinel** — `alerts/event_sentinel.py` +
   `cli/run_event_sentinel.py` (10-min timer): high-impact
   `economic_events` in the next 60 min on USD/EUR/GBP/CAD →
   `ECO_EVENT_IMMINENT` (critical = web-push tier). Event-CLUSTER dedup
   via `source_payload.event_key` (the generic 2h (code, asset) window
   would mask a 16:00 print behind a 14:30 cluster). The calendar's
   timezone was verified against prod BEFORE building on it (US CPI
   stored `14:30+02` = 08:30 ET ✓).
5. **Validation harness unblocked** — `--dry-run` now evaluates with
   the flag OFF (read-only, always rolled back; journalctl is the
   validation log). Persisting runs stay strictly flag-gated. Arming
   remains an owner/post-validation step — NOT armed by this ADR.

Catalog grows 57 → **61** (`assert_catalog_complete` updated; +3
DATA_FRESHNESS, +1 EVENT_SENTINEL).

## Consequences

- The 06-10 P0 class (silent total outage) is now covered on BOTH
  halves: runner (ADR-110) and data tables (this ADR).
- Per-asset geopolitics differentiation un-gates as density accumulates
  — re-witness `_section_geopolitics(asset)` `applied=True` after a few
  collection days.
- The trader gets a push BEFORE every high-impact print on the traded
  universe's currencies (worst-case lead 50-60 min). ADR-017 untouched:
  calendar copy is descriptive, never directional.
- New steady-state noise floor: stale WARNING-tier alerts (slow series)
  appear in /v1/alerts without notify spam (2h dedup + warning tier not
  pushed). Thresholds live in ONE place (the registry) for tuning.
- Deferred, named: SSE push (poll stays acceptable per plan), Kalshi/
  Manifold data_pool consumers + cross-market consensus (Chantier C
  dimension work), Prometheus rules (systemd+notify path meets the gate
  without a new infra layer — revisit if alert routing outgrows ntfy).
- Known residual (pre-existing, verifier finding #5): `check_metric`
  web-pushes BEFORE the caller's commit — if the commit later fails, the
  push has left and the dedup row hasn't landed (possible re-push next
  tick). The realistic trigger on this branch (VARCHAR(16) overflow) is
  fixed at the source + a defensive truncate; moving to post-commit
  notification means changing the contract for 15+ existing callers —
  deliberately deferred to a dedicated pass.

## Verification

Pure-logic tests (registry invariants, minute-granular classification,
ADR-105 gating incl. Monday-reopen, transition exit contract, event
clustering/dedup, CLI flag contract) + full api suite + runtime
witnesses on prod (deploy section of SESSION_LOG_2026-06-11-s03).
