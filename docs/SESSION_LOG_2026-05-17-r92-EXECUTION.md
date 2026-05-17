# SESSION_LOG 2026-05-17 — r92 EXECUTION (ADR-097 FRED-liveness guard made functional)

**Round type:** Tier-3 autonomy-hardening (the r91 announced default).
Target = the long-flagged "ADR-097 FRED-liveness CI non-functional /
`scripts/ci/fred_liveness_check.py` absent" gap.

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API**.
ADR-017 / Voie D untouched (CI-tooling round). **No Hetzner deploy** —
this is a GitHub-Actions-only guard; it activates additively when Eliot
sets the CI secret.

## R59 OVERTURNED THE PREMISE (the most important finding)

The pickup / ADR-099:69-71 / ADR-099:145 all asserted the script "does
not exist; ADR-097:3 'code shipped' empirically refuted". **R59 (the
mandated first inspection) proved this STALE at HEAD `9160069`:** the
script (222 LOC, ADR-097-compliant) AND `.github/workflows/fred-liveness.yml`
have existed since **r61**. The r72 audit that produced the "absent"
finding ran against a state now ~56 commits old. **Acting on the stale
memory (re-creating the script) would have been a doublon** — R59
prevented it (doctrine: freshly-verified reality wins over a memory
claim; verify, don't re-affirm). gh confirmed the workflow is not yet on
the default branch (lives only on this unmerged 56-ahead branch) → it
has never run.

## The REAL gap : shipped-but-broken since r61 (2 latent defects)

The guard was non-functional from r61→r92, so the R53/r88 dead-series
lesson (China-M1 2019; the recurring failure the last 10+ rounds caught
by hand) was **never actually mechanically enforced** :

- **Defect A (exit-4 import).** The script imported the max-age registry
  from `services/data_pool.py` (SQLAlchemy + 33 ORM models + ~25
  services) ; the workflow installed only `httpx` → canonical-source
  import failed → exit 4 every run, even with a valid key. (Also
  `merged_series()` lazy-imports `fred.py` which needs `structlog` —
  not installed either.)
- **Defect B (key-absent nightly red).** Key-absent → fail-closed
  exit-3 (correct per ADR-097), but `ICHOR_CI_FRED_API_KEY` is an
  Eliot-gated secret not yet set (RUNBOOK-019) → the nightly cron would
  red the Actions tab indefinitely once merged.

## r92 fix — made genuinely functional, additively, ADR-097-faithful

- **NEW `apps/api/src/ichor_api/services/fred_age_registry.py`** —
  dependency-free SSOT (`FRED_SERIES_MAX_AGE_DAYS` +
  `FRED_DEFAULT_MAX_AGE_DAYS`), the **exact extraction ADR-097:23/:102
  anticipated**. The per-series table moved verbatim (zero value
  change).
- **MOD `data_pool.py`** — re-exports the registry under the historic
  private names (`_FRED_SERIES_MAX_AGE_DAYS` / `_FRED_DEFAULT_MAX_AGE_DAYS`),
  **byte-identical** (r71/r91 anti-accumulation extract-to-SSOT ; no
  duplicate dict — single source of truth). `_max_age_days_for` /
  `_latest_fred` unchanged.
- **MOD `scripts/ci/fred_liveness_check.py`** — registry import
  repointed to the dep-free `fred_age_registry` (Defect A fixed at
  source). Fail-closed exit-3 contract deliberately UNCHANGED (ADR-097
  is immutable ; not unilaterally weakened).
- **MOD `.github/workflows/fred-liveness.yml`** — install
  `httpx structlog` (the script's full import graph =
  fred_age_registry[dep-free] + fred_extended[clean] + fred[httpx+
  structlog] → minimal, no heavy apps/api install ; Defect A fixed at
  workflow). Added a `keycheck` step that **secret-gates** the run :
  skips cleanly with a `::notice::` until `gh secret set
ICHOR_CI_FRED_API_KEY`, then auto-activates (Defect B fixed
  additively ; script contract intact).
- **NEW `apps/api/tests/test_fred_liveness_check.py`** — first unit
  test : `_classify_severity` GREEN/YELLOW/RED boundaries, httpx
  `MockTransport` `check_series` (200/404/empty/missing-date/transport-
  error), the **byte-identical registry-extraction guard** (`data_pool.
_FRED_SERIES_MAX_AGE_DAYS is fred_age_registry.FRED_SERIES_MAX_AGE_DAYS`
  - known values pinned), and the fail-closed exit-3 contract lock.
- **ADR-097 §Amendment (r92)** appended (immutable → amend, ADR-093-r49
  precedent). **ADR-099:71 + :145** annotated `[r92 CORRECTION/DONE]`
  (the stale audit finding + the T3.1 roadmap line) — honesty fix.
  Pickup v26 + MEMORY.md corrected.

## Verification (CI-only — no Hetzner deploy)

- `ruff check` → "All checks passed!" (after the deterministic isort
  `--fix` ; the r92 reformat is import-ordering only, no logic) ;
  `ruff format` clean.
- **`pytest` 93 passed, 0 failures** (new `test_fred_liveness_check.py`
  - `test_fred_frequency_registry.py` [the data_pool-extraction
    regression] + `test_data_pool_gbp_specific.py` [section regression] +
    `test_invariants_ichor.py` [ADR-081/Voie-D]). The **byte-identical
    extraction is empirically proven** by the `is`-identity test + the
    frequency-registry + GBP-section tests all passing post-extraction.
- The workflow change cannot be CI-run here (requires the Eliot-gated
  secret + default branch — that is precisely the additive-by-design
  outcome) ; its logic is verified by inspection + the script's
  fail-closed/skip behaviour is unit-tested.

## Flagged residuals (NOT fixed — scope discipline)

- **Eliot residual (additive activation):** `gh secret set
ICHOR_CI_FRED_API_KEY --repo fxeliott/ichor` (RUNBOOK-019) — the
  guard auto-activates the moment it lands ; until then it skips
  cleanly (no false nightly RED). This is the _only_ remaining gesture
  for ADR-097 to be live.
- ADR-099:208 cross-ref line ("non-functional — T3.1 completes it")
  still reads stale ; folded into the README/ADR-index doc-hygiene
  backlog (r91-flagged) rather than a third inline annotation.
- Carried forward (r91): vitest/vite peer skew (repo-wide infra) ;
  README `## Index` stale since ADR-076 ; GBP Driver-3.

## Process lessons (durable)

- **R59 is the doctrine that matters most when memory asserts a gap.**
  A 20-round-old "X is absent" claim was false at HEAD ; the mandated
  inspection-before-action turned a phantom green-field build into a
  precise "shipped-but-broken, fix the 2 real defects" round, and
  caught a doublon before a single line was written.
- **"Shipped" ≠ "functional".** ADR-097:3's "code shipped" was _true_ ;
  the guard was still dead (import + key defects). Verify the thing
  _runs_, not just that the file exists ("marche exactement").
- **Immutable-ADR honesty:** correct stale governing-ADR claims via
  inline `[CORRECTION]`/`[DONE]` annotations + a dated `§Amendment`,
  never by rewriting history (ADR-093-r49 pattern).

## Next

**Default sans pivot:** Tier 3 autonomy hardening continues — T3.2
human-visible degraded-data alert (break the silent-skip chain :
`fred.py` + `data_pool return "",[]` + `run_session_card.py` broad
except) ; cron 365d/yr holiday-gate ; COT-EUR silent-skip ; GBP
Driver-3 (`IR3TIB01GBM156N`) ; **+ the r91 hygiene flags (vitest/vite
peer-skew realign so the verdict + this new test run in CI ; README
index back-fill 077→102 incl. ADR-099:208).** Then Tier 4 premium UI.
R59 first.

**Session = 4 deep rounds post-/clear (r89/r90/r91/r92).** Context
large ; per anti-context-rot doctrine + the standing brief ("ne grind
pas jusqu'à la dégradation") **`/clear` is recommended now** — pickup
v26 is the zero-loss resume anchor (updated this round) ; the next
`continue` resumes cleanly from it.
