# Session log — 2026-06-02 · Quantum-leap (make Ichor truly _alive_)

> Eliot re-read his full vision (Prompt_Ichor v3), had it challenged hard → evidence-based
> audits → **9 gaps** → a sequenced **7-phase master plan** (`ichor_quantum_leap_plan.md`,
> audit `ichor_audit_2026-06-02.md`). Méta-read: Ichor is built ~85% but "one flag-flip /
> one cable / one page away from being genuinely _alive_" at the spot Eliot looks. Eliot
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

<!-- phase sections appended here as they ship + deploy + witness -->
