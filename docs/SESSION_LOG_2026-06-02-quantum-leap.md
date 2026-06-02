# Session log — 2026-06-02 · Quantum-leap (make Ichor truly _alive_)

> Eliot re-read his full vision (Prompt*Ichor v3), had it challenged hard → evidence-based
> audits → **9 gaps** → a sequenced **7-phase master plan** (`ichor_quantum_leap_plan.md`,
> audit `ichor_audit_2026-06-02.md`). Méta-read: Ichor is built ~85% but "one flag-flip /
> one cable / one page away from being genuinely \_alive*" at the spot Eliot looks. Eliot
> **authorized everything** (Tier A + all Tier B + "do even more"). This log records the
> execution, phase by phase. Voie D + ADR-017 held throughout; ZERO Anthropic spend.

---

## Phase 0 — Record the repo, and a critical pipeline rescue

### 0.a — Doc-debt catch-up: 06-01 evening (London + freshness) was shipped but unrecorded

The prose record (`CLAUDE.md` "Last sync" = 2026-05-30) did not mention three features that
shipped + deployed + merged on 2026-06-01 evening (branch `claude/agitated-bhabha-e0dde0`,
merged via **PR #162 → main `d683e3b`**). Recorded here to close the gap:

- **Premium coach refonte** (`b9e66a1`, `107c490`) — vibrant multi-hue OKLCH design system,
  cockpit landing, ~26 components scrubbed of model/version jargon → plain coach FR (§6.9).
- **§6.2 London-morning read** (`ff77438`, `f971d8b`) — `GET /v1/london-session/{asset}`
  - `<LondonSessionPanel>`; equity indices honestly suppressed (no London session). Witnessed
    LIVE on prod (EUR_USD = real data; SPX500 = coherent structural absence).
- **Apex honest freshness gate** (`6a30fe8`) — `<VerdictFreshnessBanner>` (stale/absent) above
  the verdict, gated on `card.generated_at` via `deriveFreshness`.

Validation at the time: api 16 London tests + 48 ADR-081 invariants; web2 tsc 0 / eslint 0 /
**vitest 502/502** / next build. All LIVE on Hetzner.

### 0.b — 🔴 Pipeline rescue: the Win11 runner was down → cards were 1–3 days stale

On opening, the live pipeline was **broken** (the exact failure class Eliot keeps catching):

- **Root cause**: the Win11 `claude-runner` (port 8766) was **down**. Its launcher pointed
  `ICHOR_RUNNER_CLAUDE_BINARY` at `C:\Users\eliot\.local\bin\claude.exe`, which no longer
  exists (the native installer was removed; `claude` is now the npm-global bundle at
  `…\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe`). The runner crashed with
  `FileNotFoundError [WinError 2]`, the Startup folder was empty, and `create_subprocess_exec`
  can't launch a `.cmd` shim — so the whole Couche-2/briefing pipeline died silently. Today's
  06:01 `pre_londres` cron fired but generated **zero cards**; the latest card was 06-01 17:25.
- **Fix 1 (binary + persistence)**: relaunched uvicorn against the correct native `claude.exe`;
  re-installed the durable auto-detecting `.bat` (it already probes the 3 known install
  locations) into the Startup folder so a reboot can't re-break it. `claude_cli_available:true`
  through the tunnel from Hetzner.
- **Second failure — the 502 race**: with the runner back, full Opus cards still died at the
  async poll with `502 Bad Gateway`. cloudflared logs showed `EOF` from the origin during a
  running subprocess. **Diagnosis**: uvicorn closes idle keep-alive connections after **5s**
  by default; the orchestrator polls every **5s**, so cloudflared reused a connection exactly
  as uvicorn closed it → EOF → 502 → the card aborted mid-generation. (Healthz / one-off GETs
  worked because there was no sustained 5s poll cycle to hit the race.)
- **Fix 2 (server)**: launch uvicorn with `--timeout-keep-alive 75` (≫ the 5s poll interval).
- **Fix 3 (client, defense-in-depth)**: the async poll loop now tolerates transient tunnel
  blips (5xx/52x + dropped connections) up to `_MAX_CONSECUTIVE_POLL_ERRORS` in a row instead
  of aborting a 200s card on a 1s hiccup; a successful poll resets the counter; 4xx (404
  expired / 401 auth) still aborts. Adds `test_runner_client_async.py` (6 tests — the async
  polling path had **no** coverage before).

**Real witness (the lesson 29/05 standard — verify rendered content, not "it compiles")**:
a full **4-pass + Pass-6** EUR_USD card generated end-to-end with **0× 502** (poll_count 7–13
per pass). Fresh card persisted: `EUR_USD pre_ny`, bias=long, conviction=27, **7 scenarios**,
**11 key levels**.

Shipped as **PR #163 → main `ffd2ba8`** (`fix(infra): restore claude-runner pipeline
reliability (keep-alive + poll retry)`). Brain deployed to Hetzner (healthz 200). ichor_brain
suite **108 passed**, ruff clean.

---

## Phases 1–7 (appended as each lands)

### Phase 1 — The apex verdict is alive (gaps 1, 2, 7) — SHIPPED + DEPLOYED + WITNESSED

The NY-session verdict is the most-looked-at surface, yet it was inert. Three fixes (PR #165 → main):

- **A1 real live_triggers** (was hardcoded `[]`). New async `_assemble_live_triggers` in
  `session_verdict_builder.py` sources REAL recent data (read-only, no LLM): economic releases
  with a published actual under 12h → `economic_release`; central-bank speeches under 12h →
  `central_bank_speech`; strong-tone news (FinBERT score magnitude ≥ 0.85) under 6h →
  `news_headline`. Every trigger `tests` the verdict (honest — no fabricated directional
  confirms/invalidates, doctrine #11). Scenario invalidations are NOT re-emitted (the panel
  already renders them). Wired into both verdict paths; fail-open per source; each trigger built
  in try/except so an ADR-017-tripping headline is skipped not raised; sorted desc, cap-10.
- **A2 60s live-refresh**: `<SessionVerdictPanel>` client-polls the verdict every 60s (Page
  Visibility + AbortController), seeded from SSR, keeps last-good on null so the apex never blanks.
- **A4 conviction gauge on the apex**: the radial `<ConvictionGauge>` is wired into the apex chip
  (direction → tone), giving the text-only verdict a visual anchor.

Validation: new `test_session_verdict_live_triggers.py` (12) + backend targeted 82 passed; web2
tsc 0 / eslint 0 / vitest 506 / next build OK. Witness: `/v1/verdict/session-ny/EUR_USD` returns
**8 real triggers** (news + CB speeches, all `tests_verdict`, source-stamped, ADR-017-clean); the
public `/briefing/EUR_USD` SSR HTML renders the "Déclencheurs en direct" block + the gauge SVG, 0
error boundary.

### Phase 2 — Real-time trader notifications (gap 5) — SHIPPED + DEPLOYED + WITNESSED

The 33-entry alert catalog persisted hits to the DB and stopped; nothing reached the trader.
Web-push existed server-side (VAPID + pywebpush + Redis) but was only fired for cartes-prêtes and
web2 had no way to subscribe. Now (PR #166 → main):

- **Backend**: `alerts_runner` calls `_maybe_notify` after persisting each hit (both
  `check_metric` and `check_scenario_invalidations`). Only `critical` fires (hard scenario
  invalidations + crisis-level macro alerts) so the existing 2h per-code dedup bounds spam.
  ADR-017: the copy is the curated catalog text, re-checked with `is_adr017_clean`; fail-soft so a
  push failure never breaks alert persistence.
- **Frontend**: new `public/sw.js` (push + notificationclick), `lib/push.ts` (register SW, request
  permission, subscribe with the VAPID key, POST `/v1/push/subscribe`), and a `<NotificationToggle>`
  on the `/briefing` landing (hidden when push is unsupported).

Validation: `test_alerts_runner_notify.py` (5); web2 tsc 0 / eslint 0 / vitest 506 / build OK.
Witness: `/sw.js` served 200, `/v1/push/public-key` returns the VAPID key, `/v1/push/test` →
`{"delivered":0}` (clean no-op until a browser subscribes). **Manual step for Eliot**: click
"Activer les alertes" on `/briefing` and accept the browser prompt to start receiving alerts.

### Phase 3 — Finish the §6.9 scrub (no model/version/jargon in rendered text) — SHIPPED

The product must read like a plain-French trading coach, not an engineering doc. The `/learn/*`,
`/calibration`, `/sessions/[asset]` and several dashboard pages still rendered internal names
(model/vendor names, ML technique acronyms, internal architecture terms). Scrubbed **28 page
files** of rendered occurrences → plain coach FR (PR #167 → main):

- Vendor/model names ("Claude", "Opus 4.8", "Sonnet 4.6", "Max 20x") → "le moteur d'analyse".
- ML acronyms surfaced to the user (HMM / FinBERT / VPIN / HAR-RV / DTW / SABR-SVI / ADWIN /
  Brier) → plain descriptions ("détection automatique du régime", "analyse du ton des
  actualités", "fiabilité", "situations historiques similaires", …).
- Internal architecture ("Couche-2", "Pass-1..6", "4-pass orchestrator", "data_pool") → "la
  veille", "l'analyse du régime / le test « et si ? »", "le contexte rassemblé".
- `error.tsx`: removed the exposed `ichor-api` / runner hostname → neutral outage copy.

EXCEPTION kept: `/legal/ai-disclosure` still names the provider (EU AI Act §50 obligation).

Guard against regression: new `__tests__/noModelNames.test.ts` source-inspects every page .tsx
(via `import.meta.glob`) and fails on any "Claude/Anthropic/Opus/Sonnet/Haiku" — 61 tests, all
green. Validation: tsc 0 / eslint 0 / vitest 506 + 61 / next build OK. Witness: source grep for
model names in rendered context = 0 (residuals are only code identifiers like `liveBrier` /
`Pass4ScenarioTree`, never user-visible).

### Phase 4 — Auto-improvement loop armed (gap 3) — DONE (DB flags, no code)

The learning loops measure (Vovk / drift / post-mortem fire nightly + Sunday) but the return into
the analysis was gated OFF by two fail-closed feature flags that did not even exist as rows.
Armed both (reversible):

- `INSERT feature_flags … w116c_llm_addendum_enabled = true` — the Sunday LLM addendum generator
  is now allowed to run. Dry-run validated the path (gate passes, runs clean).
- `INSERT feature_flags … pass3_addenda_injection_enabled = true` — stored addenda now inject
  into Pass-3. A fresh EUR_USD card generated cleanly with injection ON (`verdict=approved`), so
  the 17:01 batch is de-risked.

Honest caveat: there are currently **0 anti-skill pockets** (16 recent post-mortems all show the
model skilled vs baseline — the system is well-calibrated), so the generator has nothing to
correct yet and the `pass3_addenda` store is empty. The loop is **armed**: the first time the
model underperforms on a pocket, the Sunday generator will produce a corrective addendum (ADR-017
re-checked) and cards will inject it. The content witness is therefore event-conditional.

### Phase 5 — Opus 4.8 everywhere (§11, non-negotiable) — SHIPPED + DEPLOYED + VALIDATED (ADR-108)

Every local Claude call now runs on Opus 4.8 (the 4-pass core was already Opus). PR #168 → main,
plus **ADR-108** superseding ADR-023's model choice:

- **Pass-6 scenario decomposition**: sonnet medium → opus high (orchestrator default). LIVE; the
  17:01 ny_mid cron produced fresh cards with it.
- **Macro briefings** (`run_briefing`): all sonnet → opus high. LIVE.
- **Couche-2 agents** (cb_nlp/news_nlp/macro/sentiment/positioning): haiku low → opus low.
  ADR-023 had pinned Haiku only for the legacy SYNC 100s Cloudflare cap; Wave 67 moved Couche-2
  to the CF-edge-immune async-polling path, so Opus is now safe. effort stays low (structured
  extraction). Deployed via a single-connection tar-pipe (the multi-step deploy scripts kept
  hitting a transient Hetzner SSH-instability window). **Witness**: the `sentiment` agent ran on
  Opus low via async in 71s, success.

Validation: invariants 48 / brain 108 / agents 106 pass, ruff clean. Note: a mid-session Opus
throttle (slow + empty responses) was traced to Eliot's _parallel_ interactive Claude Code use
on the shared Max 20x account — NOT the Ichor pipeline — so full-Opus is the chosen config
(graceful degradation + Voie D as the safety net). Voie D unchanged (Max 20x, zero API spend).

### Phase 6 — Live web research via self-hosted SearXNG (§6 #1 non-negotiable, W103, ADR-084) — SHIPPED + DEPLOYED + WITNESSED

Ichor now does live web search at card-build time, beyond the ingested collectors. PR #169 → main:

- **Infra**: SearXNG Docker container on Hetzner (loopback 127.0.0.1:8081, JSON API on, limiter
  off since loopback-only, explicit `172.21.0.0/24` subnet to dodge the exhausted daemon
  address-pool, restart=unless-stopped, healthcheck). `infra/ansible/roles/searxng/files/` +
  idempotent `scripts/hetzner/register-searxng.sh`. Voie D: $0 marginal, no metered LLM.
- **`services/web_research.py`**: async SearXNG client, frozen `WebResultSnapshot`, URL +
  near-dup-title dedup, 24h in-process TTL cache, guarded Serper fallback (dormant w/o key),
  fail-open ([] on any error). **ADR-017: DROP** any result whose title/snippet trips
  `is_adr017_clean` — a trade-call snippet never reaches the LLM prompt; the cache stores only
  clean snapshots.
- **data_pool**: `_WEB_RESEARCH_QUERIES` per-asset SSOT + `_section_web_research` (merge/dedup,
  honest-absence, FR coach framing "actualité live, pas un signal", source-stamp
  `web_research:searxng@<ts>`) wired into `build_data_pool` next to `news`, fail-open.
- **config**: `web_research_searxng_url` (env `ICHOR_API_WEB_RESEARCH_SEARXNG_URL`).

Validation: SearXNG LIVE (healthy, JSON 14 results). test_web_research 18 pass + invariants 51 +
recent_actuals regression; ruff clean. **Witness**: `_section_web_research("EUR_USD")` on prod
renders 11 real live sources (ECB reference rates, Euro-Area rate, Trading Economics, …).

### §10 — Premium bespoke data-viz — ALREADY DONE (anti-doublon, verified, NOT rebuilt)

The §10 data-viz was already delivered by the 2026-06-01 refonte + Phase 1: `ScenariosPanel`
(7-bucket diverging coloured probability ladder, bar width ∝ p, bear/neutral/bull tints),
`CorrelationsStrip` (diverging heatmap via `lib/correlationHeat`), `ConvictionGauge` (radial SVG,
now on the apex via Phase 1), `EventSurpriseGauge`, area charts (`Sparkline`/`VolumePanel`/
`TodaySessionPulse` via `lib/microchart`) — all on the briefing deep-dive with the OKLCH dark+blue
design system + glassmorphism + motion. Verified present + wired (page.tsx:475/525/559); nothing
to rebuild (anti-doublon).

---

## Session wrap (2026-06-02)

**Delivered + on `main` (4c8dcbc), 9 PRs #163-#169, ZERO Anthropic spend, Voie D + ADR-017 held**:
pipeline rescue + Phase 0 (docs) + Phase 1 (verdict alive) + Phase 2 (notify) + Phase 3 (scrub) +
Phase 4 (auto-improvement armed) + Phase 5/§11 (Opus everywhere, ADR-108) + Phase 6/§6 (SearXNG
web research) + §10 (already done). Pipeline verified live: Win11 runner ok/cli=true, Hetzner api
200, SearXNG healthy, 7 fresh Opus cards in the last 6h.

**Remaining — §7 streaming cadence** (the only big unbuilt piece): react the instant a strong
event drops (economic release published / hard scenario invalidation / news burst) → targeted
verdict regen for that asset + push, instead of waiting for the next 4×/day batch. It touches the
LIVE pipeline + is Opus-budget-sensitive, so it is deferred to a fresh context. **Recommended
design**: a NEW additive, flag-gated, reversible cron (mirror
`register-cron-scenario-invalidation-check`, ~6×/day) that detects a NEW strong event since the
asset's last card and regenerates ONLY that asset's card + pushes (reuse `_assemble_live_triggers`
sources + recent `economic_events.actual`); budget guard (cap N regens/day + dedup); NEVER touch
the existing 4×/day batch (additive only). Full pickup detail in
`~/.claude/projects/D--Ichor/memory/auto_session_resume.md`.

**Open with Eliot**: the "ichor-beta" reference URL (his calibration standard) — still to provide.
