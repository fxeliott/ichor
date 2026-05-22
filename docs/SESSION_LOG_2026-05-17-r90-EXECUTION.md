# SESSION_LOG 2026-05-17 — r90 EXECUTION (ADR-099 Tier 2 continuation)

**Round type:** feature increment — ADR-099 **Tier 2 continuation =
`_section_gbp_specific`** (the per-round default from the r89 SESSION_LOG /
pickup v26). GBP/USD was the only one of the 5 ADR-083 priority assets
(EUR/GBP/XAU/SPX/NAS) WITHOUT a dedicated per-asset fundamental section
(r40 only fixed a generic GBP path bug) — the most concrete "ce qui
manque" for the mandated 5-asset × 8-layer coverage.

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API**
(pure deterministic data_pool, Voie D). ADR-017 held (gbp_specific
section empirically `ADR017 CLEAN` live on prod). Purely additive —
`verdict.ts` SSOT and every other section untouched. **Zero new FRED
ingestion** (`fred_extended.py` unchanged — both series already polled).

## What shipped (3 files, backend, zero new ingestion)

- **NEW `docs/decisions/ADR-101-...md`** — thin per-asset continuation
  ADR (Status: Accepted), extends the already-Accepted ADR-092 to
  GBP_USD (precedent: ADR-093 thin AUD child). 2-driver scope, Driver-3
  (BoE-Fed) explicitly deferred.
- **MOD `apps/api/src/ichor_api/services/data_pool.py`** — new
  `async def _section_gbp_specific` (before `_section_rate_diff`) + one
  wiring triplet in `build_data_pool` after the AUD triplet. 2-driver,
  mirrors the proven JPY r45 inline-FRED template. Asset-gated to
  `GBP_USD`, silent-skip if `IRLTLT01GBM156N` absent.
- **NEW `apps/api/tests/test_data_pool_gbp_specific.py`** — 13 tests
  (12 mirrored from the JPY template + the r40-bug-class directional-
  binding guard).

**Design (data-grounded, DOI-verified, honest):** Driver 1 = UK-US 10Y
rate differential (`dgs10 - uk10y`, the `_RATE_DIFF_PAIRS` US−foreign
sign convention) via Engel-West 2005 (DOI:10.1086/429137). Driver 2 =
sterling external-imbalance risk premium via Della Corte-Sarno-Sestieri
2012 (DOI:10.1162/REST_a_00157) — **an INDEPENDENT additive lens layered
ON the rate read, NOT a reinterpretation of it** (the ichor-trader
YELLOW-1 correction, see below). Safe-haven = one-line caveat only
(Ranaldo-Söderlind 2010 DOI:10.1093/rof/rfq007 — sterling is NOT a USD
haven). **R44 sign-convention discipline (the r40 GBP-bug class):**
GBP/USD quotes USD per GBP so USD is the QUOTE currency (polarity as
EUR/USD, INVERSE to USD/JPY) — a WIDER US-UK differential = USD-bid =
GBP/USD downside (GBP-soft); narrower/negative = sterling rate advantage
= GBP-bid. Stated explicitly in the section, ADR, and a dedicated test.

## R59 inspection (before any code — 2 parallel sub-agents + live SSH)

- `ichor-navigator`: exact per-asset-section pattern map (signature,
  asset-gate, `_latest_fred`, `_RATE_DIFF_PAIRS` [GBP already at :153],
  `_FRED_SERIES_MAX_AGE_DAYS` [`IRLTLT01GBM156N`:120d already], wiring
  point, JPY/AUD analogues, ADR-092 governance, test pattern).
  **Key finding: zero new FRED plumbing needed.**
- `general-purpose` web research: GBP/USD = rate-differential +
  risk-premium currency, NOT commodity (reject AUD-style ToT mirror);
  DOI-verified frameworks; candidate FRED series with explicit
  liveness-must-be-DB-verified caveats.
- **R53 / r88-lesson FRED-liveness gate (prod-DB ground-truth, NOT
  web-cache):** `DGS10` LIVE 2026-05-14 4.47 (≪14d) ; `IRLTLT01GBM156N`
  LIVE 2026-04-01 4.8207 (46d < 120d registry max-age — monthly OECD
  1-mo lag, NOT dead like the China IMF-IFS series). Driver-1 fully
  data-grounded.

## ichor-trader proactive review (R28 — every RED/YELLOW applied pre-merge)

**No RED.** FX sign-convention/polarity = **GREEN** (the highest-risk
r40-bug-class item — directionally correct, triple-consistent
code/ADR/test, explicitly guarded). ADR-017 / symmetric language /
Tetlock / source-stamping / Driver-3-deferral all GREEN.

- **YELLOW-1 (framework-attribution over-claim) — FIXED.** The original
  framing "DCS 2012 = regime-conditional lens on the SAME differential /
  reinterpretation of the same data" was an over-claim: DCS 2012 is an
  _external-imbalance_ (net-foreign-asset/current-account) predictor —
  an INDEPENDENT structural signal, NOT a reinterpretation of the rate
  spread. Reframed in all 4 locations (data_pool docstring + inline
  branch + rendered composite + ADR-101 Decision bullet) as an
  independent additive lens layered on — not derived from — the
  Engel-West read. This is exactly the r88 anti-over-claim /
  framework-attribution-honesty discipline applied.
- **YELLOW-2 (DCS page-range cross-check) — RESOLVED.** Citation-gate
  via Crossref primary source (below) confirmed `94(1):100-115` exact.
- **Recommended r40-guard test — ADDED.** `test_polarity_binds_both_
sign_directions` pins the sign→direction mapping itself (positive→
  GBP-soft, negative→GBP-bid) feeding the real 2026-05 print — the
  exact gap the r40 GBP bug slipped through (prior tests only checked
  the `±X.XX pp` string).

## Citation-gate (R44 / maximum-mode — primary-source, not second-hand)

WebFetch → Crossref API for all 3 shipped DOIs (Bash curl was
network-policy-denied → adjusted to the sanctioned WebFetch tool):

- `10.1086/429137` → "Exchange Rates and Fundamentals", Engel/West 2005,
  JPE 113(3):485-517 ✓ exact.
- `10.1162/REST_a_00157` → "The Predictive Information Content of
  External Imbalances for Exchange Rate Returns", Della Corte/Sarno/
  Sestieri 2012, REStat 94(1):100-115 ✓ exact (title confirms it is an
  external-imbalance paper → substantiates YELLOW-1).
- `10.1093/rof/rfq007` → "Safe Haven Currencies", Ranaldo/Söderlind
  2010, Rev.Finance 14(3):385-407 ✓ exact (title supports the
  sterling-is-NOT-a-haven caveat). Zero hallucination.

## Verification (3-witness, directly OBSERVED — r88 lesson honored)

1. **Static/test gate:** `ruff check` clean + `ruff format` clean ;
   **141 pytest passed** (13 GBP + JPY/AUD regression + ADR-017/Voie-D
   invariants), 0 failures. Doctrine-#4 venv verified worktree-pointed
   (`ichor_api.__file__` → worktree, `has _section_gbp_specific: True`)
   — pytest tests the real new code, not stale main. One symmetric-test
   assertion updated to the YELLOW-1-corrected token (the doctrine still
   holds; the test pinned a phrase the honesty-fix legitimately changed
   — fixed the test, did NOT re-add stale wording).
2. **Deploy:** vetted `redeploy-api.sh` (path hard-check, `.bak`,
   auto-rollback). Step-4 SSH hit a connection-timeout (known
   sshd-throttle, r76/r77 op-note) — prod NOT regressed (un-restarted =
   old code in memory; additive change anyway). ONE consolidated
   throttle-aware recovery SSH completed the restart + verify +
   inline-rollback-contingency: `healthz=200 sample=200`, no rollback,
   deployed STABLE grep-confirms the new code (def @2012, wiring
   @4479-4481).
3. **Direct live observation** (`/v1/data-pool/GBP_USD`, one SSH): the
   `gbp_specific` section renders LIVE with **real prod FRED data** —
   `UK 10Y = 4.82% (2026-04-01)`, `DGS10 = 4.47% (2026-05-14)`,
   **`US-UK 10Y differential = -0.35 pp`** (the real sterling-rate-
   advantage regime, observed not deduced), correct R44 polarity, the
   **YELLOW-1-corrected DCS framing live**, both source-stamps,
   `ADR017 = CLEAN`. Asset-gate proven live: `EUR_USD` pool does NOT
   carry it (no leakage).

## Flagged residuals (NOT fixed — scope discipline)

- **Driver 3 (BoE-vs-Fed reaction-function, Clarida-Galí-Gertler 1998
  DOI:10.1016/S0014-2921(98)00016-6) DEFERRED** — needs the unpolled
  `IR3TIB01GBM156N` (UK 3M interbank); its liveness is NOT prod-DB-
  verified, so per the r88 lesson it is NOT shipped this round (no new
  unverified-liveness series). Documented in ADR-101 §Deferred + inline.
  Upstream diligence captured: `IRSTCB01GBM156N` does NOT exist;
  `GBRCPALTT01IXNBM` discontinued (successor `GBRCPIALLMINMEI`).
- A dedicated external-balance dataset for Driver 2 (vs the current
  interpretive overlay) is a future enrichment.
- Pre-existing (not r90): Dependabot 3 vulns on main (r49 baseline) ;
  the r89-flagged KeyLevelsPanel joke-market backend data-quality.

## Process lessons (durable)

- **Citation-gate must use the sanctioned outbound tool.** Bash curl to
  api.crossref.org was network-policy-denied; WebFetch is the sanctioned
  path. Adjusted without re-attempting the denied call.
- **SSH-throttle deploy recovery pattern (reinforces r76/r77):** when a
  deploy script's mid-sequence SSH times out, prod is safe (un-restarted
  = old code, additive change). Do NOT revenge-retry; do ONE consolidated
  throttle-aware recovery SSH that completes the remaining steps + an
  inline rollback contingency. Never hammer sshd.
- **ichor-trader catches framework-attribution over-claims, not just
  sign/safety** — the DCS-2012 "reinterpretation" over-claim is exactly
  the r88 honesty failure mode; the proactive review is the right gate
  for it (R28 + R44).

## Next

**Default sans pivot:** ADR-099 **Tier 2 continuation** (remaining
ichor-trader Tier-2 items) — the **confluence re-weight by source
independence** in `lib/verdict.ts` (the synthesis SSOT — PRUDENCE, must
regression-verify byte-identical à la r71/r83 ; this is the remaining
high-value Tier-2 analytical-depth item) ; then optional AAII follow-up
→ Tier 3 autonomy hardening (ADR-097 `fred_liveness_check.py` missing ;
cron 365d/yr holiday-gate ; COT-EUR silent-skip ; **and the Driver-3
GBP enrichment**: ship `IR3TIB01GBM156N` ingestion + R53 liveness verify

- a Driver-3 BoE-Fed paragraph) → Tier 4 premium UI. R59 first; the
  next `continue` executes this default unless Eliot pivots. Session = 2
  rounds post-/clear (r89 + r90), not deep — no handoff/clear needed; the
  pickup v26 stays the current resume anchor.
