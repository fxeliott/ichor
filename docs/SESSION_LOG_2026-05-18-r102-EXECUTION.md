# SESSION_LOG 2026-05-18 — r102 EXECUTION (ADR-101 §Implementation(r102) — `IR3TIB01GBM156N` max-age recalibration 120→180)

**Round type:** ADR-099 §Tier-3 — GBP Driver-3. The r101-close
binding default ("Tier 3 continues, R59 first ; GBP Driver-3 — R53
prod-DB liveness verify, then wire the Driver-3 paragraph"). doctrine
#10 re-eval: the post-r101 cron ingested `IR3TIB01GBM156N` ⇒ step 3
(R53 liveness verify) is now executable, and it **surfaced a real
false-DEGRADE cadence bug** (137 d observed lag > the r101 120 d
ceiling) — exactly the r94 ADR-092 §Round-94 PCPS class. **Honest
split (pre-authorized by the r101-close default + the round prompt):
r102 = (a) R53 citation-gate + (b) max-age recalibration ONLY** ;
r103 = (c) US-side-leg framework resolution + (d) the Driver-3
paragraph. The full (a)+(b)+(c)+(d) is NOT one atomic verified
increment — (c) is a genuine framework-attribution decision ADR-101
itself flags a future-round RED ; bundling it mixes two review
surfaces and risks the mis-stamp ADR-101 warns of. Split announced,
not accumulated.

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API**
(FRED is the free public API, key already in env — Voie D). ADR-017
N/A (pure integer threshold config + ADR/test prose ; no signal, no
emit path ; `test_invariants_ichor` 41/41 green). **ZERO migration**
(generic `fred_observations` table — `series_id` an indexed column,
not a per-series table ; the KEYWORD-MIGRATION hook fired on the
_word_, not a schema change — r101 precedent ; no DB backup needed,
evidenced not assumed). One coherent atomic increment.

## Resume verification (R59 — the round prompt is a failsafe, live wins)

Spawned in the STALE `gifted-bell-c1b656` worktree ; real work in
`friendly-fermi-2fff71`. Verified live before any action via
`git -C` : HEAD `1404db7` (r101), branch `claude/friendly-fermi-2fff71`,
66 ahead origin/main, 0 uncommitted, origin==HEAD byte-equal. Doctrine
#4: worktree venv resolves `ichor_api` to the WORKTREE
(`D:\Ichor\.claude\worktrees\friendly-fermi-2fff71\apps\api\src\ichor_api\__init__.py`
— witnessed). Live == prompt failsafe (0 discrepancy on the resume
baseline).

## R59 (2 background sub-agents + self re-verify, doctrine #3)

1. **general-purpose FRED primary-source citation-gate** (the r88
   China-M1 anti-hallucination discipline — primary source, NOT
   web-cache). Findings (every figure URL-cited) :
   - `IR3TIB01GBM156N` _Interest Rates: 3-Month or 90-Day Rates and
     Yields: Interbank Rates: Total for the United Kingdom_ — Monthly,
     OECD Main Economic Indicators. **Obs end 2026-01-01 = 3.71**,
     Last Updated 2026-02-16, **NO discontinued banner**
     (https://fred.stlouisfed.org/series/IR3TIB01GBM156N +
     …/graph/fredgraph.csv?id=IR3TIB01GBM156N). ≈137 d stale at
     verify 2026-05-18. **Alive-but-slow — the r94 ADR-092
     §Round-94 false-DEGRADE class, NOT the China-M1
     (`MYAGM1CNM189N`, frozen 2019, kept 60 d) dead class.**
   - Siblings refresh ~47 d : `IRLTLT01GBM156N` UK 10Y obs 2026-04-01
     = 4.8207 ; `IR3TIB01USM156N` US 3M obs 2026-04-01 = 3.77
     (**EXISTS**, same OECD-MEI family, NOT polled — r103 input).
     `IR3TIB01GBM156N` is empirically the SLOW member of its family.
   - Already-polled timely US 3M : `DGS3MO` (US 3M Treasury CMT,
     daily, ~4 d) is in `fred_extended.py:26` — an r103 US-side-leg
     option (T-bill/CMT instrument ≠ interbank ⇒ label must change).
2. **r97-r100 SESSION_LOG digest fork** — holiday-gate genuinely
   COMPLETE, nothing half-built ; lesson #13 (no schema-guess) ;
   confirmed the 3 recalibration touch-points + r94 precedent commit
   `17e3780`.
3. **Self re-verify** (the sub-agent map is a hypothesis until
   re-read) : ADR-101 §Deferred + §Impl(r101) IS the binding spec ;
   `_section_data_integrity` (data_pool.py:438-531) liveness-checks
   ONLY the curated `_ASSET_CRITICAL_ANCHORS` (data_pool.py:409-435) ;
   `GBP_USD`'s sole anchor is `IRLTLT01GBM156N` ; `IR3TIB01GBM156N`
   is consumed by NO rendered section (Driver-3 paragraph deferred ;
   `_section_gbp_specific` never calls `_latest_fred(...,"IR3TIB01GBM156N")`)
   ⇒ the 120-d false-DEGRADE is **LATENT, not live**.

## ADR-before-code — ADR-101 §Implementation(r102), NO new ADR (doctrine #9)

Appended a dated `## Implementation (r102, 2026-05-18)` to immutable
ADR-101 (the ADR-104 §Impl(r96) / ADR-105 §Impl(r99,r100) / ADR-101
§Impl(r101) immutable-append precedent — §Deferred + §Impl(r101)
ARE the spec ; a redundant child ADR would itself violate #9). It
records: the R53 citation-gate ground-truth, the 120→180 derivation,
the LATENT-not-live framing, the deliberate scope boundary, the
still-deferred (c)+(d), and the consolidated-SSH proof reference.

## Recalibration 120 → 180 (the decision)

r101's `120` was the correct conservative **no-data** mirror of the
OECD-MEI monthly family (a missing entry → the 14-d DAILY default =
the r35 always-stale bug). Step-3 R53 data **refutes 120 for this
member specifically** : 137 d observed > 120 d ⟹ it would
false-DEGRADE the moment a consumer reads it — the exact r94 ADR-092
§Round-94 pathology (commit `17e3780`, PCPS 60→120). Applying the
**r94 margin discipline** (honestly attributed per ichor-trader
YELLOW-2 — r94 used a ~30 d _absolute_ margin over the ~90 d
worst-case → 120 ; this is NOT a verbatim "×1.33 rule" ; the
proportionalized form for ~137 d ≈ 1.33× / ~+43 d → 182 → clean
6-month ceiling **180**) ; robust under either the proportional or
the additive reading (both ≈180). The independent citation-gate
evidence-floor was 170 (137 + ~1 monthly bin) ; **180 over 170** for
r94 margin-discipline parity + family-laggard robustness + a clean
auditable 6-month ceiling. 180 d still catches a genuine
China-M1-class >6-month freeze (the r94 safety property preserved ;
`_classify_severity` → YELLOW >180 d, RED >360 d). Sole non-120
OECD-MEI monthly registry entry **by design and on evidence**.

## What shipped (1 registry value + verbose evidenced comment + 3 test touch-points + 1 ADR append + 3 ichor-trader YELLOW-1 string fixes ; ZERO migration)

- **`services/fred_age_registry.py`** — `"IR3TIB01GBM156N"` value
  `120 → 180` + a verbose r94-style evidenced comment block
  (primary-source-cited, NOT the China-M1 dead class, the honestly
  attributed r94 margin-discipline derivation, ADR-101 §Impl(r102)).
  `data_pool.py` re-exports the same object → `_max_age_days_for`
  auto-inherits, zero-diff (witnessed `is` identity on prod).
- **`tests/test_fred_frequency_registry.py`** — dedicated test
  `test_uk_3m_interbank_monthly_120_days` **renamed**
  `..._180_days` (semantic-honesty : a 120-named test asserting 180
  would lie), docstring rewritten (the documented OECD-MEI family
  laggard, ~137 d, recalibrated 180 — no longer "same 120 d as the
  UK 10Y sibling"), asserts `== 180` ×2 ; `monthly_series` sanity-
  tuple comment updated (membership/`≥30` assertion unchanged).
- **`tests/test_fred_liveness_check.py`** — byte-identical-extraction
  pin `registry["IR3TIB01GBM156N"] == 120 → == 180` (ruff-wrapped
  multi-line, doctrine #6 ; logic unchanged).
- **`docs/decisions/ADR-101-…md`** — `## Implementation (r102)`
  appended (immutable, doctrine #9).
- **ichor-trader YELLOW-1 cross-file-drift fixes (string-only,
  assertions retained — the r101 YELLOW-1 remediation shape)** :
  `data_pool.py:2278-2282` docstring + `data_pool.py:2362-2367`
  **live-rendered GBP-card text** + `test_data_pool_gbp_specific.py:324-325`
  docstring all said `IR3TIB01GBM156N` "not yet prod-ingested /
  R53-not-verified" — now FALSE post-cron. Reworded to the accurate
  post-r102 state (poller-configured r101 + ingested post-r101 +
  R53-recalibrated 180 d r102 ; the Driver-3 _paragraph_ still
  deferred to r103). The corrected text does NOT assert prod-DB
  liveness ahead of the consolidated-SSH witness (forecast≠preuve
  honored — only the now-false _negative_ was removed).

## ichor-trader proactive review (R28 — every RED/YELLOW pre-merge)

Dispatched BEFORE deploy with the explicit scope-boundary question.
**0 RED / 2 YELLOW, both pre-merge-mandatory, BOTH APPLIED + the
round re-verified GREEN.**

- **YELLOW-1 (scope boundary) — overruled my "leave all for r103"
  default on the one now-false-negative clause.** Adjudication: my 3
  justifications (forecast≠preuve / atomicity / r103-rewrites-it) are
  sound for NOT adding Driver-3 prose or claiming liveness ahead of
  the witness, but do NOT license leaving a now-false _negative_
  ("not yet prod-ingested / not yet R53-verified") in a **rendered
  runtime string** + 2 docstrings — that IS the r101-YELLOW-1
  cross-file-drift class my round introduces. The highest-severity
  instance (`data_pool.py:2362-2367`) is rendered into the live GBP
  card today (inside the always-true `if dgs10_latest is not None:`
  branch). Fixed all 3 string-only, assertions retained, exact
  wording per ichor-trader (no liveness claim ahead of the witness).
- **YELLOW-2 (recalibration-value attribution honesty)** — value
  180 substantively correct + the r94 precedent commit `17e3780`
  faithfully cited (verified, not hallucinated), BUT "the r94 design
  rule = ×1.33" over-stated r94's _verbatim_ rule (r94 = a ~30 d
  absolute margin). Softened in BOTH `fred_age_registry.py` AND
  ADR-101 §Impl(r102) to attribute 1.33× as a proportionalized
  interpolation of r94's additive margin (number 180 unchanged ;
  same family as the ADR-101 r90 "regime-conditional lens" honesty
  YELLOW).
- **Probe honored**: the ADR §Impl(r102) references this SESSION_LOG
  as the consolidated-SSH proof — this file carries the verbatim
  witness (below) so the ADR does not assert a proof that does not
  exist (the forecast≠preuve YELLOW ichor-trader flagged is avoided).

## Verification — Witness A static + deploy + Witness B/C LIVE (one consolidated throttle-aware SSH)

1. **Witness A — static gate (GREEN):** doctrine-#4 venv→worktree
   confirmed ; `ruff check` clean + `ruff format` (auto-wrapped
   `test_fred_liveness_check.py` long comment + the new prose —
   doctrine #6, logic byte-identical) ; **pytest 95/95** twice
   (pre- and post-YELLOW-fixes) across `test_fred_frequency_registry`
   - `test_fred_liveness_check` + `test_data_pool_gbp_specific`
     [GREEN post-string-fix — the 4 substring assertions
     `Clarida-Gali-Gertler 1998` / `10.1016/S0014-2921(98)00016-6` /
     `IR3TIB01GBM156N` / `DEFERRED` + the safe-haven assertions all
     retained] + `test_invariants_ichor` 41 ADR-081 — ZERO doctrinal
     regression.
2. **Deploy (additive, ADR-099 §D-4 autonomous, ZERO migration):**
   vetted `redeploy-api.sh` (R59-verified by reading the script —
   pure-bash, hard-path-check → timestamped `.bak` → tar-over-ssh
   → restart → healthz/sample probe → auto-rollback on non-200).
   Steps 1-3 OK (code synced to prod `/opt/ichor/api/src/src/ichor_api`
   - `.bak`). **Step-4 hit the documented benign sshd-throttle**
     (`ssh: connect … timed out` — code already synced, service
     un-restarted ⇒ prod = OLD code, NOT regressed = safe for an
     additive change ; the auto-rollback did NOT fire because the
     script died at the SSH connect, before the verify/rollback
     logic). Recovered with **ONE consolidated throttle-aware SSH**
     (single ~75 s decay wait, then ONE connection — doctrine #7,
     never hammered/revenge-retried).
3. **Witness B+C — LIVE on prod (the ONE consolidated SSH ;
   verbatim, the ichor-trader-required proof) :**

```
WITNESS_HEALTHZ=200
WITNESS_ACTIVE=active
WITNESS_MAXAGE_IR3TIB01GBM156N=180        # the REAL prod _max_age_days_for code path
WITNESS_REGISTRY_VAL=180
WITNESS_REEXPORT_SAME_OBJ=True            # data_pool re-export identity, zero-diff
WITNESS_SIBLING_UK10Y=120                 # IRLTLT01GBM156N correctly unchanged
deployed fred_age_registry.py:73 = "IR3TIB01GBM156N": 180,  # … r102 §Impl(r102) …
# R53 prod-DB schema (\d, no-schema-guess lesson #13) : observation_date date,
#   series_id varchar(64), fetched_at timestamptz, uq(series_id,observation_date)
IR3TIB01GBM156N|2026-01-01|1|137          # MAX(obs)|COUNT|age_days
IRLTLT01GBM156N|2026-04-01|2|47           # sibling
collector MAX(fetched_at) = 2026-05-18 06:00:43+02   # alive, fetched TODAY (anti-cache)
```

**R53 cross-check (ichor-trader mandatory probe) : age 137 d —
`137 > 120` ⟹ the recalibration WAS necessary (old 120 would
false-DEGRADE) ; `137 < 180` ⟹ no day-one DEGRADE under the new
ceiling. Both satisfied — empirically necessary-and-sufficient.**
The collector `fetched_at` = today proves the ~137 d is real
OECD-MEI publication lag (alive-but-slow), NOT a collector
failure / NOT discontinued — concordant with the citation-gate
primary source + the prompt failsafe (0 discrepancy).

## Honesty framing (calibrated — lessons #1/#2/#11)

- **The threshold false-DEGRADE was LATENT** : `IR3TIB01GBM156N`
  is not a critical anchor and not yet consumed by any rendered
  section ⇒ r102 removes the **precondition** that would make the
  r103 Driver-3 paragraph false-DEGRADE every GBP card ; it does
  NOT change a currently-DEGRADE-rendered card.
- **BUT the deferral-reason prose was a LIVE user-facing
  inaccuracy** (ichor-trader YELLOW-1) : `data_pool.py:2362-2367`
  renders into every GBP card and said "not yet prod-ingested" —
  false post-cron. r102 corrects that to the accurate state. (Two
  distinct things : the _mechanism_ was latent ; one _prose string_
  was live-wrong. Both stated precisely, neither over/under-claimed.)
- **R53 liveness is now PROD-DB-VERIFIED at my verify-time** (137 d,
  alive-but-slow, collector fetched today) — an observed witness,
  NOT a forecast. This is legitimately stronger than r101's
  deliberate "no liveness claim" (r101 had no prod data ; r102 does).

## Flagged residuals (NOT fixed — scope discipline, deferred to r103)

- **(c) US-side leg of the BoE-vs-Fed 3-month reaction-function
  differential** : `IR3TIB01USM156N` (US 3M interbank, same
  OECD-MEI family, ~47 d, primary-source-confirmed EXISTS) is the
  faithful Clarida-Galí-Gertler 3M-vs-3M counterpart but is NOT
  polled (an r101-class chicken-egg if ingested) ; `DGS3MO`
  (already polled, daily, ~4 d) is a T-bill/CMT instrument ≠
  interbank (label must change if used). Reusing `DGS10` 10Y under
  the Clarida-Galí-Gertler label remains the FORBIDDEN mis-stamp
  (ADR-101 §Impl(r101) Axis-5 RED). The instrument/label choice is
  an r103 ichor-trader-R28-reviewed decision, not pre-committed
  (never-act-on-a-guess).
- **(d) the Driver-3 paragraph** in `_section_gbp_specific`
  (post-(c) : R44 sign-convention, symmetric language, Tetlock +
  VIX cross-confirm, source-stamp `FRED:IR3TIB01GBM156N@<date>`,
  frequency-mismatch + R24 annotations, ADR-017-clean ; adapt
  `test_data_pool_gbp_specific.py` — the `"DEFERRED"` assertion
  flips when the paragraph goes active).
- Carried (unchanged) : §Cross-endpoint no-sidecar page-wiring
  integration test (r96/r97 YELLOW, low value) ; US-holiday
  fused-briefing asset-PRUNE (YAGNI) ; Pass-6 occasional
  ADR-017-token retry (guard HOLDS) ; KeyLevelsPanel $5 polymarket
  joke ; Dependabot 3 main vulns (r49 baseline) ; pre-existing
  FastAPI `regex`→`pattern` deprecation warnings (unrelated tech
  debt, NOT an r102 regression) ; MEMORY.md > soft-cap ; 13 git
  worktrees incl. stale (housekeeping). Then Tier 4 premium UI.
- Eliot-gated (RUNBOOK-019, unchanged) : merge PR #138 ; named CF
  tunnel ; `gh secret set ICHOR_CI_FRED_API_KEY` ; activate the
  holiday-gate DB flags ; rotate leaked creds ; revoke PAT.

## Process lessons (durable)

- **A deferred liveness step empirically surfaces a cadence bug the
  conservative no-data default masked** (the round-prompt's NEW
  lesson #6, now observed) : r101's `120` was correct _without
  data_ ; r102's R53 verify is precisely what catches that `120`
  false-DEGRADEs THIS family-laggard member. The deferral was not a
  gap — it was the mechanism that found the bug with real data.
- **ichor-trader R28 caught a real cross-file-drift my round
  introduced AND overruled my scope-boundary default** (doctrine #5,
  the r101 YELLOW-1 precedent). My "leave all 4 strings for r103"
  was right for 3 (the wholesale-rewrite ones) but wrong for the
  now-false-negative clause in a _rendered_ string — applied
  pre-merge.
- **Calibrated honesty has two axes here** : the _mechanism_ latent
  vs the _prose_ live-wrong are distinct ; stating each precisely
  (not collapsing to one "latent" claim) is the honest framing.
- **The split was the atomic-discipline call** : (c) US-side-leg is
  a framework-attribution decision with its own review surface ;
  bundling it into a threshold-config round would have been the
  "mélanger/accumuler" Eliot forbids. Pre-authorized split,
  announced.

## Next

**Default sans pivot:** ADR-099 **Tier 3 continues — r103 = GBP
Driver-3 (c) + (d)**. R59 first. (c) Resolve the US-side leg: R59 +
ichor-trader R28 the instrument/label decision — `IR3TIB01USM156N`
true-3M-vs-3M (ingest = r101-class chicken-egg, then a later round
wires post-cron) **vs** already-polled `DGS3MO` US-3M-CMT-daily
(no chicken-egg, but T-bill/CMT ≠ interbank ⇒ the framework label
must be stated honestly, NOT "Clarida-Galí-Gertler interbank"). Do
NOT reuse `DGS10` 10Y under the Clarida-Galí-Gertler label
(ADR-101 §Impl(r101) Axis-5 RED). (d) Wire the Driver-3 paragraph in
`_section_gbp_specific` (R44 polarity, symmetric, Tetlock+VIX,
source-stamp, frequency-mismatch + R24, ADR-017-clean) + flip the
`test_data_pool_gbp_specific.py` `"DEFERRED"` assertion. If (c)+(d)
is non-atomic (e.g. the chicken-egg path is chosen): SPLIT honestly
(r103 = (c) ingestion plumbing ; r104 = (d) post-cron wiring) —
announce, do not accumulate. Then Tier 4 premium UI. The next
`continue` executes this default unless Eliot pivots.

**Session depth:** PREMIÈRE-ACTION reading + r102 (3 sub-agents :
citation-gate + r97-r100 digest + ichor-trader R28) in a fresh
post-/clear session. pickup v26 + SESSION_LOG r95→r102 are the
zero-loss anchor (current through r102).
