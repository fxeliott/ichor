# SESSION_LOG 2026-05-16 — Round 75 (ADR-099 Tier 1.1: Volume panel)

> Round type: **feature + deploy-script root-cause fix**. Branch
> `claude/friendly-fermi-2fff71`. ZERO Anthropic API spend. Voie D + ADR-017 held.
> Trigger: Eliot "continue" → ADR-099 D-3 Tier 1.1 (volume = an explicit
> Eliot vision layer, previously ABSENT from the dashboard).

## What r75 shipped

The **Volume** layer on `/briefing/[asset]` (was layer 5 of 8, ABSENT per
the r72 audit; backend was already serveable — pure frontend).

- `lib/api.ts`: `getIntradayBars(asset, hours=72, limit=10000)` — **reuses**
  the existing `IntradayBarOut` type (anti-doublon, not redefined).
- `components/briefing/VolumePanel.tsx` (new, house style from
  `CorrelationsStrip`): hand-rolled **SSR-safe SVG** microchart (no
  charting dep, fixed viewBox, RSC-clean — per r72 web-research), volume
  bars from a true 0 baseline (no truncated axis) tinted up/down, close-
  price polyline overlay, tabular-nums stat row.
- `app/briefing/[asset]/page.tsx`: fetch in the SSR `Promise.all`, slice
  the **last 90 bars server-side** (endpoint returns the whole ≤72h window
  ascending, verified R59 — only 90 ship to the client, not ~3.7k), new
  `<section>` placed between News and Correlations.

### R59 ground truth that shaped the design (verified, not guessed)

- Endpoint params: `hours ∈ [1,72]`, `limit ∈ [10,10000]`; returns the
  full window **ascending**; `limit` truncates from the OLDEST end → must
  fetch wide + tail-slice to reach the most recent bar.
- Today is **Saturday 2026-05-16** (server clock) — markets closed; last
  EUR_USD bar = Fri 20:59 UTC. The panel renders a **"Marché fermé ·
  dernière <jour>"** badge (ADR-093 degraded-explicit) — exactly Eliot's
  explicit weekend/holiday-awareness requirement, verified live.
- EUR_USD volume 6–345 (avg 149), 0 nulls → labelled honestly as a
  **Polygon tick/aggregate proxy**; the panel states "le volume réel FX
  n'existe pas (marché décentralisé)" (web-research + no-fake-precision).

### Deploy-script root-cause fix (caught by R59 content-verify)

First redeploy returned HTTP 200 but the Volume panel was **absent from
the rendered HTML** — `redeploy-web2.sh` Step 4 used `systemctl enable
--now` which **no-ops on an already-active service**, so the old r73
build kept being served. Also the unconditional `restart ichor-web2-
tunnel` rotated the quick-tunnel URL every redeploy (+ a journal-grep
race → false 530 FATAL). Fixed at the root: Step 4 now `restart`s
`ichor-web2` (loads new build) and starts `ichor-web2-tunnel` **only if
inactive** (URL stable across app redeploys). Re-deployed `--skip-build`;
verified.

## Empirical witnesses (R59 — public path, the real Eliot experience)

- `https://latino-superintendent-restoration-dealtime.trycloudflare.com/briefing/EUR_USD`
  = **200**, 164 360 B (was ~140 KB → +Volume).
- Markers present: `volume-heading`, `Activité (volume proxy)`, `Agrégat
tick Polygon`, `Marché fermé · dernière` (weekend badge correct), `le
volume réel FX n'existe pas`, stat labels Dernière/Moyenne/Max/Fenêtre,
  1 `<svg>` microchart.
- Cockpit `/briefing` still 200. `tsc --noEmit` + `eslint --max-warnings 0`
  both clean on the 3 changed files.
- **ADR-017 intact**: `BUY/SELL` appears only in (a) the VolumePanel
  boundary docstring and (b) the pre-existing page footer disclaimer
  `No BUY/SELL signals (ADR-017 boundary)` — the sanctioned exceptions
  per the CLAUDE.md invariant. No functional leak (Grep-verified on source).

## Caveat (unchanged from r73, RUNBOOK-019 Tier 0.2)

Quick-tunnel URL is now **stable across app redeploys** (the fix) but
still rotates if `ichor-web2-tunnel` itself restarts (reboot/crash).
Current stable URL above. Permanent hostname = named CF tunnel (Eliot-gated).

## Next stage (on Eliot "continue")

ADR-099 **Tier 1.2 — Géopolitique panel** (`_section_geopolitics:3772`
exists backend: AI-GPR + GDELT; surface it). Then T1.3 holidays via
`pandas_market_calendars`, T1.4 sentiment + institutional positioning,
T1.5 correlations unconditional.

## Checkpoint

Commit: api.ts + VolumePanel.tsx + page.tsx + redeploy-web2.sh + this
SESSION_LOG on `claude/friendly-fermi-2fff71`. Memory pickup updated separately.
