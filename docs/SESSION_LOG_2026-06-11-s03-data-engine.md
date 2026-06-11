# SESSION LOG — 2026-06-11 · Session 03/09 re-run · Data-engine slice (Chantier D + newsletters)

> Master-plan reference: [`PLAN_DIRECTEUR.md`](PLAN_DIRECTEUR.md) v4.1 §5
> session-file execution mapping — **03 → Chantier D (+ newsletters
> expansion)**. PR [#225](https://github.com/fxeliott/ichor/pull/225)
> squash-merged → `main 2b7f2de`. ADR:
> [`ADR-111`](decisions/ADR-111-s03-proactive-data-freshness-and-collection-depth.md).

## 0 · Verdict

The S03 data layer was broad and ALIVE but **blind to its own decay** and
**reactive-only**. Five Voie-D slices (zero LLM call added) shipped,
deployed and runtime-witnessed the same day: a proactive 29-source
freshness monitor (the Chantier D "killed collector alerts < 15 min" gate,
data half), per-asset GDELT slices (un-gates the S04 geopolitics
differentiation), a +10-feed world-newsletter depth pass with RSS 1.0/RDF
support, a pre-announcement sentinel (critical web-push BEFORE every
high-impact print on USD/EUR/GBP/CAD), and the un-blocking of the
scenario-invalidation 3-session validation harness. An independent
fresh-context verifier returned 9 findings — **ALL folded pre-merge**,
including one true BLOCKER.

## 1 · Ground truth first (audit before code)

- 7 fresh read-only agents (`wf_e796c2bd`, 843k tokens, 288 tool uses)
  over 7 axes + a live prod sweep (timers, 12/12 flags, freshness of 44
  tables). Key facts: collection alive (polymarket 9,747 rows/24h, gdelt
  1,842/24h, fx_ticks < 1 min) but ZERO staleness alerting; GDELT
  global-only (the S04 06-09 deferral); newsletters thin (11 feeds);
  "être prévenu de TOUTES les annonces" reactive-only; the
  `--dry-run` of scenario-invalidation gated BEHIND the very flag its
  validation was supposed to arm.
- Two parallel web researches with live verification: 18 RSS feeds
  VERIFIED by real fetch (BLS/BoE/ReliefWeb 403, Treasury timeout,
  Reuters/AP dead — rejected, never guessed); GDELT DOC 2.0 still
  keyless, real 429s observed, theme names verified, polite budget
  computed (~672 req/day at 14 queries/30 min).
- Calendar timezone verified against prod BEFORE building the sentinel
  on it: US CPI stored `14:30+02` = 08:30 ET ✓, BoC `15:45+02` ✓.

## 2 · Shipped (7 commits, squash `2b7f2de`)

1. **Per-asset GDELT slices** — 6 new queries (eurozone, UK economy,
   BoC/Canada, RBA/China, S&P, Nasdaq/tech); labels carry NEWS_KEYWORDS
   vocabulary so `filter_rows_by_asset_affinity` crosses `min_required`
   on real density (the gate itself untouched). Concurrency 4→2 + 2 s
   politeness delay.
2. **Newsletter depth pass** — +10 fetch-verified feeds (BoC, SNB, BEA,
   StatCan, ONS, FXStreet, EIA, CNBC economy, OilPrice, Crisis Group);
   RSS 1.0/RDF parser branch (BoC needs it); ForexLive post-rebrand
   canonical URL (name kept → dedup history holds). 21 feeds total.
3. **Proactive data-freshness monitor** — `services/collector_freshness.py`
   (29-source registry, minute-granular, ADR-105 market gating incl. the
   Monday-reopen false-alarm kill) + `cli/run_data_freshness_check.py`
   (5-min timer, COLLECTOR_STALE/COLLECTOR_ABSENT/RSS_FEED_SILENT via the
   canonical pipeline, healthy→degraded transition → exit 2 →
   `OnFailure=ichor-notify@`). Exit-code policing rejected by design
   (benign exit-1 collectors); destination-table freshness is the truth.
4. **Pre-announcement sentinel** — `alerts/event_sentinel.py` +
   `cli/run_event_sentinel.py` (10-min timer, horizon 60 min,
   `ECO_EVENT_IMMINENT` critical = web-push tier, event-CLUSTER dedup via
   payload `event_key`).
5. **Validation harness un-blocked** — `--dry-run` evaluates flag-OFF
   (read-only, always rolled back); persisting runs stay flag-gated.
6. **Alerts import-cycle killed for good** — `AlertDef`/`AlertHit` moved
   to leaf `alerts/defs.py` (re-exported; zero caller touched); the r165
   TYPE_CHECKING/lazy-import workaround deleted; CodeQL error → 0 open
   alerts. Catalog 57 → **61** (+3 freshness, +1 sentinel).

## 3 · Independent fresh-context verifier (mandatory protocol) — 9/9 folded

42-tool adversarial pass, verdict NOT-READY, all folded pre-merge:
**BLOCKER** `cleveland_nowcast` source_key (17 chars) would overflow
`alerts.asset` VARCHAR(16) and crash the sweep at exactly the moment the
source degrades → renamed + hard limit in `FreshnessSpec.__post_init__` +
defensive 16-char clamp in `_persist_hit` + registry invariant test.
**MAJOR** fx_ticks/polygon probes moved to hypertable partition keys
(`ts`/`bar_ts` — chunk exclusion; `max(created_at)` would full-scan ~1.5M
rows/day every 5 min). **MAJOR ×2** web pushes are not rollbackable —
`notify=False` propagated on every dry-run/validation path (sentinel +
scenario-invalidation; without it every flag-OFF validation run would
re-push the same hard invalidation). MINOR ×2 + NIT ×2 (dead nfib entry,
ADR count, title copy, accent). Residual pre-existing push-before-commit
pattern documented in ADR-111.

## 4 · Verification (runtime, not "it compiles")

- Tests: **3,267 pass / 0 fail** full api suite (local + verifier re-run)
  incl. 50 new S03 tests; mypy 0 new on every touched module; ruff clean;
  15/15 pre-commit hooks per commit; CI 100% green incl. CodeQL (0 open
  code-scanning alerts after the cycle break).
- **Deploy**: `redeploy-api.sh` → healthz 200 + sample 200, backup
  `ichor_api.20260611-095259`. Both timers registered + armed
  (`ichor-data-freshness-check` 5 min, `ichor-event-sentinel` 10 min).
- **Witness — freshness monitor first prod run (11:54)**: 29 sources
  checked · 0 degraded · 0 false positives · 13 silent feeds correctly
  split: 10 = the new feeds (not yet fetched at that minute) + **3 true
  detections on the first tick: `boe_news` (the known 403 WAF class),
  `sec_press`, `wsj_markets`** → 1 RSS_FEED_SILENT alert persisted.
- **Witness — sentinel honest-quiet (11:55)**: 2 runs, horizon 60 min,
  0 alerts (ECB 14:15 not yet inside the window) — no fabricated noise.
- **Witness — validation harness (11:57)**: flag-OFF dry-run = VALIDATION
  MODE, evaluates the day's real cards, detects **2 real HARD
  invalidations (NAS100 + GBP, bucket crash_flush)**, rolled back, exit 0,
  **zero push emitted** (the verifier-#4 fix earning its keep on its very
  first run). Arming evidence now accumulates in journalctl.
- **Witness — kill-test (Chantier D gate) — PROVEN**: see §5.
- **Witness — natural sentinel fires (ECB day) — PROVEN ×3**: see §5.

## 5 · Same-day runtime witnesses (verbatim, recorded at close)

**Kill-test (the falsifiable Chantier D gate).** Polymarket timer
deliberately stopped 12:19:37 (last snapshot 12:16:44; 30-min window →
stale from 12:46:44). Tick 12:44:17: still fresh (no false positive).
Tick 12:49:17:

```
alert.triggered  asset=polymarket code=COLLECTOR_STALE value=1.08
freshness · 29 sources checked · 1 degraded (1 critical) · 1 alerts emitted
  DEGRADED [critical] polymarket: stale age=0.5h (max 0.5h)
freshness: TRANSITION/renotify — critical sources degraded: polymarket
```

→ **detection 2 min 33 s after the threshold crossing** (5-min tick as
designed; the 15-min fast tier detects a killed fx/polygon collector
< 15 min by the same arithmetic). systemd `Result=failed → Triggering
OnFailure= dependencies` recorded in `/var/log/ichor-failures.log`;
2-hourly re-notify witnessed exactly on schedule (alerts at 12:49 →
14:51 "2.6h" → 16:53 "4.6h" — no 5-min spam). Timer restored; fresh
snapshot immediately after (a first kill-test attempt earlier was
aborted by the operator's own capped wait — lesson recorded in memory:
never cap a temporal witness's wait).

**Pre-announcement sentinel — three natural fires on ECB day.**
13:16:22 `[EUR] T-59min — Main Refinancing Rate; Monetary Policy
Statement` (cluster of 2 prints = ONE alert, `EUR@2026-06-11T12:15Z`);
13:26 tick: 0 alerts (event_key dedup — no re-spam); 13:36:24 `[USD]
T-54min — Core PPI m/m; PPI m/m`; 13:46:29 `[EUR] T-59min — ECB Press
Conference` — **a second EUR cluster 30 min after the first, alerted
separately**: exactly the case the generic 2h (code, asset) dedup would
have masked, proving the event-cluster design in prod.

**Feeds.** statcan_daily 0 → **342 rows** after the #226 Atom-xhtml
title fix (first fetch 12:45). The monitor's silent-feed list converged
13 → 5 → 3 as the new feeds delivered; the steady-state 3 (`boe_news`,
`sec_press`, `wsj_markets`) are REAL upstream issues, surfaced by the
monitor on its first day.

**GDELT per-asset (cumulative day one).** All 6 slices persist:
nas100_nasdaq_tech 153 · usdcad_boc_canada 66 · spx500_spx_us_equities
48 · eurusd_eurozone 33 · audusd_rba_china 28 · gbpusd_uk_economy 7
rows — the density the S04 geopolitics differentiation was gated on is
now accumulating.

**Ops note (not S03):** `ichor-session-cards@ny_mid` failed at 18:31
(= the 17:00 batch hitting its 5400 s wall) and **the S02 notify path
caught it** — the silent-outage class stays dead; xhigh batch duration
vs wall remains the S02 passive watch item.

## 6 · Invariants held

ADR-017 (4 new alert templates pass `is_adr017_clean`, verifier-confirmed;
descriptive calendar copy only), Voie D (zero `import anthropic`; all five
slices are pure SQL/HTTP — zero LLM call added), no Alembic migration,
watermark/audit untouched, Couche-2 untouched. **ZERO Anthropic API
spend.** Engine framing per ADR-110 (Opus 4.8 xhigh), confirmed by the
owner in-session.

## 7 · Deferred, named (no silent drops)

SSE push (poll acceptable per plan §4.6) · Kalshi/Manifold data_pool
consumers + cross-prediction-market consensus (Chantier C dimension work)
· Prometheus rule files (systemd+notify meets the gate; revisit if
routing outgrows ntfy) · post-commit notification refactor (15+ callers,
dedicated pass) · `sec_press`/`wsj_markets` silent-feed root-cause (NEW —
surfaced by the monitor's first run) · `scenario_invalidation_monitor_enabled`
arming (owner gate after ≥3-session validation — evidence now
accumulating).
