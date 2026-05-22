# Round 67 — EXECUTION ship summary

> **Date** : 2026-05-15 23:40 CEST
> **Trigger** : Eliot "continue" — r66 default Option B (gamma_flip data-quality bug visible on the dashboard)
> **Scope** : root-cause + 3-layer defense-in-depth fix for the gex gamma_flip garbage rendering on `/briefing`
> **Branch** : `claude/friendly-fermi-2fff71` → 30 commits ahead `origin/main`

---

## TL;DR

The r66 audit-gap (`gamma_flip` showing `+128.95%` nonsense on the
dashboard) was root-caused to a **collector data bug**, NOT proxy-scaling
as the r66 note guessed. The cumulative-from-low GEX sum crosses zero
spuriously at deep-OTM strikes (tiny low-OI gamma = numerical noise) ;
on days with no clean near-spot crossing the collector wrote a flip
56 % away from spot. Fixed with **3 defense-in-depth layers** (collector
band-filter + computer sanity-reject + frontend render-source
precedence), 5 regression tests, deployed, and **empirically verified on
the rendered dashboard : the garbage is GONE**.

---

## Root cause (verified, not guessed — R59 doctrine)

r66 flagged "proxy-scaling bug (QQQ/SPY ETF scale vs index scale)". r67
inspected the real `gex_snapshots` data on Hetzner and **disproved that
hypothesis** :

```
QQQ 2026-05-15 21:30  spot=710.74  flip=310.43  cw=710  pw=705  ← flip GARBAGE
QQQ 2026-05-15 14:30  spot=719.79  flip=715.00  cw=720  pw=715  ← flip SANE
QQQ 2026-05-14 21:30  spot=720.30  flip=716.48  cw=720          ← flip SANE
QQQ 2026-05-13 21:30  spot=715.60  flip=549.77  cw=715          ← flip GARBAGE
```

`spot` + `call_wall` + `put_wall` are **always consistent** (~705-720) ;
only `gamma_flip` intermittently goes garbage (310, 549). It's NOT a
systematic scale mismatch — it's `gex_yfinance.aggregate_dealer_gex`
lines 192-202 : it records EVERY zero-crossing of the cumulative-from-low
running GEX sum, then picks `min(crossings, key=abs(x-spot))`. Deep-OTM
strikes with tiny OI make the cumulative sum oscillate around zero far
from spot ; on days with no clean near-spot crossing, the "least-bad"
garbage crossing is selected. Walls are fine because they're
`max(per_strike, key=abs(gex))` → structurally near spot.

---

## 3-layer defense-in-depth fix (Ichor doctrine)

**Layer 1 — collector domain constraint** (`gex_yfinance.py`) :
`_GAMMA_FLIP_MAX_SPOT_DISTANCE_PCT = 0.15`. Only crossings within ±15 %
of spot are eligible ; if none in-band, `flip = None`. A real dealer
gamma flip is structurally proximate to spot (empirically the GOOD rows
are within ~1 %) — a missing flip is honest, a −56 % flip is corrupt.
Fixes all NEW gex_snapshots from the next cron fire.

**Layer 2 — computer read-path backstop** (`services/key_levels/gamma_flip.py`) :
`_GAMMA_FLIP_SANITY_MAX_DISTANCE_PCT = 0.25`. Rejects emitting a
KeyLevel if `|spot−flip|/flip > 25 %`. Protects against the garbage
ALREADY persisted in `gex_snapshots` before Layer 1 (the 310.43 row).
25 % > collector's 15 % deliberately — the computer hard-rejects only
the unambiguous garbage class, doesn't second-guess borderline collector
output.

**Layer 3 — frontend render-source precedence** (`/briefing/[asset]`) :
r65 preferred the persisted `card.key_levels` snapshot (r62). But a
session card generated BEFORE Layer 1+2 froze the garbage into its JSONB
— the dashboard kept rendering `+128.95%` from the frozen snapshot even
after the live API was clean. Corrected : for a LIVE pre-session
briefing ("comprends le marché _avant qu'il ouvre_" = current state),
live `/v1/key-levels` is the truth ; the persisted snapshot is for
explicit `/replay` (ADR-083 D4 "what was true then" semantic). r62
persistence is NOT wasted — it remains the replay source. Live first,
persisted fallback only on live-fetch failure.

---

## Regression tests (5 new, 31/31 pass)

`test_gex_yfinance.py` (+3) :

- `test_aggregate_far_otm_only_crossing_yields_none_flip` — the exact
  prod garbage class (far-OTM-only crossing) → `None`, not garbage
- `test_aggregate_single_crossing_just_in_band_is_kept` — ~10 % crossing
  kept (no over-rejection)
- `test_aggregate_single_crossing_just_out_of_band_is_rejected` — ~30 %
  crossing → `None` (pins the band gate)

`test_key_levels_gamma_flip.py` (+2) :

- `test_implausibly_far_flip_rejected_r67` — the literal prod row
  (QQQ spot 710.74 / flip 310.43) → no KeyLevel
- `test_plausible_flip_still_emitted_r67` — sane flip (spot 719.79 /
  flip 715.00) still emits normally (guard doesn't over-reject)

---

## Empirical verification (R18/R59 — real prod data + rendered dashboard)

| W   | Check                                                              | Result                                                                  |
| --- | ------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| W1  | 31/31 gex + gamma_flip unit tests                                  | PASS (5 new r67)                                                        |
| W2  | Hetzner deploy : gex_yfinance.py + gamma_flip.py + chown + restart | ichor-api active ✓                                                      |
| W3  | Live `/v1/key-levels` post-deploy : gamma_flip count               | **0** (the 310.43 −56 % garbage rejected) ; total 10→8 ✓                |
| W4  | Dashboard `/briefing/EUR_USD` body scan post Layer-3               | NO `310.43` / `128.95` / `58.72` / "Gamma flip" ✓                       |
| W5  | Dashboard KeyLevel families rendered                               | TGA + HKMA + VIX + SKEW + HY OAS + Polymarket (6 clean, zero garbage) ✓ |
| W6  | Dealer GEX section screenshot                                      | shows only sane call_wall 710.00 ≈ spot ; no `+128.95%` nonsense ✓      |

Not "ça marche structurellement" — **the garbage is empirically GONE
from the actual rendered dashboard with real Hetzner prod data**.

---

## Files changed r67

| File                                                       | Change                                     | Lines     |
| ---------------------------------------------------------- | ------------------------------------------ | --------- |
| `apps/api/src/ichor_api/collectors/gex_yfinance.py`        | Layer 1 : band-filter crossings ±15 % spot | +25       |
| `apps/api/src/ichor_api/services/key_levels/gamma_flip.py` | Layer 2 : sanity-reject >25 %              | +18       |
| `apps/api/tests/test_gex_yfinance.py`                      | +3 band regression tests                   | +44       |
| `apps/api/tests/test_key_levels_gamma_flip.py`             | +2 sanity-reject tests                     | +27       |
| `apps/web2/app/briefing/[asset]/page.tsx`                  | Layer 3 : live-first render precedence     | +12       |
| `docs/SESSION_LOG_2026-05-15-r67-EXECUTION.md`             | NEW                                        | this file |

Hetzner state : gex_yfinance.py + gamma_flip.py deployed + restart +
verified (no git diff for the deploy itself).

---

## Self-checklist r67

| Item                                                                   | Status |
| ---------------------------------------------------------------------- | ------ |
| Root-caused via REAL data (disproved the r66 proxy-scaling guess)      | ✓      |
| 3-layer defense-in-depth (collector + computer + frontend)             | ✓      |
| 5 regression tests, 31/31 pass                                         | ✓      |
| Hetzner deploy + restart + live-API verified gamma_flip=0              | ✓      |
| Dashboard empirically verified garbage GONE (real prod data)           | ✓      |
| Scope discipline (gamma_flip only ; walls confirmed fine, not touched) | ✓      |
| No over-rejection (sane flips still emit — tested)                     | ✓      |
| TS clean + lint clean                                                  | ✓      |
| Voie D + ZERO Anthropic API spend                                      | ✓      |
| R18/R59 satisfied (real prod data, rendered)                           | ✓      |

---

## Master_Readiness post-r67

**Closed by r67** :

- ✅ gamma_flip garbage (r66 audit-gap) — 3-layer fix, deployed, dashboard-verified clean
- ✅ Root-cause discipline : disproved the r66 proxy-scaling guess with real data (R59)
- ✅ Frontend render-source semantics clarified (live=briefing, persisted=replay)

**Still open** :

- ⏳ gamma_flip KeyLevels currently absent (all live gex_snapshots rows pre-date Layer 1) — self-heals at next gex cron fire (13:00/21:00 Paris) producing in-band flips. Expected, not a defect.
- ⏳ CF Pages deploy (Eliot manual) for persistent URL ; SSH-tunnel works for now
- ⏳ r68+ : scenarios Pass-6 tree + news feed + economic calendar on `/briefing/[asset]`
- 1 silent-dead collector (`cot`)

**Confidence post-r67** : ~97% (a trust-destroying visible bug eliminated + root-caused properly, not patched on a guess)

---

## Branch state

`claude/friendly-fermi-2fff71` → 30 commits ahead `origin/main`. **17 rounds (r51-r67) en 1 session** :

- r51-r60 : safety/collectors/ADR-083 D3
- r61 : ADR-097/098 + FRED liveness CI
- r62 : SessionCard.key_levels persistence
- r63 : Hetzner deploy + CI guards
- r64 : brain venv path consolidation
- r65 : FRONTEND UNGELED — /briefing dashboard MVP
- r66 : live-data verification + PROD sessions-500 fix
- **r67 : gamma_flip 3-layer data-quality fix + dashboard-verified clean**

À ton "continue" suivant :

- **A** : r68 frontend phase 2 — scenarios Pass-6 tree + news feed + economic calendar on `/briefing/[asset]` (the dashboard is now trustworthy enough to build depth on)
- **B** : CF Pages private deploy setup (persistent URL — needs Eliot `gh secret` OR Hetzner-host pivot)
- **C** : sentiment panel — COT/MyFXBook positioning ("ce que les gens font")
- **D** : `cot` collector last silent-dead (HIGH risk, dedicated ADR Socrata)

Default sans pivot : **Option A** (r68 frontend phase 2 — the foundation
is now verified-clean, so building depth no longer stacks on garbage ;
directly serves Eliot's "couvrir tout le champ du possible" vision).
