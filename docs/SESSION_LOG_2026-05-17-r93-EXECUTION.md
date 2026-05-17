# SESSION_LOG 2026-05-17 — r93 EXECUTION (ADR-099 §T3.2 / ADR-103)

**Round type:** Tier-3 autonomy-hardening — ADR-099 **§T3.2 "human-visible
degraded-data alert — break the silent-skip chain"** (the per-round default
from the r92 SESSION_LOG / pickup v26). Fresh session after `/clear`
(r89→r92 deep session terminated zero-loss).

**Branch:** `claude/friendly-fermi-2fff71` (worktree
`D:\Ichor\.claude\worktrees\friendly-fermi-2fff71`). **ZERO Anthropic API**
(pure deterministic runtime audit, Voie D). ADR-017 held — both render
branches empirically `adr017_clean = True` live on prod. Purely additive:
`_latest_fred` + every `_section_*` gate **byte-identical** (ichor-trader
algebraically re-proved this); `verdict.ts` SSOT untouched (backend round).

## Resume verification (R59 — prompt is a failsafe, live wins)

Spawned in the STALE `gifted-bell-c1b656` worktree (r49 `635a0a9`); the
real work is `friendly-fermi-2fff71`. Verified by tool, no contradiction:
branch `claude/friendly-fermi-2fff71`, HEAD **`7cbddea`**, 57 ahead /
0 behind origin/main, tree clean, fully pushed. Read pickup v26
authoritative block + doctrinal-patterns + the 4 SESSION_LOGs r89-r92.

## R59 OVERTURNED THE PROMPT HYPOTHESIS (doctrine #3 paid off)

The prompt/pickup framed T3.2 as "break the `fred.py` + `data_pool`
`return "",[]` + `run_session_card.py` broad-except silent-skip chain".
File:line R59 (own reads + `ichor-navigator` read-only code-map) proved:

- There is **no `services/fred.py`**; the silent-skip decision is
  `data_pool._latest_fred` (`:258-290`), which folds `observation_date
  > = cutoff`into SQL so a **stale** series returns the same`None` as a
**never-ingested** one — the stale-vs-absent distinction is destroyed
at the query layer (`:285-286`).
- The silent-skip is **not** a `run_session_card.py` broad-except (those
  excepts are scoped to calibration/RAG/pass3 best-effort only). It is
  the `if <src>:` conditional append in `build_data_pool` (`:4364-4428`)
  — no else, no log, no manifest. The session-card path discards
  `pool.sections_emitted` at `run_session_card.py:98`.
- In-codebase doctrinal precedent: `_section_key_levels` is
  "Always-rendered … explicit state instead of missing data"
  (`:4260-4261`). ADR-093 is an **Accepted/immutable**, _static_,
  AUD-only, never-projected prose primitive. ADR-099 §D-2: "never
  silently absent".

Acting on the stale hypothesis (wrapping `run_session_card.py` in an
alerting except) would have fixed the wrong layer. R59 reshaped the
design before a line was written.

## What shipped (4 files + 1 ADR, backend, ZERO new ingestion/migration/cron)

- **NEW `docs/decisions/ADR-103-runtime-fred-liveness-degraded-data-explicit-surface.md`**
  — thin child (Status: Accepted) implementing ADR-099 §T3.2,
  generalizing the ADR-093 static prose primitive into a dynamic runtime
  audit. New child ADR is the doctrinally-correct vehicle (ADR-093
  immutable; ADR-101/102 thin-child precedent).
- **MOD `apps/api/src/ichor_api/services/data_pool.py`** —
  `FredLiveness` + `DegradedInput` frozen dataclasses + `DataPool.
degraded_inputs` defaulted field (additive, frozen-safe); `_fred_liveness`
  (cutoff-FREE latest query → fresh/stale/absent against the r92
  `fred_age_registry` SSOT — the info `_latest_fred` destroys ; one extra
  cheap indexed LIMIT 1; `_latest_fred` itself untouched); `_CriticalAnchor`
  - `_MACRO_CORE_ANCHORS` (Pass-1 régime classifier inputs, overrides
    verbatim from `_section_executive_summary:324-329`) + `_ASSET_CRITICAL_
ANCHORS` (per-asset primary anchors + the ADR-093 AUD composite
    sub-drivers, R59-verified against every `_section_*_specific` gate, not
    guessed); always-rendered `_section_data_integrity` (3-tuple like
    `_section_daily_levels`, inserted at index 1 — after executive_summary,
    before macro_trinity — to prime Pass-1+Pass-2); deterministic header
    `Data integrity :` line (machine-truth, LLM-independent).
- **MOD `apps/api/src/ichor_api/routers/data_pool.py`** — `DegradedInputOut`
  - projection into the r90-live `GET /v1/data-pool/{asset}` operator
    surface.
- **NEW `apps/api/tests/test_data_pool_data_integrity.py`** — 18 tests
  (fresh/stale/absent classification, the byte-consistency boundary
  invariant `age<=max_age ⟺ _latest_fred >= cutoff`, always-rendered
  incl. an asset with no per-asset map, the AUD China-M1 dead-series
  scenario, absent-anchor, Class-A-asset-gating-never-degraded, the
  SPX VIXCLS macro-core/per-asset dedup, registry shape, ADR-017 canary
  on both renders).

**Scope (calibrated-honest, lesson #2 "shipped ≠ functional"):** r93 =
the backend deterministic foundation — degradation is now (a) explicit &
primed in the data-pool the LLM reasons over + deterministic header
machine-truth, and (b) operator-visible deterministically via the live
`/v1/data-pool/{asset}`. The **dedicated end-user `/briefing` badge**
(the `session_card_audit` ORM→`SessionCardOut`→`api.ts`→component chain +
an alembic migration) is the **announced r94** follow-up — the proven
r76→r77 / r80→r81 backend-then-frontend split; bundling it = the
migration-blast-radius + accumulation Eliot forbids. The ADR-103 §Scope
states this honestly; "human-visible alert" is satisfied at the
LLM+operator layer this round, end-user-UI deferred and named.

## ichor-trader proactive review (R28 — every RED/YELLOW pre-merge)

Dispatched BEFORE deploy on the full diff. **APPROVE for merge — zero
RED, zero YELLOW, all 6 concerns GREEN.** Independently re-proved:
(1) ADR-017 doctrine clean (data-provenance vocabulary, boundary note
correct, judged beyond the regex); (2) priming risk **mechanically
impossible** — `classify_master_regime` is a pure numeric function over
7 inputs, never reads the markdown, so a DEGRADED header cannot bias the
régime quadrant; (3) byte-consistency invariant algebraically proven
(`(today-latest).days <= N ⟺ latest >= today-N`, inclusive both ends,
same `_max_age_days_for` resolver, same `value.is_not(None)` filter,
tz-safe); (4) every per-asset anchor cross-checked against its real
`_section_*_specific` gate, AUD-composite mapping accurate not
over-claimed, EUR_USD honestly excluded (non-FRED Bund); (5) scope
calibration honest; (6) source-stamping correct (only FRESH series
stamped — a stale series has no valid current observation to cite; no
Critic invariant broken). **R28 "apply each RED/YELLOW pre-merge" = a
no-op this round** (none found — the strongest clearance).

## Verification (3-witness, "marche exactement pas juste fonctionne")

1. **Static/test gate:** `ruff check` clean + `ruff format` clean (the
   reformat was whitespace-only, doctrine #6); doctrine-#4 venv verified
   worktree-pointed (`ichor_api.__file__` → worktree; new symbols +
   `DataPool.degraded_inputs` present). **109/109** targeted pytest
   (new + gbp/fred-registry/fred-liveness/invariants), then **272/272**
   broad regression (`-k` all 7 per-asset sections + registry +
   invariants) — `_latest_fred` semantics + every section byte-identical
   (ADR-103 §Acceptance-5).
2. **Deploy:** vetted `redeploy-api.sh deploy`. Step-4 SSH hit the known
   sshd throttle (Steps 1-3 succeeded — path hard-check + `.bak` +
   code rsynced into `STABLE`; only the restart SSH timed out → prod NOT
   regressed, un-restarted = old code in memory). Per the r76/r90
   recovery pattern: NO revenge-retry — **ONE consolidated
   throttle-aware SSH** completed restart + 30×2s `/healthz` poll +
   sample probe + the r93 live witness + an inline rollback contingency,
   all in a single connection. `healthz=200`,
   `sample(/v1/geopolitics/briefing)=200`, no rollback, deployed STABLE.
3. **Direct live observation** (same consolidated SSH, internal :8000,
   zero public exposure) — the silent-skip chain **empirically broken on
   real prod data**:
   - **GBP_USD** + **USD_CAD**: `data_integrity` ∈ `sections_emitted`,
     `degraded_inputs=[]`, header `0 critical FRED anchor(s) degraded
(all fresh)`, `Status : ALL FRESH` (GBP 7 anchors / USD_CAD 6
     macro-core — proves always-rendered even for a non-priority asset
     with NO per-asset map, ADR-103 §Acceptance-2), `adr017_clean=True`.
   - **AUD_USD**: `Status : ⚠️ DEGRADED — 3 of 10`. The previously
     **silent** ADR-093 §r49 China-M1 now EXPLICIT: `MYAGM1CNM189N`
     STALE latest `2019-08-01` **age 2481 d > 60** → "aud_specific
     China-credit driver (ADR-093 composite)". **Plus two NOT predicted
     (R59 — discovered at verify, not forecast):** `PIORECRUSDM`
     (iron-ore) + `PCOPPUSDM` (copper) both STALE latest `2026-03-01`
     age 77 d > 60. Deterministic header carries the machine-truth
     verbatim. `adr017_clean=True` on the DEGRADED render too.

The feature found a **real, previously-invisible 3-driver AUD-composite
degradation on its very first live run** — exactly its purpose. Pre-r93
this was a section silently dropping a sub-driver with zero trace.

## Flagged residuals (NOT fixed — scope discipline)

- **NEW empirical discovery (r93 surfaced it):** `PIORECRUSDM` +
  `PCOPPUSDM` are STALE at 77 d > the 60 d registry max-age (latest
  `2026-03-01`). Open question for a future R53/registry-calibration
  round: are these monthly series with a normal ~2-month publication lag
  (then the 60 d registry entry is mis-calibrated vs the UK-10Y-style
  120 d precedent) **or** genuinely discontinued like China-M1? Do NOT
  guess — verify via the FRED API / prod-DB ground-truth (R53). This is
  the T3.2 feature working as designed (it makes the invisible visible);
  the calibration/liveness triage is its own round, not r93 scope-creep.
- **End-user `/briefing` badge = r94** (honestly deferred, not silently
  dropped) — needs the `session_card_audit` ORM→Pydantic→`api.ts`→
  component chain + an alembic migration (the proven backend-then-frontend
  split).
- **Non-FRED EUR-Bund anchor not audited** (`_section_eur_specific`
  reads `BundYieldObservation`, a separate no-cutoff table). Documented
  in ADR-103 §Negative as a future extension, out of FRED-liveness scope.
- Carried forward (r91/r92): vitest/vite peer-skew repo-wide infra
  realign (so the verdict + fred-liveness tests run in CI); README/ADR
  `## Index` back-fill 077→102 (incl. ADR-099:208, ADR-103); GBP
  Driver-3 (`IR3TIB01GBM156N`); Pass-6 occasional ADR-017-token retry;
  Dependabot 3 main vulns (r49 baseline).

## Process lessons (durable)

- **R59 reshapes the design, not just confirms state.** The prompt's
  "broad-except" hypothesis was the wrong layer; file:line inspection
  before coding turned a mis-aimed fix into a precise one (doctrine #3
  generalized: a prior round's _mechanism description_ is a hypothesis,
  not just its _audit-gap_).
- **A degraded-data feature must be live-verified against a KNOWN
  degraded series, not just the green path.** The China-M1 ground-truth
  - the unpredicted iron/copper finding is what makes this "marche
    exactement", not "renders". (r88 forecast≠proof lesson applied — I did
    not predict the AUD result; I observed it.)
- **SSH-throttle recovery is now muscle memory:** Steps 1-3 of the
  vetted deploy succeeded → prod safe (un-restarted = old code) → ONE
  consolidated recovery SSH with an inline rollback contingency, never a
  revenge-retry (r76/r77/r90 reinforced).

## Next

**Default sans pivot:** ADR-099 **Tier 3 autonomy hardening continues**.
R59 first; pick highest value/effort among: the **PIORECRUSDM/PCOPPUSDM
60 d-vs-actual-cadence registry-calibration triage** (R53 prod-DB
ground-truth — the concrete gap r93 just surfaced, high value, low
blast-radius) ; the cron 365 d/yr holiday-gate (high blast radius —
register-cron/systemd, the 2026-05-04 5-services-killed class —
PRUDENCE, R59 + infra-auditor) ; GBP Driver-3 (`IR3TIB01GBM156N`
ingestion + R53 liveness first) ; the r94 end-user `/briefing`
degraded-data badge (the ADR-103-prepared `DataPool.degraded_inputs`
foundation → ORM/migration/Pydantic/component chain). Then the r91/r92
doc/infra-hygiene flags → Tier 4 premium UI. The next `continue`
executes this default unless Eliot pivots. **Session = 5 deep rounds
post-/clear (r89/r90/r91/r92/r93)** — past the checkpoint zone; per
anti-context-rot doctrine + the standing brief ("ne grind pas jusqu'à
la dégradation") **`/clear` is recommended now** — pickup v26 is the
zero-loss anchor (updated this round).
