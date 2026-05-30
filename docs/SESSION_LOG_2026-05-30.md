# SESSION LOG — 2026-05-30 (content-correctness → STIR/FedWatch → real-time coverage)

Branch `claude/amazing-heyrovsky-80df1e`. 11 commits `1c10f9f → 5675ffc`, all
pushed (PR #159), 124 ahead `origin/main`. Voie D held (zero `import anthropic`),
ADR-017 held (no BUY/SELL — every new narrative is descriptive + test-guarded),
ADR-023 held (Couche-2 Haiku — upgrade flagged, not done). ZERO Anthropic API spend.

## What shipped (commit → what → live verification)

### Content-correctness block (the "juste + cohérent" gain)

- **`1c10f9f` disclosure 4.7→4.8** — `config.ai_provider_tag` + `middleware/ai_watermark.DEFAULT_PROVIDER_TAG` (W90 SSOT pair) + `well_known` + 13 web2 refs. LIVE: `/.well-known/ai-content` provider=`anthropic-claude-opus-4-8`, web2 renders Opus 4.8.
- **`9787739` coherence gate + derived thesis** — NEW `services/card_coherence.py`. `reconcile_coherence()` (WRITE, wired `cli/run_session_card.py` before persist) demotes a directional bias to neutral when the 7-bucket scenario mass contradicts it OR (US equity, cash-closed overnight) the lean is weak; shaves conviction on a weak edge. Demote-only (never promotes/flips). `synthesize_thesis()` (READ, `schemas.from_orm_row`) builds the 1-3 sentence verdict + surfaces scenario/driver tension without flipping the badge. LIVE: EUR `coherence_adjusted long→neutral reason=scenario_mass_short_vs_bias_long`; thesis rendered on /briefing.
- **`ccb91b0` DXY disambiguation** — relabel FRED `DTWEXBGS` "DXY (broad)" → "USD broad index (DTWEXBGS)" + a prompt note so the LLM stops conflating the ~119 broad index with the ~99-105 ICE DXY. LIVE: new EUR card invalidations cite `FRED_DTWEXBGS 119.7/120.5`, not ICE 98.5/99.3.
- SPX/NAS consistency = the same coherence gate's `equity_overnight_clamp` (extended to `{pre_londres, ny_close}` in `e882321`). LIVE: SPX + NAS both neutral on the cash-closed overnight.
- de-dup/stale: ASSESSED not-a-bug (Polymarket data fresh, UK10Y honestly dated, macro blocks shared-by-design). No fabricated fix.

### STIR / FedWatch vertical

- **`e418622` /v1/stir + `769cbaf` <StirPanel>** — NEW `services/stir.py` `assess_stir()`: reconstructs the CME ZQ-futures implied EFFR path + cumulative bp vs front + ~5-session repricing delta (the anticipation signal), from already-persisted `fred_observations` (no migration). `routers/stir.py` mirrors yield_curve. `<StirPanel>` in a new "Taux & Fed" briefing section. LIVE: curl 200 + panel screenshot.
- **`e882321` post-review hardening (4 findings from a code-reviewer subagent + own audit)** — equity clamp ny_close→`{pre_londres,ny_close}` (SPX live long→neutral); STIR bar dynamic scale (no clip); STIR note/badge half-up rounding aligned (note == badge); `_derive_thesis` exception log debug→warning.
- **`413ab23` key-level asset-relevance filter (web2)** — drop another asset's asset-specific dealer-gamma (SPX/NAS) from FX cards; keep macro (USD/USDHKD). LIVE: EUR card Dealer-GEX absent, SPX present.
- **`c6dced6` per-FOMC-meeting FedWatch probabilities** — `StirMeeting` + `_compute_meetings` + `_move_probabilities` in `stir.py`. Day-weighted blend for mid-month meetings (Jun17/Sep16/Dec9), next-clean-month anchor for late-month (Jul29→Aug, Oct28→Nov, avoids ÷3 instability), chained, P=|Δ|/25. Methodology + 2026 FOMC calendar WEB-VERIFIED (cmegroup.com + federalreserve.gov). LIVE: `/v1/stir` meetings + stacked-bar panel; telescoping cross-check ΣΔ 14.3 vs cumulative 12.5bp (gap explained = front ZQ=F vs K26 explicit contract).

### Real-time coverage (full Ichor vision §6)

- **`cb1c0d6` real-time published-result reactivity** — `_section_recent_actuals` in `data_pool.py` wires the existing `recent_actuals` service (published actual vs consensus + r141 surprise classifier) into the LLM prompt. LIVE: regen EUR → `recent_actuals` in sections list, real data (Unemployment Claims 215K vs 211K +1.9%).
- **`5675ffc` London-morning session read (§6.2 CAPITAL)** — NEW pure `services/london_session.py`: slices the London-morning window (08:00-12:00 London local → UTC via ZoneInfo, DST-correct) from 1-min `polygon_intraday` bars → O/H/L/C + range + direction (reuses origin-zone `_classify_direction`, no doublon) + range-vs-prior-5-windows. `_section_london_session` appended after recent_actuals. LIVE: ground-truth verified vs Friday EUR 07-11h UTC (240 bars, open 1.1653→close 1.16427, −10pip, baissière); `london_session` in regen sections list.

## Tests / quality gates

- Full apps/api suite **2944 passed / 34 skipped / 0 fail** (on `cb1c0d6`).
- +271 passed over the whole session-touched surface (incl. `london_session`, `card_coherence`, `stir`, `recent_actuals`, data_pool variants, invariants W90, watermark, well_known).
- New tests: `test_card_coherence.py` (18), `test_stir.py` (13), `test_data_pool_recent_actuals.py` (3), `test_london_session.py` (6, incl. a DST summer/winter window check).
- tsc + eslint clean on web2; pre-commit (gitleaks/ruff/prettier/ADR-081 invariants) green per commit.

## Flagged decisions (owner to decide)

- **§10 Opus 4.8 everywhere**: briefings ALREADY on Opus 4.8 ✓. Couche-2 NLP on Haiku (`model="haiku"` in `packages/agents/src/ichor_agents/agents/*.py`). Switching to Opus risks 24/7 durability (single Win11 runner subprocess contention + quota + latency) — a genuine §10-vs-§5 trade-off. Recommend: test-behind-flag a few days vs keep Haiku for durability.

## Remaining gaps (ranked) + DOCUMENTATION DEBT

1. **Consensus-range source** — `economic_events.forecast_min/max = 0/107` → the surprise RANGE classifier (above/below_range) can't fire (point-surprise magnitude works). Also the cause of the GDP "0.40284" FF-feed value anomaly. Needs a free consensus source (FXStreet/Investing) in the calendar collector. Highest leverage.
2. **Frontend `<LondonSessionPanel>`** — backend `/v1`-less section is in the prompt; a visual panel is the natural complement.
3. **§10 Couche-2 Opus decision** (above).
4. ECB/BoE implied paths (needs a free OIS source); weekend-card relevance.
5. **DOC-DEBT (this session)**: formal ADRs not written for the 5 architectural additions (coherence gate, STIR engine, FedWatch per-meeting, real-time reactivity, London read). Rationale + design ARE recorded here + in `auto_session_resume.md`; formal `docs/decisions/ADR-108..` to be authored next session (project convention: one decision = one ADR).

## Keys exposed in logs (EIA + FRED) → rotate (Eliot manual).
