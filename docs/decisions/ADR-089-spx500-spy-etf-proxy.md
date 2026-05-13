# ADR-089: SPX500_USD → SPY ETF proxy (Polygon Indices 403 mitigation, Voie D budget discipline)

**Status**: Accepted (round-32b ratify, 2026-05-13) — SPY proxy shipped round-27 commit `eaaff82` (`data_pool.py:_ASSET_TO_POLYGON["SPX500_USD"] = "SPY"` + tests updated to accept `{SPY, I:SPX}`). Reversible via 1-line revert if Polygon Indices Starter is later budgeted (cf. pricing TBD — re-verify with polygon.io before purchase).

**Date**: 2026-05-13

**Supersedes**: none

**Extends**: [ADR-083](ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md) D1 (6-asset universe : EURUSD, GBPUSD, USDCAD, XAUUSD, NAS100, **SPX500**), [ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D spend discipline).

## Context

The Polygon (rebranded **Massive** since 2026) collector at `apps/api/src/ichor_api/collectors/polygon.py:39-63` maps `SPX500_USD → I:SPX`. The Stocks Starter plan ($29/mo, already paid) does NOT include the cash index `I:SPX` — that's gated behind the **Indices** plan add-on ($49/mo Starter 15-min delayed, $99/mo Advanced real-time as of 2026-05).

Consequence : every `GET /v1/aggs/ticker/I:SPX/range/...` returns HTTP 403. 1/6 of the D1 universe is dark. Pass-2 SPX500 framework (`packages/ichor_brain/src/ichor_brain/passes/asset.py:143-154`) consumes ISM / NFP / CPI / Fed-cut prob / dealer GEX / VIX term slope / HY OAS / AAII — none of these require millisecond-precision cash level, but Pass-2 still needs **price bars** for stamping `data_pool` snapshots (range, ATR, momentum context).

Round-27 researcher analysis enumerated 4 options. This ADR captures the decision matrix and recommends Option 3.

## Decision

### Recommended : Option 3 — SPY ETF proxy

Patch the collector ASSET_TO_TICKER mapping :

```python
# apps/api/src/ichor_api/collectors/polygon.py (lines 39-63 area)
ASSET_TO_TICKER: dict[str, str] = {
    "EUR_USD": "C:EURUSD",
    # ... unchanged for FX pairs ...
    "NAS100_USD": "I:NDX",  # NAS100 stays on I:NDX (covered by current plan)
    # SPX500_USD : aliased to SPY (NYSE Arca) until Polygon Indices
    # plan ($49/mo Starter) is budgeted. SPY tracks I:SPX with <0.1% MTD
    # tracking error — invisible for Pass-2 qualitative framework
    # (asset.py:143-154 drivers are ISM/NFP/CPI/GEX/HY OAS, not
    # absolute close levels). To revert : change "SPY" back to "I:SPX"
    # AFTER upgrading the Polygon plan. Single-line revert.
    "SPX500_USD": "SPY",  # was "I:SPX" — 403 on Stocks Starter plan
    # ...
}
```

### Why Option 3 wins (4-way analysis)

| Option                                | Recurring cost                                                    | Effort                                                                                                                                           | Tracking error vs cash SPX                                                                                                                 | Voie D / ADR-017 doctrinal                                                                                                                     | Reversibility                                                                                   | Pass-2 edge                                                                           |
| ------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| **1. Polygon Indices Starter $49/mo** | **$49/mo = $588/yr** ; real-time = $99/mo                         | 0.5h (plan upgrade + collector unchanged)                                                                                                        | 0 (true index)                                                                                                                             | Voie D : tolerable (data API, not LLM API). Cost discipline pressure : $588/yr is non-trivial for "marginal-over-SPY" lift                     | Trivial : downgrade plan = 403 returns, dict unchanged                                          | Maximal cash-level fidelity. But 15-min delay rends edge marginal for 4-pass intraday |
| **2. ES futures proxy `/ES`**         | Unknown (Massive Futures tier pricing opaque ; likely $50-200/mo) | 3-5h : add CME continuous + rollover front→next month + basis adj                                                                                | ~0.3-1.5% drift (cost-of-carry, dividend strip). Non-blocking for direction/régime — Pass-2 doesn't read level absolu                      | Voie D tolerable. ADR-017 neutral                                                                                                              | Moderate : rollover handler is permanent complexity ; CFTC TFF already covers positioning bonus | Good (volume + open interest) but redundant with CFTC TFF                             |
| **🥇 3. SPY ETF proxy (RECOMMENDED)** | **$0** (Polygon Stocks Starter $29/mo already covers SPY)         | **1-2h** : one-line patch + smoke test                                                                                                           | ~0.01% intraday (NAV spread tight) ; ~0.1% MTD (dividend timing) ; 0.0945% annual expense ratio — **imperceptible for qualitative Pass-2** | Voie D ✅ zero new spend. ADR-017 ✅ standard market data, neutral                                                                             | **Trivial** : revert to `I:SPX` = one-line change when Indices plan upgraded later              | Sufficient. Pass-2 reasons on macro drivers, not exact SPX close                      |
| **4. Drop SPX500 from D1**            | $0                                                                | 2-3h : ADR supersedes ADR-083 D1, remove from collector + framework + cron + tests + docs/CLAUDE.md + frontend `/today` + calibration scoreboard | N/A                                                                                                                                        | Voie D ✅. ADR-017 ✅. But **violates intent of ADR-083 §16-17** — Eliot explicitly listed SPX500 in the 6 traded assets. Doctrinal regression | Moderate : re-add SPX500 later = ratify new ADR + migration + tests                             | Negative : 1/6 dark = trader loses an asset they actually trade                       |

### Acceptance criteria

1. `apps/api/src/ichor_api/collectors/polygon.py` patched ; `ASSET_TO_TICKER["SPX500_USD"] = "SPY"`.
2. Empirical 3-witness proof (rule 18) :
   - **Witness 1** : unit test `test_polygon_spx500_maps_to_spy` PASS.
   - **Witness 2** : `curl GET /v1/market/intraday?asset=SPX500_USD&from=...&to=...` returns 200 OK with ~390 bars/day NYSE RTH.
   - **Witness 3** : sample session-card persisted post-fix for `SPX500_USD/new_york` window has non-null `polygon_intraday_section` in data-pool.
3. CI guard `test_spx500_uses_etf_proxy_or_indices_plan` documents the current state and asserts `ASSET_TO_TICKER["SPX500_USD"] in {"SPY", "I:SPX"}` (allows future upgrade).
4. Comment in `polygon.py` documents the tracking-error rationale + revert procedure.

### Future "level conversion" hint (deferred)

If a downstream consumer (e.g., future W106 `key_levels[]` dealer GEX in SPX index points) needs cash-SPX magnitudes, add a separate `services/spy_to_spx_proxy.py` with empirical multiplier (ratio ~10 : SPY $740 ≈ SPX 7400 in 2026). This stays out of the collector layer (separation of concerns).

## Reversibility

- **Trivial** : `ASSET_TO_TICKER["SPX500_USD"] = "I:SPX"` if Polygon Indices Starter activated.
- **No schema migration** : table `polygon_intraday` is asset-agnostic.
- **Frontend** : `/today/SPX500_USD` keeps the same route. UI doesn't care about ticker identity.

## Consequences

### Positive

- **Zero recurring spend** : honors Voie D budget discipline (rule 16 spirit).
- **Unblocks SPX500 cards** : 4 cards/day × 4 sessions = 16/week SPX500 contextual analyses that were dark.
- **One-line patch** : low risk, easy code-review.
- **Future-flexible** : when Eliot decides Indices Starter $49/mo is worth it for W106 cash-level gamma flip work, revert is one string.

### Negative

- **Tracking error 0.1% MTD on the "absolute level"** of SPX500 cards : negligible for direction + régime but introduces a small bias in any consumer that compares `polygon_intraday.close` to a fixed SPX-points threshold. Mitigation = if W106 `key_levels[]` SPX points lands, ship `services/spy_to_spx_proxy.py` _then_.
- **NYSE RTH only** : SPY trades only NYSE hours (9:30-16:00 ET) ; the cash `I:SPX` is similarly RTH-only. Pre-open / after-hours SPX500 cards = "no bars in window" (same behaviour as current state, no regression).
- **Naming friction in audit trail** : data-pool snippets stamped `Polygon ticker SPY` instead of `I:SPX`. Pass-2 LLM may reference "SPY" in its narrative output. Acceptable for now ; if confusing, ship a display-name layer in `services/data_pool.py:_render_polygon_section` that maps SPY → "SPX500 (via SPY proxy)" for narrative purposes only.

### Neutral

- **Massive (rebrand) pricing volatility** : pricing was non-trivial to confirm via web ; the page redirect makes scraping unreliable. Verified via WebSearch secondary sources 2026-05. If Massive bundles indices into Stocks Starter at a future date, revert to `I:SPX` becomes free.

## Decision tree for Eliot

- ✅ **Default = Option 3 SPY proxy** : ship if you want SPX500 cards working immediately at no extra cost.
- ⚠ Option 1 Indices Starter $49/mo : ship if you plan to add cash-SPX level-sensitive features (dealer GEX flip levels, futures basis trade signals) and want pristine data NOW.
- ❌ Option 2 ES futures : avoid (rollover complexity, opaque pricing, redundant with CFTC TFF).
- ❌ Option 4 Drop SPX500 : avoid unless you reconsider whether SPX500 belongs in D1 (cost-benefit revisit of ADR-083 §16-17).

## Next session shipping plan

If Eliot ratifies Option 3 (same session or next) :

1. Branch `claude/round-27-spx500-spy-proxy`.
2. Patch `polygon.py` one-line + comment block.
3. Add unit test + CI guard.
4. Smoke test : SSH Hetzner + `curl /v1/market/intraday?asset=SPX500_USD`.
5. Smoke test : trigger `cli/run_session_card.py --asset SPX500_USD --session new_york --dry-run`.
6. PR.

Estimated 30 minutes end-to-end if smoke tests green first try.
