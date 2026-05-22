# Round 66 — EXECUTION ship summary

> **Date** : 2026-05-15 23:10 CEST
> **Trigger** : Eliot "continue" — r66 chose live-data empirical verification over stacking more features (anti-accumulation discipline)
> **Scope** : verify the r65 dashboard against REAL Hetzner data via SSH tunnel ; fix what breaks ; discovered + fixed a latent PRODUCTION bug
> **Branch** : `claude/friendly-fermi-2fff71` → 29 commits ahead `origin/main`

---

## TL;DR

r66 chose **verification over accumulation**. Instead of stacking r66
features on the unverified r65 MVP, it SSH-tunnelled to the live Hetzner
API (zero public exposure — honors "ultra sécurisé du public le plus
caché") and rendered the dashboard with **real production session-card
data**. This caught **a latent production bug that has nothing to do with
the frontend** : `/v1/sessions` + `/v1/sessions/{asset}` have been
**500-ing in prod** for every `ny_mid`/`ny_close` card since the W101e
partial fix. Fixed + deployed + empirically verified. The dashboard now
renders real EUR/USD `ny_close` session card end-to-end : bias, conviction,
regime, KeyLevels, mechanisms, invalidations, catalysts.

---

## The production bug (highest-value find of the round)

**Symptom** : `/v1/sessions/EUR_USD` → HTTP 500.

**Root cause** (from Hetzner `journalctl`) :

```
File "routers/sessions.py", line 104, in list_sessions_for_asset
pydantic_core.ValidationError: 1 validation error for SessionCardOut
  Input should be 'pre_londres', 'pre_ny' or 'event_driven'
  [input_value='ny_close']
```

`schemas.py:329` `SessionCardOut.session_type` was
`Literal["pre_londres","pre_ny","event_driven"]` (**3 values**) but the
canonical `ichor_brain.types.SessionType` (ADR-031 single source) is
**5 values** (`+ny_mid +ny_close` — the 4-windows/day × 8-assets design,
CLAUDE.md "32 cards/day target"). Every card written in the `ny_mid` or
`ny_close` window made `from_orm_row()` raise → both `/v1/sessions` and
`/v1/sessions/{asset}` 500.

**Why it survived** : W101e fixed the _input_ `_SESSION_TYPE_RE` regex in
`sessions.py` + `calibration.py` (acknowledged in the sessions.py:40
comment) but **missed the _output_ `SessionCardOut` Literal**. Classic
partial fix — the input contract was widened, the output schema wasn't.
It was invisible because `/v1/today` (the only live consumer) uses
`TodaySessionPreview` which has no `session_type` field.

**Fix** : `schemas.py:329` widened to the canonical 5-value Literal +
explanatory comment referencing ADR-031 source-of-truth. Widening a
Literal only accepts more valid values — zero risk to existing callers.
**Deployed to Hetzner this round** (scp + chown + restart) + verified :
`/v1/sessions/EUR_USD` → **HTTP 200** (returns the `ny_close` card that
was crashing it), `/v1/sessions` → **HTTP 200**.

---

## Frontend real-data fixes (R59 doctrine — structure ≠ proof)

The r65 MVP "worked" against an offline API (graceful empty states). r66
proved it was **wrong against real data** in 3 ways :

1. **Wrong endpoint** : r65 `fetchSessionCardForAsset` called
   `/v1/sessions?asset=X&limit=1` (query params on the list endpoint
   that ignores them + 500'd). Real endpoint is `/v1/sessions/{asset}`
   (path param, returns `SessionCardList`). Fixed.

2. **`session_type` type drift** : `lib/api.ts:152` `SessionCard` +
   `BriefingHeader` `SESSION_LABEL` were 3-value (would crash / show
   undefined label on the real `ny_close` card). Widened to 5 values
   (the TypeScript `Record<session_type,string>` enforced the fix).

3. **NarrativeBlocks wrong shape** : r65 used a generic `extractText`
   field-probe (`description/text/why/...`) that did NOT match the real
   Pass-2 schema. Real shapes (verified against prod) :
   - `mechanisms[]` : `{claim, sources[]}` — `claim` was NOT probed →
     would render raw JSON
   - `invalidations[]` : `{source, condition, threshold}` — `threshold`
     (the actionable number) was buried
   - `catalysts[]` : `{time, event, expected_impact}` —
     `expected_impact` not surfaced, `time` field name not in probe list

   Rewrote NarrativeBlocks with **3 shape-aware renderers** : mechanisms
   show claim + source pills ; invalidations show condition + a
   highlighted amber threshold badge + source stamp ; catalysts show a
   cobalt timestamp + event + expected-impact. Defensive JSON fallback
   retained for drift.

---

## Empirical 4-witness (real prod data, screenshot-verified)

| W   | Check                                         | Result                                                                                                                                             |
| --- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| W1  | `/v1/sessions/EUR_USD` HTTP status post-fix   | 200 (was 500) ✓                                                                                                                                    |
| W2  | `/v1/sessions` HTTP status post-fix           | 200 (was 500) ✓                                                                                                                                    |
| W3  | `/briefing/EUR_USD` SSR render via SSH tunnel | header shows "CLÔTURE NEW YORK" (ny_close label) + "▼ −SHORT" + conviction 32% + "USD complacency" regime + magnitude 25→55 ✓                      |
| W4  | KeyLevels render real snapshot                | TGA $838.4B + HKMA peg 7.85 + GEX + SKEW 139.3 + HY OAS 2.76% + 3 polymarket, grouped + source-stamped ✓                                           |
| W5  | NarrativeBlocks real Pass-2                   | 5 mechanisms (claim+sources pills) + 5 invalidations (condition+threshold badges 1.1640/117.50/4.38/21.0/0.10) + 3 catalysts (time+event+impact) ✓ |
| W6  | `/briefing` landing macro cards               | RISK APPETITE 0.70 EXTREME_RISK_ON + FUNDING STRESS 0.10 + VIX 17.3 CONTANGO + live "Pré-Londres dans 7h58" countdown ✓                            |
| W7  | Console errors                                | 0 ✓                                                                                                                                                |

**This is R18/R59 fully satisfied** : not "ça marche structurellement"
but "ça marche exactement avec la vraie data prod, vérifié visuellement".

---

## Audit-gap flagged (NOT fixed — scope discipline)

Real KeyLevels exposed a **backend data bug** : `gamma_flip` for
NAS100/SPX500 shows nonsense :

```
"Spot 710.74 above flip 310.43 (+128.95%)"   (NAS100, QQQ proxy)
"Spot 740.37 above flip 466.47 (+58.72%)"    (SPX500, SPY proxy)
```

QQQ price (~710) vs a flip level (~310) → +128.95% distance is
absurd. The `gamma_flip` computer's proxy-scaling (ADR-089 QQQ→NAS100 /
SPY→SPX500) produces flip levels at the proxy ETF scale, not the index
scale. **NOT fixed r66** (scope = sessions 500 + frontend real-data ;
this is a separate `services/key_levels/gamma_flip.py` computation bug).
Flagged as r67+ audit-gap.

---

## Files changed r66

| File                                                | Change                                                         | Lines          |
| --------------------------------------------------- | -------------------------------------------------------------- | -------------- |
| `apps/api/src/ichor_api/schemas.py`                 | SessionCardOut Literal 3→5 windows (PROD bug fix, deployed)    | +12            |
| `apps/web2/lib/api.ts`                              | SessionCard.session_type 5-window                              | +3             |
| `apps/web2/components/briefing/BriefingHeader.tsx`  | SESSION_LABEL +ny_mid +ny_close                                | +2             |
| `apps/web2/app/briefing/[asset]/page.tsx`           | correct `/v1/sessions/{asset}` endpoint + SessionCardList type | ~8             |
| `apps/web2/components/briefing/NarrativeBlocks.tsx` | full shape-aware rewrite (3 real Pass-2 schemas)               | ~210 (rewrite) |
| `docs/SESSION_LOG_2026-05-15-r66-EXECUTION.md`      | NEW                                                            | this file      |

Hetzner state change : `schemas.py` deployed + ichor-api restarted +
`/v1/sessions*` 500→200 verified (no git diff for the deploy itself).

---

## Self-checklist r66

| Item                                                                 | Status |
| -------------------------------------------------------------------- | ------ |
| Chose verification over accumulation (anti-accumulation discipline)  | ✓      |
| SSH tunnel — zero public exposure (security directive honored)       | ✓      |
| Production bug found + root-caused via journalctl                    | ✓      |
| Backend fix deployed Hetzner + HTTP 200 verified                     | ✓      |
| Frontend 3 real-data bugs fixed (endpoint, type drift, shape)        | ✓      |
| TS clean + lint clean                                                | ✓      |
| Real-data render screenshot-verified (7 witnesses)                   | ✓      |
| R18/R59 doctrine satisfied (real prod data, not structure)           | ✓      |
| gamma_flip proxy-scaling bug flagged as audit-gap (scope discipline) | ✓      |
| Voie D + ZERO Anthropic API spend                                    | ✓      |
| Frontend gel : N/A (ungeled r65)                                     | ✓      |

---

## Master_Readiness post-r66

**Closed by r66** :

- ✅ `/v1/sessions` + `/v1/sessions/{asset}` PRODUCTION 500 (latent since W101e) — fixed + deployed + verified
- ✅ r65 dashboard empirically verified against REAL Hetzner data (was structure-only)
- ✅ NarrativeBlocks now matches real Pass-2 schema (mechanisms/invalidations/catalysts)
- ✅ session_type 3→5 drift closed across backend + frontend (doctrinal hygiene)

**Still open** :

- ⏳ CF Pages deploy (Eliot manual `gh secret set CLOUDFLARE_API_TOKEN`) — for a persistent URL ; SSH-tunnel works for now
- ⏳ NEW audit-gap : `gamma_flip` proxy-scaling bug (QQQ/SPY proxy flip levels at wrong scale) — r67+
- ⏳ r67+ : scenarios Pass-6 tree + news feed + economic calendar + sentiment on `/briefing/[asset]`
- 1 silent-dead collector (`cot`)

**Confidence post-r66** : ~96% (frontend now empirically verified with real data + a real prod bug closed ; +4pp vs r65's honest 92%)

---

## Branch state

`claude/friendly-fermi-2fff71` → 29 commits ahead `origin/main`. **16 rounds (r51-r66) en 1 session** :

- r51-r60 : safety/collectors/ADR-083 D3
- r61 : ADR-097/098 + FRED liveness CI
- r62 : SessionCard.key_levels persistence
- r63 : Hetzner deploy r62 + CI guards
- r64 : brain venv path consolidation
- r65 : FRONTEND UNGELED — /briefing dashboard MVP
- **r66 : live-data verification + PROD sessions-500 fix + NarrativeBlocks real-shape rewrite**

À ton "continue" suivant :

- **A** : r67 frontend phase 2 — scenarios Pass-6 tree + news feed + economic calendar on `/briefing/[asset]`
- **B** : fix the `gamma_flip` proxy-scaling backend data bug (r66 audit-gap — KeyLevels show nonsense for NAS100/SPX500)
- **C** : CF Pages deploy setup for a persistent private URL (needs Eliot `gh secret` OR Hetzner-host pivot)
- **D** : sentiment panel (COT/MyFXBook positioning — "ce que les gens font")

Default sans pivot : **Option B** (fix gamma_flip proxy-scaling — it's a
real data-quality bug now VISIBLE on the dashboard Eliot will look at ;
wrong numbers on a premium UI erode trust faster than missing features).
