# SESSION_LOG 2026-05-16 — Round 80 (ADR-099 Tier 1.4a: institutional positioning backend)

> Round type: **backend endpoint** (deployed via vetted redeploy-api.sh).
> Branch `claude/friendly-fermi-2fff71`. ZERO Anthropic API spend.
> Voie D + ADR-017 held. Trigger: Eliot "continue" → ADR-099 Tier 1.4.

## Scope decision (announced, position-sizing — proven r76/r77 split)

R59: only `/v1/positioning` (MyFXBook RETAIL) existed. The audit gap =
"Layer 7 acteurs-du-marché PARTIAL — no CFTC/COT institutional ;
SPX500/NAS100 positioning DARK". Institutional positioning is the
biggest distinct gap (smart money vs retail). Split like r76/r77:
**1.4a (this round) = backend endpoint + deploy + verify** ;
**1.4b (next) = frontend panel**. AAII equity-sentiment deferred to a
Tier-1.4 follow-up (sentiment layer 6 is already PARTIAL via news-tone ;
institutional positioning is the higher-value structural gap).

## What r80 shipped

`GET /v1/positioning/institutional?asset=X` — **extends the existing
`routers/positioning.py`** (anti-doublon, not a new router). Mirrors
`data_pool._section_tff_positioning` + `_section_cot` EXACTLY (same
trader conventions) so the dashboard surfaces the SAME institutional
read the 4-pass LLM sees:

- **TFF** (CftcTffObservation): 4-class nets (Dealer/AssetMgr/LevFunds/
  Other) + Δw/w + smart-money-divergence flag. Covers **all 5 priority
  assets incl. SPX500 (13874A)** — fills the SPX/NAS dark gap.
- **COT** (CotPosition): managed_money_net + swap_dealer + producer +
  Δ1w/Δ4w/Δ12w + accelerating/reversal pattern. Covers 4 (no SPX500
  E-mini in the collector yet — honest `null`, ADR-093).
- Market-code maps imported **lazily from data_pool** (single source of
  truth — if Eliot adds SPX500 to COT later, both the LLM section AND
  this endpoint update together ; lazy import = zero circular-import
  risk against that very large module).
- Honest `cadence` field ("hebdomadaire, données arrêtées au mardi") +
  `report_date` so the weekly CFTC lag is explicit (no fake freshness).
  ADR-017-safe: pure positioning facts + a descriptive divergence flag.

## Empirical witnesses (R59 — "marche exactement")

- `uv run ruff check` = "All checks passed!"; `py_compile` OK pre-deploy.
- Deploy: SSH throttled at Step 4 (recurring this long session) →
  completed via the proven single-consolidated-SSH (restart + verify +
  auto-rollback). New code on disk + un-restarted service = old code
  (safe intermediate, no regression — same as r76/r78).
- Live verified: `healthz=200`.
  - `EUR_USD`: `tff` populated (market 099741, report_date 2026-05-12,
    OI 829,377, dealer_net −353,218, asset_mgr_net +290,280,
    lev_money_net +18,003, Δw/w present, divergence=false) ; `cot=null`
    (cot_positions has no 099741 rows — honest degraded, identical to
    the in-prod `_section_cot` behaviour, NOT a bug).
  - `SPX500_USD`: `tff` populated (market 13874A, report_date
    2026-05-12, OI 2,056,229, dealer_net −736,273, asset_mgr_net
    +1,054,872, lev_money_net −432,438) → **institutional positioning
    now exists for the previously-dark SPX500**.

### Data-availability note (Tier-3 candidate, NOT a r80 bug)

`cot_positions` returned no rows for EUR (099741). The COT collector
appears not to populate FX the way TFF does — consistent with the
broader audit's "silent-skip" concern. Surfaced honestly as `cot:null`.
Flag for the Tier-3 autonomy-hardening backlog (degraded-data alert),
not fixed here (anti-accumulation: one increment per round).

No dedicated unit test added: the endpoint is a faithful projection of
two `_section_*` functions already running in prod (established
behaviour) — a unit test would mostly re-test the mirror. Verification
= live real-data check (proportionate, consistent with r76 precedent).

## Next stage (on Eliot "continue")

ADR-099 **Tier 1.4b — InstitutionalPositioningPanel.tsx** (frontend,
house style): TFF 4-class bars + smart-money-divergence flag + COT
managed-money trend, consuming `/v1/positioning/institutional?asset=X`
via a `getInstitutionalPositioning` api.ts helper ; wire into
`page.tsx` near the existing "Positionnement" (retail) section ;
honest `report_date` staleness + `cot:null` empty-state. Then T1.5
correlations unconditional.

## Checkpoint

Commit: routers/positioning.py + this SESSION_LOG on
`claude/friendly-fermi-2fff71`. Backend deployed (scp). Memory updated separately.
