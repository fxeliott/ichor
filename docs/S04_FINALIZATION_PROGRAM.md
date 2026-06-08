# S04 — Finalization Program (turnkey, ranked, file:line-precise)

> Built 2026-06-07 from the 8-agent adversarial re-verify (`wf_806bbb9c`) + the
> prior 10-agent depth audit. Canonical gap record: memory
> `D--Ichor/ichor-s04-reverify-2026-06-07` + `ichor-s04-dimension-depth-audit-2026-06-07`.
>
> **State**: S04 = 9/9 dimensions WIRED + 50/50 killed (live in prod, cron `--live`).
> Spec bar « chaque dimension poussée au maximum, sans zone d'ombre » = NOT met.
> 0/9 maxed. This file is the executable sequence to close it.
>
> **Update 2026-06-09**: TIER-2 #2 (Volume = real RVOL layer) is SHIPPED, DEPLOYED and
> WITNESSED in prod (PR #204, `4f3fa94`). The Volume dimension now carries a real depth
> read (RVOL ratio, 60d z-score, participation bucket), not just a weight — the first
> dimension to get genuine per-dimension depth. See the DONE note in TIER-2 #2 below and
> `docs/SESSION_LOG_2026-06-09-s04-volume-rvol.md`.
>
> **Witness rule (Eliot criterion ⑥)**: every brain-path (data_pool / verdict) change
> below is DONE only after `redeploy-api.sh` + a live card witness. The pure-logic
> parts are unit-testable locally; the runtime witness is the deploy step.

## DONE this session (verified, on branch `claude/s04-fx-volume-disclaimer`)

- **FX volume disclosure** (`microstructure.py`) — commit `41e9976`. EUR/GBP Polygon FX
  carry no volume → 4/6 metrics read n/a; now an explicit "volume not reported" note so
  the brain treats it as a data property, not a gap. pytest 22 passed, ruff+ADR-081 ✓.
  **Witness pending**: deploy → an EUR_USD card shows the note.

## Theme of the remaining program: « make absence/staleness explicit »

The systemic root the audit found: the brain cannot distinguish FRESH / STALE / ABSENT
for any non-FRED source. The FX-volume fix is one instance. The program below
generalizes that, then fills the real per-dimension depth gaps.

## TIER 1 — systemic (highest leverage, do first)

1. **Generalize the liveness primitive to non-FRED tables** [high].
   Today `_section_data_integrity` + `_MACRO_CORE_ANCHORS`/`_ASSET_CRITICAL_ANCHORS`
   (data_pool.py:418-460) audit ONLY ~6 FRED series. 6 non-FRED tables render
   stale-as-fresh with zero trace: NyfedMct (4163), ClevelandFed (4376), NFIB (4030),
   COT (4284), TFF (4231), GPR (4506).
   - Pure: add `assess_table_staleness(latest_obs_date, now, max_age_days) -> DegradedInput|None`
     (unit-testable now). Generalize `DegradedInput` to carry `source_key` not just FRED `series_id`.
   - Wire: each `_section_*` emits a STALE band + appends to the shared degraded list;
     rename integrity header (data_pool.py:5495) "critical FRED anchor(s)" → "critical anchor(s)".
   - **Critical sub-case**: `_section_cross_asset_matrix` (data_pool.py:3502-3529) feeds the
     Pass-1 regime classifier with NO age check → stale MCT/Cleveland actively poison the
     regime band. Gate these first.
   - Witness: kill a non-FRED collector in staging → integrity header counts it.

## TIER 2 — real per-dimension depth (the « zone d'ombre » per dimension)

2. ✅ **DONE — Volume = real RVOL layer** [high] (PR #204, `4f3fa94`, witnessed prod
   2026-06-09). `microstructure.py` gains `RelativeVolumeReading`, pure
   `classify_relative_volume` (RVOL ratio vs 20d avg, 60d volume z-score,
   non-directional participation bucket), `assess_relative_volume` (daily
   `market_data` bars), and `render_relative_volume_block`. `data_pool.py` gains
   `_section_volume_rvol` (3-tuple, liveness-gated) wired into `build_data_pool` and
   `build_asset_data_only`. Scope (empirically witnessed): SPX500/NAS100/XAU carry
   real daily volume; FX gets an honest N/A by data property (zero DB I/O). Empty or
   stale series surface an ABSENT/STALE band plus a degraded trace. ADR-017-safe
   (descriptive, non-directional). 30 tests. Witness: SPX RVOL 0.88×, NAS 0.96×,
   XAU 1.03×, EUR_USD honest N/A, all `degraded=[]`.
3. ✅ **DONE (code) — Geopolitics per-asset** [med] (PR #206, `b738ab9`, witnessed prod
   2026-06-09). `_section_geopolitics(session, asset)` narrows the GDELT negative-event
   cluster via `filter_rows_by_asset_affinity` (title+query_label+domain+url,
   min_required=3, scarce→global fallback), mirroring `_section_news` +
   `routers/geopolitics.py` (pool aligned to router top×8). AI-GPR stays global. 7 tests,
   ruff/mypy clean. **Honest runtime caveat**: on the current 24h GDELT window all assets
   fell back to global (matched 0–1 < 3) → the per-asset differentiation is DATA-GATED; it
   activates on per-asset geo density (ECB day, gold shock…). The lever for routine
   differentiation = richer per-asset GDELT queries (Session-03 collector), NOT this section.
4. **Acteurs / TFF coverage** [high, NEEDS domain call]. cftc_tff collects 15 markets;
   consumer `_TFF_MARKET_BY_ASSET` (data_pool.py:206-215) uses 8. CHF/NZD/RUT/UST-2/5/10/30Y
   never surface per-asset. Extending requires a SEMANTIC decision (which TFF market informs
   which asset, e.g. UST_10Y → SPX/NAS rate-sensitivity?) — Eliot/analyst call, not mechanical.
   Add a guard test `consumer ⊆ collector` to prevent silent drift.
5. **Sentiment orphan wire** [low]. CRYPTO_FNG persisted (run_collectors.py:1490), zero
   analysis reader → add to a sentiment section (extremes ≤20/≥80 as risk context).
6. **Volume orphan** [low]. FinraShortVolume persisted, zero reader (needs finra_api_token).
   Either wire a short-interest section or drop the dead collector.
7. **News depth** [low]. Surface couche2 `asset_sentiment` + `entities`
   (couche2_persistence.py:107-115 drops them). Distinguish asset-news vs world-news
   (today they collapse to the same global feed for thin assets).

## TIER 3 — robustness / honesty (no new dimension, hardens existing)

8. **Conviction dollar self-reference** [low]. run_session_card.py:163 injects the card's
   own bias into the consensus that later corroborates it. Leave-one-out, or document the
   ≥2-directional guard bounds it.
9. **Macroeconomic theme activation** [low]. After S03 DTWEXBGS backfill (≥30 rows), the
   gate is still AND-conditioned on VIX>30 (theme_classifier.py:745) → DXY-extreme alone
   never fires. Decide: graded standalone contribution vs document as a co-occurrence regime.
10. **Async-DB integration test** for `build_session_verdict` fusion seam (the keystone has
    no end-to-end automated test — test_session_verdict_fusion_seam.py:8-10 defers to the
    live witness). Needs a migrated test DB.

## ARCHITECTURE decisions (Eliot's call — not mechanical)

- **Couche-1 has ZERO model fallback** [high]. Cerebras/Groq FallbackChain wraps only the
  5 Couche-2 agents; orchestrator.py retries the same Win11 runner then raises. SPEC.md:86
  implies global fallback → spec vs code mismatch. Options: (A) accept premium-only +
  fail-loud (document, reconcile SPEC); (B) add a degraded Cerebras/Groq path for briefings
  behind an explicit "degraded provenance" watermark. Trade-off: HA conflicts with Max-20x
  single-user ToS — the whole Voie-D premise.
- **SPEC.md model version** stale (Opus 4.7 vs code/ADR-108 4.8) — refresh under the repo's
  ADR-supersedes-spec convention (Eliot's doc-convention call).

## NOT a defect (corrected this session)

- "DB password leak" close-note = **false alarm** (no asyncpg/pg_dump in audit.log/transcripts;
  audit.log stores only truncated command lines). No rotation needed unless the pw was seen
  on a shared screen.
- "manipulation magnet aggregates gamma/COT/skew" = the CODE is honest ("cross-read, not
  duplicated"); only the PR narrative overclaimed.
- geopol z-scores = NOT orphans (live readers via the alert path).
