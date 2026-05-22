# SESSION_LOG 2026-05-17 — r94 EXECUTION (ADR-092 §Round-94 / ADR-103 §Amendment)

**Round type:** Tier-3 autonomy-hardening follow-through — the r93
SESSION_LOG / pickup v26 binding default: resolve the
`PIORECRUSDM`/`PCOPPUSDM` 77 d > 60 d gap that r93's ADR-103 surface
itself surfaced. A registry recalibration (ADR-before-code), NOT a
feature add.

**Branch:** `claude/friendly-fermi-2fff71` (worktree
`D:\Ichor\.claude\worktrees\friendly-fermi-2fff71`). **ZERO Anthropic
API**. ADR-017 / Voie D held (the one new prose bullet is empirically
`adr017_clean = True` live). `_latest_fred` + every `_section_*` gate
byte-identical; the ONLY behavioural delta is iron/copper resolving
120 d (not 60 d) in `_max_age_days_for`.

## Resume verification (R59 — prompt is a failsafe, live wins)

Spawned in the STALE `gifted-bell-c1b656` worktree; real work is
`friendly-fermi-2fff71`. Verified by tool: HEAD `2203ae0` (r93), 58
ahead, clean, pushed. The standing-brief re-issuance = "continue"
(doctrine #10) → executed the announced default. Re-evaluated against
"ce qui crée le plus de valeur": the r93-surfaced false-DEGRADED is the
highest-value/lowest-blast-radius item (a freshly-shipped feature
emitting a false alarm in user-facing output erodes trust in the whole
T3.2 surface) — no higher-value gap emerged, no pivot.

## The decision — Case A confirmed by THREE independent authoritative sources (R53, zero guess)

r93 flagged `PIORECRUSDM` + `PCOPPUSDM` STALE at 77 d > 60 d. The open
question (r93 SESSION_LOG): live-monthly-with-lag (60 d mis-calibrated)
**or** genuinely dead like China-M1? Resolved with the R53 discipline
(the China-M1 web-cache-hallucination lesson — never accept liveness
from cache; multi-source authoritative ground-truth):

1. **prod-DB** (`psql -d ichor`, my SSH): iron/copper latest
   `2026-03-01`, age 77 d, n=1 — categorically unlike the dead China-M1
   (2481 d) ; the live monthly OECD anchors `IRLTLT01{AU,GB}M156N` are
   46 d under their 120 d entry (correctly FRESH).
2. **FRED primary source** (`general-purpose` sub-agent rendered the
   LIVE `fred.stlouisfed.org` series pages in-browser — WebFetch was
   403'd by FRED's bot-UA, correctly escalated to a real browser, NOT a
   cache): both **Monthly**, IMF Primary Commodity Price System, latest
   **Mar 2026**, last updated by FRED **2026-04-15**, **NOT
   discontinued / actively maintained**, ~2-week-after-month-end lag →
   freshest obs inherently ~75–90 d old.
3. **`ichor-navigator` code-map**: the r46 `= 60` was authored by
   ADR-092 §T1.AUD-2 on the assumption _"IMF PinkBook publishes
   early-month"_ — empirically refuted ; the registry block itself
   pre-sanctioned the fix (_"if silent-skip emerges, bump to 90d or
   120d"_) ; every other monthly series in the registry is 120 d.

**Verdict: the 60 d registry value is mis-calibrated (false-DEGRADED
every AUD card). r93's ADR-103 surface behaved EXACTLY as designed —
it judges liveness vs the registry SSOT and correctly exposed a latent
ADR-092 mis-calibration that had silently dropped the AUD commodity
composite for ~10+ rounds. The bug was the input value, not the
surface.**

## What shipped (1 registry value + 2 ADR amendments + 1 YELLOW-1 caveat + tests)

- **`docs/decisions/ADR-092-…md` §Round-94 amendment** (top-of-body,
  after metadata — immutable-ADR honesty pattern, ADR-093 §r49 /
  ADR-097 §Amendment precedent): documents the 3-source refutation +
  the 60→120 correction ; original §T1.AUD-2 text left intact for
  archaeology (no history rewrite).
- **`docs/decisions/ADR-103-…md` §Amendment (r94)** (appended): records
  that its first live DEGRADED was a registry mis-calibration ; ADR-103
  is **NOT amended in substance** (it worked as designed) ; the fix is
  at the registry layer.
- **`fred_age_registry.py`**: `PIORECRUSDM` + `PCOPPUSDM` **60 → 120**
  (matches the monthly-OECD SSOT precedent ADR-092:63 used for AU-10Y +
  every other monthly entry) ; the refuted _"PinkBook publishes
  early-month"_ rationale comment rewritten to the R53-correct
  explanation. **`MYAGM1CNM189N` left at 60 d UNCHANGED** (genuinely
  discontinued 2019-08-01 — must stay correctly DEGRADED ; widening it
  would mask a real dead series ; documented inline + test-pinned).
- **`data_pool.py` `_section_aud_specific` (ichor-trader YELLOW-1
  APPLIED pre-merge)**: a new staleness-caveat bullet on the
  now-rendering iron/copper composite, mirroring the existing China-M1
  single-print-constraint precedent — material because the tolerated
  staleness ceiling doubled (a Pass-2 LLM must not over-weight a
  100–120 d-old print next to a 1-day-old DGS10). Prose-only,
  ADR-017-clean, regression-pinned.
- **Tests**: `test_fred_frequency_registry.py` — the old 3-series-==60
  test split into `test_china_m1_dead_series_stays_60d` (==60) +
  `test_iron_copper_imf_pcps_monthly_120d_r94_recalibration` (==120 +
  consistency with `IRLTLT01AUM156N`). `test_data_pool_data_integrity.py`
  — appended behavioural proofs (`_fred_liveness` PIORE/PCOPP 77 d →
  fresh, 130 d → stale). `test_data_pool_aud_specific.py` — the
  YELLOW-1 caveat regression-pinned in the full-composite test.

## ichor-trader proactive review (R28 — every RED/YELLOW pre-merge)

Dispatched BEFORE deploy on the full diff. **No RED.** All 6 concerns
GREEN except **one YELLOW-1** (the iron/copper composite lacked the
per-driver no-extrapolate caveat the China-M1 driver has — material now
the staleness ceiling doubled). **YELLOW-1 APPLIED pre-merge** (the
caveat bullet + the regression-pin). GREEN findings: 120 d is correct
(90/100 explicitly rejected — precedent + margin + acceptable
~4-month death-detection for a _tertiary sub-driver_ with a redundant
nightly ADR-097 CI guard) ; China-M1 correctly preserved at 60 d ;
both ADR amendments factually accurate, non-over-claimed,
immutable-pattern-correct ; SSOT byte-identical re-export ;
source-stamping/Critic-verifiability **net-positive** (the composite
now emits the `FRED:PIORECRUSDM@…`/`PCOPPUSDM@…` stamps it previously
dropped — `source_pool_hash` for AUD cards changes going forward, which
is correct and attributed here).

## Verification (3-witness, "marche exactement pas juste fonctionne")

1. **Static/test gate:** ruff check + `ruff format --check` clean (5
   files) ; doctrine-#4 venv worktree-pointed ; registry correctness
   asserted live (`PIORECRUSDM=120 PCOPPUSDM=120 MYAGM1CNM189N=60
IRLTLT01AUM156N=120`) ; **150/150** targeted pytest incl. the
   YELLOW-1 regression-pin + the `_fred_liveness` 77 d→fresh /
   130 d→stale behavioural proof + `aud_specific` regression
   byte-identical.
2. **Deploy:** vetted `redeploy-api.sh`. Step-4 SSH hit the known
   sshd-throttle (Steps 1-3 succeeded — code rsynced into `STABLE`,
   prod NOT regressed). ONE consolidated throttle-aware recovery SSH
   (r76/r90 pattern) completed restart + 30×2 s `/healthz` poll +
   sample + the R53 reconfirm + the r94 witness + inline rollback
   contingency, single connection. `healthz=200`, `sample=200`, no
   rollback.
3. **Direct live observation** (same SSH, internal :8000) — the exact
   intended outcome on real prod data:
   - **R53 anti-cache reconfirm** (ichor-trader probe — verify, don't
     trust the cached 77 d): PIORE/PCOPP still `2026-03-01`/77 d (margin
     intact, NOT a genuine ingestion stall), China-M1 2481 d, AU-10Y
     46 d.
   - `AUD_USD` `degraded_inputs` = **only `MYAGM1CNM189N`** →
     `iron_copper_still_degraded = False` (**the false DEGRADED is
     GONE** — iron/copper FRESH at 120 d) ; `china_m1_still_degraded =
True` (**the genuine dead series is STILL caught** — the widening
     did not blind the surface ; concerns #2/#3 validated live).
   - Status line `⚠️ DEGRADED — 1 of 10` (was "3 of 10" at r93 — the
     AUD card now honestly reports ONLY the real death, not 2 false
     alarms). `iron_composite_renders = True` (the composite that was
     silently dropping for ~10+ rounds now renders the real prints) ;
     `staleness_caveat_renders = True` (YELLOW-1 live) ; `adr017_clean
= True`.

## Flagged residuals (NOT fixed — scope discipline)

- **`source_pool_hash` for `AUD_USD` cards changes going forward**
  (the composite now renders where it false-dropped — expected,
  correct, attributed here per ichor-trader concern #5 ; not a silent
  regression).
- The China-M1 `MYAGM1CNM189N` DEGRADED is **correct and desirable**
  (a real 6-year-dead series) — the standing AUD-composite audit-gap
  (find a live China-credit-impulse alternative) remains open per
  ADR-093 §r49 ; out of r94 scope (calibration round, not a
  data-sourcing round).
- Carried forward (r91/r92/r93): vitest/vite peer-skew repo-wide infra
  realign (so the verdict + fred-liveness + data_integrity tests run in
  CI) ; README/ADR `## Index` back-fill 077→103 ; GBP Driver-3
  (`IR3TIB01GBM156N`) ; Pass-6 occasional ADR-017-token retry ;
  Dependabot 3 main vulns (r49 baseline) ; the r94 end-user `/briefing`
  degraded-data badge (the ADR-103 `DataPool.degraded_inputs`
  foundation → ORM/migration/Pydantic/component chain — proven
  backend-then-frontend split).

## Process lessons (durable)

- **A freshly-shipped audit surface's first production signal must be
  triaged, not trusted or dismissed.** r93's ADR-103 surface emitting
  "3 of 10 DEGRADED" was a _true-positive mechanism find_ (a real
  latent ADR-092 mis-calibration silently dropping the AUD composite
  for ~10+ rounds) AND contained a false sub-signal (iron/copper) — R53
  multi-source triage separated them. Neither "the surface is noisy,
  ignore it" nor "3 series are dead" was correct ; only the
  ground-truth was.
- **R53 = multiple INDEPENDENT authoritative sources, and re-confirm at
  verify-time.** prod-DB + FRED-primary (via real browser, not
  WebFetch-cache) + code-map agreed ; the post-deploy SSH re-ran the
  prod-DB query rather than trusting the cached 77 d (ichor-trader's
  anti-cache discipline) — the amendment rests on re-verified data.
- **Widening a staleness threshold creates an asymmetry that must be
  closed at the point of consumption.** The 60→120 fix made the
  composite render with older data ; ichor-trader R28 caught that the
  per-driver no-extrapolate caveat (present for China-M1) was now
  missing for iron/copper — the fix is incomplete without it.

## Next

**Default sans pivot:** ADR-099 **Tier 3 autonomy hardening continues**
— R59 first, pick highest value/effort among: the cron 365 d/yr
holiday-gate (HIGH blast-radius — register-cron/systemd, the 2026-05-04
5-services-killed class — PRUDENCE, R59 + infra-auditor) ; GBP Driver-3
(`IR3TIB01GBM156N` ingestion + R53 liveness first) ; the r94 end-user
`/briefing` degraded-data badge (the ADR-103 `DataPool.degraded_inputs`
foundation → ORM/migration/Pydantic/component chain) ; then the
r91/r92 doc/infra-hygiene flags → Tier 4 premium UI. The next
`continue` executes this default unless Eliot pivots.

**Session = 6 deep rounds post-/clear (r89→r94).** Well past the
anti-context-rot threshold ; per the standing brief ("ne grind pas
jusqu'à la dégradation") + the pickup's standing recommendation,
**`/clear` is strongly recommended now** — pickup v26 + SESSION_LOG r94
are the zero-loss anchor (current through r94) ; the next `continue`
resumes cleanly.
