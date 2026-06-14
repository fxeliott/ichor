# SESSION LOG — 2026-06-14 · S06 Chantier C · volume DimensionVote (producer + wiring), shipped + deployed

> Model: Opus 4.8 (interactive). Re-fire #12 of the Session 06 prompt
> ("focus session 6, traite tout, merge + deploy toi-même, max autonomie").
> Doctrine applied (CLAUDE.md ">2x re-fire = build the documented NEXT, don't
> re-deliberate"): took the documented NEXT dimension producer (volume, after COT)
> and shipped it end-to-end, mirroring the COT C-3b pattern exactly.

## What shipped (2 PRs, squash-merged to main, deployed Hetzner, runtime-witnessed)

### PR #251 — volume DimensionVote **producer** (`main` d5b172a)

NEW `services/volume_vote.py` (pure, I/O-free, stdlib + `dimension_vote` only) +
`tests/test_volume_vote.py` (38 tests). Maps `microstructure.RelativeVolumeReading`
(the relative-volume / participation read `data_pool._section_volume_rvol` already
feeds the LLM) into one **non-directional** `DimensionVote` (`provenance="volume"`,
`directional=False` → contributes only `uncertainty_credit`, never a tilt — ADR-017
cannot be violated by construction). Strictly additive (new files only) → fuser (179)

- card (32) golden harnesses byte-identical.

Doctrine web-verified 2026-06-14 (fresh `researcher`): StockCharts RVOL (≥1.25
"elevated", 3-5× "strong interest", >4× true "spike") · Dow-theory volume-confirms-
trend (non-directional) · below-average = no confirmation, not anti-confirmation ·
FX has no consolidated venue volume. Thresholds doubly-anchored: baseline 1.25×
(in-repo `_volume_bucket` "elevated" cut), full strength 3.0× (web "strong interest"
band — deliberately high, like COT's 10%-OI bar, so a quad-witching ~1.45× only scores
~0.11). Deferred (documented): calendar-mechanical mask (quad-witching/rebalancing/
holiday/roll) + exhaustion tail.

### PR #252 — volume DimensionVote **wiring** (`main` 7911647)

Wires the producer into the live verdict path behind `VOLUME_DIMENSION_VOTE_FLAG`,
mirror of the COT C-3b wiring:

- `data_pool._volume_vote_from_reading` (pure, no-DB) + async
  `build_volume_vote_for_asset` (FX/off-whitelist abstain with ZERO DB I/O).
- `run_session_card` write-side: freeze the **enabled** DimensionVotes (COT + volume),
  EACH gated by its own flag, into one combined `dimension_votes` snapshot.
- `session_verdict_builder` read-side: fold the frozen votes when **ANY** dimension
  flag is on (`cot_on or volume_on`).

Both flags OFF (default, fail-closed) → write no-op, read `votes=()` → fuser
byte-identical (golden harnesses re-pass). For the LIVE prod config (COT on, volume
off) the change reduces to the previous behaviour exactly (`_votes=[cot_vote]` ==
`votes_to_snapshot([cot_vote])`; read `T or F` == `T`).

## Verification (each slice: full suite + ruff + mypy + fresh adversarial verifier)

- Full api suite **3672 passed / 36 skip** (was 3664 → +8 wiring tests, ZERO
  regression); ruff clean; mypy no NEW errors (warn-only baseline, ADR-028); all
  pre-commit hooks Passed (gitleaks / ADR-081 / detect-private-key).
- Two fresh `verifier` adversarial passes (producer, wiring) → **DÉCISION OK** each.
  Producer: 5/5 mutants caught. Wiring: flag-OFF byte-identity simulated, COT-only
  path preserved, no partial-corruption on capture failure, CI guards green.
- **Prod runtime witness** (ssh, read-only): `ichor-api` active, `/healthz` 200
  (db+redis connected); prod venv imports `volume_vote` + the wiring + executes a
  live vote (`provenance=volume directional=False strength=1.0 uncertainty_credit=1.0`
  on a 3× read); clean boot, zero errors in journal since restart.

## Honest framing (zero hallucination)

This completes the volume dimension end-to-end but is **dormant** (flag OFF) — no
behaviour change until an owner enables it. Volume is non-directional (it grounds
conviction marginally via participation, never sets direction) and there remains **no
proven directional edge** (ADR-116/119 witness). A _calibrated_ activation belongs
with **C-5** (wire `select_calibrator_oos` into `_derive_direction_and_conviction`):
the witness showed raw conviction is over-confident, so activating dimensions WITHOUT
the OOS calibrator would amplify, not fix, the overconfidence. Earned conviction, not
manufactured.

## Current-state findings (verified this session — NOT caused by this work)

1. **`cot_dimension_vote_enabled = t` in prod DB** — COT is LIVE (no longer dormant as
   earlier logs said). The volume change is byte-identical for this config (verified).
2. **Push-triggered `Deploy to Hetzner` (full `site.yml`) FAILS on every push** —
   Ansible `observability` role can't create the `ichor-obs` Docker network: _"all
   predefined address pools have been fully subnetted"_ (grafana/loki/prometheus
   `Exited` ~5 weeks). The API actually deploys only via `workflow_dispatch -f tags=api`
   (the green path used here). Fix candidates: `docker network prune` on the host, or
   add an address pool in `/etc/docker/daemon.json` (`default-address-pools`). → RUNBOOK.
3. **`claude_runner_reachable: null`** (healthz) + **no fresh cards since 2026-06-12**
   (latest `session_card_audit`) — the Win11 card-generation runner is unreachable, so
   the COT live write-path hasn't produced new `dimension_votes` to witness. Pre-
   existing (cf. RUNBOOK-014).

## Known minor (documented, same as merged COT wiring)

The read-gate `cot_on or volume_on` is exercised only flag-OFF by the golden harnesses
(a mutation `or`→`and` ships green); a both-flags live integration test on
`build_session_verdict` (AsyncMock session + monkeypatched `is_enabled` + a card with
`dimension_votes`) is the follow-up — the same gap exists for the merged COT wiring.

## NEXT (fresh session)

- **C-3 next dimensions** (same pattern, one at a time, golden-diff each): rates /
  yield-curve (directional FX, all FRED tenors collected) → then geopolitics/GPR.
- **C-5** honest-display calibration wiring (owner-gated product call) — the real lever
  for a _legitimate_ high conviction.
- Add the live both-flags gate integration test (close the documented minor).
- Infra: unblock the push deploy (observability Docker network) + the Win11 runner
  (no fresh cards since 06-12).

main = 7911647. ssh ichor-hetzner = root@prod; DB read-only `sudo -u postgres psql -d
ichor`; deploy = `gh workflow run deploy.yml --ref main -f tags=api`.
