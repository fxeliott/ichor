# SESSION_LOG 2026-05-17 — r96 EXECUTION (ADR-104 §Implementation — end-user /briefing degraded-data badge)

**Round type:** Tier-3 autonomy-hardening continuation — the r95
SESSION_LOG / pickup v26 binding default ("r96 = the frontend
`/briefing` degraded-data badge, ADR-104 §Cross-endpoint is its binding
contract"). The FRONTEND leg of the r93→r94→r95 data-honesty arc. No new
ADR (ADR-104 §Cross-endpoint **is** the r96 spec — a dated
§Implementation note was appended instead, immutable-ADR discipline
doctrine #9).

**Branch:** `claude/friendly-fermi-2fff71`. **ZERO Anthropic API**
(pure deterministic presentation, Voie D). ADR-017 held (analytical
data-provenance vocabulary only, boundary footer on every state —
ichor-trader R28 GREEN). Purely additive frontend; `verdict.ts` SSOT and
every backend path untouched.

## Resume verification (R59 — prompt is a failsafe, live wins)

Spawned in the STALE `gifted-bell-c1b656` worktree; real work in
`friendly-fermi-2fff71`. "continue" = the binding r95 default (doctrine
#10) → executed. One focused R59 sub-agent re-confirmed the EXACT current
frontend shapes (the r95-era map is a hypothesis until re-verified
file:line — r95 was backend-only so the frontend was unchanged, but
"likely" ≠ "verified"): `briefing/[asset]/page.tsx` SSR,
`fetchSessionCardForAsset:85-96`→`SessionCard|null`, no card-absent early
return (sections gated inline), insertion `<PocketSkillBadge>` :224 →
`<section key-levels>` :226 ; `api.ts SessionCard` :171-214 (no
degraded_inputs — r95 backend-only confirmed) ; the
`EventSurpriseGauge`/`lib/eventSurprise.ts` house-style + RSC-boundary +
pure-SSOT-split template ; all CSS tokens real ; `redeploy-web2.sh`
mechanics.

## The decision — always-rendered tri-state badge, persist-on-card source (binding contract)

3 UI approaches were weighed (ultrathink). (A) conditional badge
(`null`→render nothing) = REJECTED — violates the ADR-104 §Cross-endpoint
contract I wrote in r95 _precisely to prevent this trap_ (`null` rendered
as nothing recreates the silent-skip ADR-103/104 kill, at the human
surface). (C) tri-state split across BriefingHeader chip + card =
REJECTED — shared-component blast radius + accumulation + against the
standalone-badge convention + the written placement. **(B) always-rendered
self-contained tri-state badge, pure SSOT + thin client component =
CHOSEN** — honors the binding contract (3 honestly-distinct states),
carries the ADR-103 always-rendered doctrine to the human, minimal blast
radius, anti-accumulation (SSOT split), clarity-through-phrasing (no
méthodologie encart).

## What shipped (frontend, additive, zero backend change)

- **NEW `apps/web2/lib/dataIntegrity.ts`** — pure SSOT (no `"use
client"`/React/JSX — RSC-safe, mirrors `lib/eventSurprise.ts`):
  `deriveDataIntegrity(degraded_inputs)` → discriminated
  `DataIntegritySummary` tri-state (`untracked` / `all_fresh` /
  `degraded`), all FR display strings + pluralisation + row mapping
  precomputed in the pure module.
- **NEW `apps/web2/components/briefing/DataIntegrityBadge.tsx`** — thin
  client component (`"use client"`, motion), mirrors the
  `EventSurpriseGauge`/`PocketSkillBadge` glass-card chrome
  byte-faithfully ; `if (!data) return null` (no card → silent, the page
  surfaces card-absence elsewhere) ; degraded = `--color-warn` headline +
  per-series `<ul>`/`<li>` list (a11y 1.3.1) ; all_fresh = low-emphasis
  `--color-bull` positive (calibrated humility) ; untracked =
  `--color-text-muted` only, NO positive color, "absence d'information, à
  ne pas interpréter comme un état sain" (the binding-contract honesty
  literal) ; ADR-017 footer on ALL three states.
- **`apps/web2/lib/api.ts`** — new `DegradedInput` interface + REQUIRED
  `degraded_inputs: DegradedInput[] | null` on `SessionCard` (accurate
  wire mirror — the backend always serializes the key post-r95 ;
  required-key/nullable-value, consistent with `source_pool_hash`/
  `key_levels` siblings ; NOT weakened to optional).
- **`apps/web2/app/briefing/[asset]/page.tsx`** — 1 component import + 1
  SSOT import + server-side `const dataIntegrity = card ?
deriveDataIntegrity(card.degraded_inputs) : null;` + the standalone
  `<DataIntegrityBadge>` between `<PocketSkillBadge>` (:224) and the
  "Niveaux clés" `<section>` (the epistemic-sibling placement).
- **`apps/web2/__tests__/verdict.test.ts`** — the r91 verdict-regression
  `mkCard` fixture completed with `degraded_inputs: null` (the new
  required field ; type-accurate, inert for `deriveVerdict` — zero
  behavioural change to the r91 byte-identity regression ; ichor-trader
  GREEN).
- **`docs/decisions/ADR-104-…md`** — appended `## Implementation (r96,
2026-05-17)` dated note (immutable-ADR append ; NO new ADR — §Cross-
  endpoint IS the r96 spec).

## Reviews (proactive pre-merge — every finding applied, doctrine #5)

- **ichor-trader R28 — 0 RED, 1 YELLOW-1, 6 GREEN.** GREEN: ADR-017
  (pure analytical provenance, footer on all 3 states, no sizing/BUY-SELL
  drift) ; ADR-104 §Cross-endpoint (the only `/v1/data-pool` string is
  the docstring forbidding it ; consumes only `card.degraded_inputs` ;
  3 genuinely-distinct renders ; no new fetch) ; tri-state honesty
  (all_fresh low-emphasis, untracked not-positive) ; anti-accumulation #4
  - RSC #5 (all logic in SSOT, clean client boundary) ; verdict.test.ts
    fixture (type-accurate, zero-behaviour-change) ; over-claim/scope
    honesty. **YELLOW-1 APPLIED**: a coupling comment at the
    `status`→label map (`"stale"|"absent"` 2-value ; any 3rd value silently
    →"PÉRIMÉE") so a future backend `DegradedInputOut` enum widening fails
    loud at review (mirrors the `eventSurprise.ts` defensive-parse note).
- **accessibility-reviewer (WCAG 2.2 AA) — 0 MUST-FIX.** Correctly
  inherits the accepted sibling baseline (1.4.1 satisfied by
  `PÉRIMÉE`/`ABSENTE` text + distinct headlines not color ; all text
  contrasts ≥4.5:1 on the dark surface, worst-case all-muted untracked
  ≈6.5:1 ; zero interactive elements → operable SCs N/A). **NICE-TO-HAVE
  1.3.1 APPLIED**: wrapped the degraded rows in `<ul>`/`<li>` (was a bare
  `<div>` sequence ; the closest sibling uses `<dl>`). The reviewer's
  defensive `role="list"` snippet conflicted with the project's enforced
  `jsx-a11y/no-redundant-roles` (eslint `--max-warnings 0`) — reconciled:
  removed the redundant role (the `display:contents` legacy-UA a11y-tree
  bug it defended against was fixed in all evergreen engines ~2021-22 ;
  on the 2026 target `<ul>/<li>` alone delivers the "list, N items"
  semantics ; honoring the codebase's own lint convention + sibling
  consistency wins). NICE-TO-HAVE 1.4.11 (pill border <3:1) deliberately
  NOT changed — decorative, meaning in full-contrast text, identical to
  the accepted `PocketSkillBadge` `/40` house convention (re-litigating
  the accepted pattern would break consistency).

## Verification (3-witness, calibrated-honest — "marche exactement", not over-sold)

1. **Witness A — static/SSOT gate:** web2 `tsc --noEmit` exit 0 + `eslint
. --max-warnings 0` exit 0 (clean on the real code) ; the pure SSOT
   logic proven by **19/19 assertions** via `node
--experimental-strip-types` (vitest pre-broken repo-wide — flagged,
   NOT scope-crept into a lockfile fix, doctrine #8), including the
   binding-contract assertion `untracked !== all_fresh`.
   **Self-caught process error (durable lesson):** the first gate run
   showed tsc=2/lint=1 — root-caused to the ephemeral
   `node-strip-types` harness being present in the tsc/lint scope
   (sequencing error: harness created before the gate in one command).
   Diagnosed, harness fully separated, clean re-run confirmed tsc=0
   /eslint=0. A polluted signal was triaged, not shipped on.
2. **Deploy:** vetted `redeploy-web2.sh` — Next build OK, `ichor-web2`
   restarted, `local=200 public=200`, **PUBLIC URL stable**
   `https://latino-superintendent-restoration-dealtime.trycloudflare.com/briefing`
   (r75 stability held — tunnel not restarted), legacy `ichor-web`
   (3030) untouched (additive). No throttle this round.
3. **Witness B+C — LIVE on real prod (ONE consolidated SSH, internal
   curl of the deployed `:3031` SSR + the `:8000` data source ;
   outbound-curl-from-here is policy-denied — doctrine #7 zero-exposure):**
   the badge faithfully maps the real persisted `card.degraded_inputs`
   to the honest tri-state, end-to-end, for **2 of 3 states on real
   priority pages**:
   - **ALL_FRESH** — `EUR_USD` + `GBP_USD`: `/v1/sessions` →
     `degraded_inputs=[]` → `/briefing/{asset}` SSR renders the
     `[ALL_FRESH]` badge + ADR-017 footer (post-r95 cron already produced
     fresh-anchor cards — the `[]` state IS live-witnessed, better than
     the pre-verify honest-scoping assumption ; observe-don't-forecast,
     lesson #1).
   - **UNTRACKED** — `NAS100_USD` + `XAU_USD` + `SPX500_USD`:
     `degraded_inputs=null` (legacy pre-0050 cards) → SSR renders the
     `[UNTRACKED]` "non suivie — absence d'information" badge + footer
     (SPX500 badge region isolated + verified untracked-only).
   - **DEGRADED** — **NOT live-witnessed on a priority page (honestly
     scoped, lesson #11, anti r87-forecast).** The only asset currently
     carrying a degraded card is `AUD_USD` (r95 Witness-C,
     `['MYAGM1CNM189N:stale']`), but `AUD_USD` is a **backend-only
     asset — not a frontend priority asset** (the 5 are EUR/GBP/XAU/SPX/
     NAS) → `/briefing/AUD_USD` hits `page.tsx:102 notFound()`
     (verified: http-200 not-found UI), so it has no badge by design. No
     priority asset currently has a degraded card. The DEGRADED render is
     therefore **SSOT-proven (19/19, incl. the degraded branch +
     PÉRIMÉE/ABSENTE rows) + ichor-trader-GREEN (3 distinct renders) +
     the identical code path as the 2 live-witnessed states** — but its
     _pixel render on a priority page_ awaits a priority asset actually
     degrading. Stated, not over-claimed.
     Two grep anomalies fully triaged to ground truth (lesson #13): AUD =
     by-design not-a-bug ; SPX500 `[series-row]` = case-insensitive grep
     false-positive on non-badge page content (badge region verified
     row-free) — verification-instrument artifacts, not defects.

## Flagged residuals (NOT fixed — scope discipline)

- **DEGRADED visual on a priority page** awaits a priority asset (EUR/
  GBP/XAU/SPX/NAS) actually carrying a degraded card — data-dependent,
  un-manufacturable without fabrication. SSOT + review + code-path are
  the standing proof until then.
- Cockpit (`briefing/page.tsx`) cross-asset degraded indicator =
  deliberately deferred (ADR-104 §Related : per-asset page is the r96
  target ; a cockpit roll-up is a possible r97+ micro-add — accumulation
  risk + out of the binding contract, stated not silently skipped).
- Carried forward (r91/r92/r93/r94/r95): vitest/vite peer-skew repo-wide
  realign (so verdict + dataIntegrity + fred-liveness + data_integrity
  tests run in CI) ; README/ADR `## Index` back-fill 077→104 ; GBP
  Driver-3 (`IR3TIB01GBM156N`) ; cron 365d/yr holiday-gate (HIGH
  blast-radius) ; Pass-6 occasional ADR-017-token retry ; Dependabot 3
  main vulns (r49 baseline) ; KeyLevelsPanel $5 polymarket joke market.

## Process lessons (durable)

- **Run the project gate (tsc/eslint) on committed-shape code with NO
  ephemeral harness present ; the node-strip-types SSOT check is a fully
  separate step.** Conflating them produced a false tsc=2/lint=1 that was
  diagnosed (not shipped on) — but the clean discipline avoids the
  detour entirely. A polluted signal must be root-caused, never
  rationalised or ignored.
- **A reviewer's exact snippet can conflict with the codebase's own
  enforced convention — reconcile, don't blindly apply.** The a11y
  `role="list"` defended a legacy-UA bug the 2026 target no longer has,
  while violating the project's `no-redundant-roles` gate ; the WCAG
  _intent_ (list semantics) was delivered by `<ul>/<li>` alone +
  codebase consistency preserved.
- **Calibrated honesty on partial live-verification (lesson #11
  reinforced).** 2/3 tri-states live-witnessed ; DEGRADED honestly
  scoped as proven-by-test-and-review-but-not-live-on-a-priority-page,
  with the precise reason (AUD backend-only) — NOT rounded up to "all 3
  live" (the r87 forecast-as-fact failure class).
- **Triage a fresh surface's first signals to ground truth (lesson
  #13).** Both grep anomalies were resolved by inspecting the real DOM /
  HTTP status, not by assuming "probably fine".

## Next

**Default sans pivot:** ADR-099 **Tier 3 autonomy hardening continues**
— R59 first, pick highest value/effort: the r91/r92 doc/infra-hygiene
flags (vitest/vite peer-skew realign so verdict + dataIntegrity +
fred-liveness tests run in CI ; README/ADR `## Index` back-fill 077→104)
; or cron 365d/yr holiday-gate (HIGH blast-radius — register-cron/
systemd 2026-05-04 class, PRUDENCE + R59 + infra-auditor) ; or GBP
Driver-3 (`IR3TIB01GBM156N` ingestion + R53 prod-DB liveness first) ;
then Tier 4 premium UI. The next `continue` executes this default unless
Eliot pivots.

**Session depth: r95 + r96 in one session, both very large (full
ship + multi-subagent reviews each).** Well past the anti-context-rot
threshold for a single context. Per the standing brief ("ne grind pas
jusqu'à la dégradation") + the doctrine, **`/clear` is recommended now**
— pickup v26 + SESSION_LOG r95 + SESSION_LOG r96 are the zero-loss
anchor (current through r96) ; the next `continue` resumes cleanly.
