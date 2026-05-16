# SESSION_LOG 2026-05-16 — Round 74 (ADR-099 Tier 0.2: externally-gated prep)

> Round type: **prepare-to-one-command** (no prod mutation). Branch
> `claude/friendly-fermi-2fff71`. ZERO Anthropic API spend. Voie D + ADR-017 held.
> Trigger: Eliot "continue" → ADR-099 D-3 Tier 0.2.

## What r74 did

ADR-099 §D-4 boundary: everything safely autonomous is done; the irreversible/
shared-state gestures are now one-click for Eliot.

1. **Created PR #138** — `claude/friendly-fermi-2fff71` → `main`, 37 commits
   (r50→r73). Empirically clean: `main` is an ancestor (0 behind / 37 ahead),
   **fast-forward, no conflicts possible**. Description carries the full
   r50→r73 summary + honest audit disclosure (scp-deploy means merge ≠ deploy).
   `gh` auth = keyring (fxeliott), `repo`+`workflow` scopes — autonomous-OK,
   precedent r46 PR #134. Reversible (closeable; prod unaffected).
   → https://github.com/fxeliott/ichor/pull/138
2. **Authored RUNBOOK-019** — exact step-by-step (RUNBOOK-018 paste-and-act
   pattern, beginner-grade) for the 5 Eliot-gated items:
   - Item 1: merge PR #138 (prod unaffected by construction).
   - Item 2: **stable `/briefing` URL** — recommended a _named_ CF tunnel on
     `fxmilyapp.com` (reuses existing infra, stays private, closes the r73
     quick-tunnel-rotation caveat). Eliot does the CF dashboard; Claude wires
     Hetzner from a pasted token. CF Pages documented + rejected (public
     `*.pages.dev` + SSR incompatible).
   - Item 3: `ICHOR_CI_FRED_API_KEY` GH secret (`gh secret set`, key never
     echoed).
   - Item 4: rotate journald-leaked FRED key + CF token (rotation > scrub;
     Claude updates Hetzner env/SOPS from pasted new values).
   - Item 5: revoke PAT `ichor-session-2026-05-15-claude-autonomy`.

## Why no autonomous secret/rotation

Per ADR-099 §D-4: Claude must not fabricate secret values, read/echo live
credentials, or merge to `main` unilaterally. Creating the PR (≠ merging) and
writing the runbook IS the "prepare to one-command readiness" deliverable.
Security: secrets stay in password manager + Hetzner `api.env` 0640 + GH
encrypted — never in chat/repo.

## Next stage (on Eliot "continue")

ADR-099 **Tier 1** — close the explicit vision-coverage gaps, highest
value/effort first: **T1.1 volume panel** (backend already serveable via
`/v1/market/intraday/{asset}` + `polygon_intraday` 140k rows live — pure
frontend SSR SVG microchart), then T1.2 géopolitique panel, T1.3 holidays via
`pandas_market_calendars`, T1.4 sentiment + institutional positioning, T1.5
correlations unconditional. Protocol per round: announce → R59 inspect →
build → TS+lint → deploy-if-backend → real-data verify → SESSION_LOG →
single-step commit (re-add after prettier) → push.

## Checkpoint

Commit: RUNBOOK-019 + this SESSION_LOG on `claude/friendly-fermi-2fff71`.
PR #138 open (Eliot merges). Memory pickup updated separately.
