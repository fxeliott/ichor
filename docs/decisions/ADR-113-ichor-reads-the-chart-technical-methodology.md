# ADR-113 — Ichor reads the chart: technical-analysis methodology module (S05 / Chantier E)

- **Status**: Accepted (2026-06-12)
- **Decider**: Eliot (owner) — GAP-4 decision recorded verbatim 2026-06-10
  (PLAN_DIRECTEUR.md §9 decision 1: "ichor lit et analyse complètement le
  chart de A à Z ultra ultra poussé"), actioned here after the §9.2 materials
  were delivered (2026-06-12: 4 technical transcripts + fundamentals
  transcript + Ichor-beta meeting hub).
- **Context session**: Session 05 re-fire (METHODO-TECHNIQUE) → Chantier E
  slice-1 (PLAN_DIRECTEUR.md §5 mapping :288-294).

## Context

Since ADR-017/ADR-083, the as-built doctrine was "**Eliot does the technical
analysis** on TradingView; Ichor covers the other ~90%" (ADR-083 D3,
`data_pool.py:846-849`, `key_levels/__init__.py:5-7`,
`liquidity_proxy.py:202-203/244-245`, brain validator messages, ~13 spots).
The Session 04/05/06 spec files emphatically reversed this ("ICHOR FAIT TOUT
… il n'y a plus de découpage entre toi et moi sur la technique") — GAP-4.
The owner arbitrated on 2026-06-10: **Option A, reinforced**. Chantier E
remained gated on the §9.2 materials, which the owner supplied on 2026-06-12
(`transcript session ichor/` + hub at `D:\Projects\reunion-trading` and
`D:\Projects\ichor beta`).

What survives unchanged, contractual (the spec itself re-affirms it): **no
BUY/SELL signals, no TP/SL, no entry orders, ever** (ADR-017, ADR-081 CI
guard). What changes is _who reads the chart_, not whether Ichor emits orders.
Execution remains Eliot, on TradingView, with his own risk management.

## Decision

1. **Ichor performs the full technical read** of the 5 priority assets,
   applying the owner's codified methodology. The single source of truth for
   that methodology is **`docs/METHODOLOGIE_TECHNIQUE_ELIOT.md`** (new,
   source-stamped against the raw transcripts, EXPLICITE/INFÉRÉE confidence
   tags, open questions listed as `[TBD owner]`). No implementation may encode
   a technical rule that is not in that document.
2. **Server-side read, Voie-D clean**: the production read computes from the
   OHLCV bars already in TimescaleDB (`polygon_intraday` 1-min aggregated in
   Python, `market_data` daily) — deterministic, testable, zero new external
   dependency. New pure-core service `services/technical_analysis.py` +
   `_section_technical_methodology` in `data_pool` (Pass-2), following the
   london_session SSOT pattern (pure compute + thin async wrapper) and the
   honest-absence/DegradedInput doctrine.
3. **TradingView (`tradingview-cdp`) is the interactive witness & indicator
   layer, NOT a prod dependency**: it runs on the owner's Win11 machine,
   breaks on TradingView updates (~1-2 months), and its README disclaims
   automated non-display collection under TradingView ToS. Therefore:
   on-demand interactive use (owner-validated chart reads, Pine deployment,
   replay study) — **no periodic automated scraping service**. Revisit only
   via a dedicated ADR if a licensed data path appears.
4. **Pine indicators are built as Ichor's own reading aids** (spec 5ter-bis:
   aids, not end-user deliverables), versioned in-repo under `docs/pine/`,
   compiled/witnessed through `tradingview-cdp` (`pine_check` works in Guest
   mode).
5. **Fusion integration is staged**: slice-1 ships `build_context()` (the
   data_pool section feeding Pass-2). The technical `DimensionVote` (sign
   allowed; no-BUY/SELL boundary in the type) plugs in when Chantier C
   slice-1 lands its contract — `conviction_fusion` stays untouched
   (CI-pinned, additive-only).
6. **Doctrine reconciliation**: ADR-083 D3's interpretation note ("Eliot does
   that on TradingView") is **superseded for the reading**, kept for the
   execution. The ~13 as-built doctrine spots get reconciled progressively;
   `key_levels` keeps its non-technical scope (technical levels live in the
   new module — separate `kind`, no mixing). Validator messages stating "the
   trader applies his/her own technical entry/exit on TradingView" remain
   TRUE (execution stays human) and are not weakened.
7. **Scam-vigilance filter** (spec 5ter-bis): the module encodes only what the
   transcripts/hub establish; rendered output uses the owner's vocabulary
   (French, plus the tolerated exceptions listed in METHODOLOGIE §0/§11 —
   e.g. « sweep »); BOS/CHoCH/FVG-style SMC jargon stays excluded; thresholds
   not given by the owner are marked provisional in code and listed in
   METHODOLOGIE §13.

## Alternatives rejected

- **Option B — keep "Eliot does TA"**: contradicts the owner's explicit,
  recorded decision and the spec (×3).
- **TradingView scraping as the primary prod data path**: structurally
  fragile (internal APIs break ~monthly), ToS-adverse, single-machine
  dependency (Win11 GUI session) — violates the permanence invariant.
- **Encoding a full SMC/ICT framework from training knowledge**: violates the
  zero-invention rule; only the owner's methodology is in scope.

## Consequences

- New: `docs/METHODOLOGIE_TECHNIQUE_ELIOT.md` (SSOT) ·
  `services/technical_analysis.py` · `_section_technical_methodology` ·
  `docs/pine/ichor_lecture_technique.pine` · tests (pure core synthetic bars,
  section monkeypatch, ADR-017 token filter on rendered prose).
- The data_pool prose slot reserved by `liquidity_proxy.py:244-245` ("pure
  price-action liquidity zones … are the technical reading (Session 05)") is
  now being filled.
- Known data caveats carried explicitly: SPX500=SPY proxy & DXY=UUP proxy
  (ADR-089) — technical levels computed on proxies are labeled as such; FX has
  no consolidated volume (honest-N/A); only 1-min and daily granularities
  exist (H1/H4 aggregated in Python).
- 9 open methodology questions are parked as `[TBD owner]`
  (METHODOLOGIE §13) — notably the truncated origin-hierarchy levels 2/3 and
  the RR transcription ambiguity. The module must not guess them.

## References

- PLAN_DIRECTEUR.md §4bis (S05 technical module), §5 (Chantier E), §9
  (decisions 1-3) · ADR-017 · ADR-083 D3 · ADR-089 · blueprint Chantier C
  slice-1 (memory `ichor_chantier_c_slice1_blueprint.md`).
- §9.2 materials: `D:\Ichor\transcript session ichor\*` + hub
  `D:\Projects\reunion-trading` + `D:\Projects\ichor beta\IchorBeta`.
