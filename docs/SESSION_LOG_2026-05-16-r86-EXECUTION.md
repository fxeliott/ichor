# SESSION_LOG 2026-05-16 — r86 EXECUTION

**Round type:** ops triage + 1 repo defect fix + 1 ADR (PRIORITÉ #1 =
RUNBOOK-020). One coherent thread; no unrelated accumulation.

**Branch:** `claude/friendly-fermi-2fff71` · worktree
`D:\Ichor\.claude\worktrees\friendly-fermi-2fff71` · base HEAD `879f7a8`
(r85). main `635a0a9` (r49). PR #138 OPEN. ZERO Anthropic API spend.
Voie D + ADR-017 held. No serving-stack touch (ichor-api / ichor-web2 /
dashboard healthy throughout — verified).

## Objective

Triage RUNBOOK-020 (generation pipeline degraded). Re-verify live (R59),
fix every Claude-safe blocker (reversible), isolate the true Eliot
boundary, surface honestly. Never fabricate/handle a secret.

## Method

2 parallel skeptical sub-agents (A: read-only Hetzner SSH ; B: repo
provenance) → personal source re-verification (citation gate) → then a
**controlled-run-per-layer** empirical loop: apply ONE verified fix →
`systemctl start ichor-briefing@pre_ny` → read the exact next error →
repeat. Every mutation reversible; read-only verification between each;
no `reset-failed`; SSH consolidated (throttle-aware).

## What was found — the 6-defect chain (RUNBOOK-020 was materially wrong)

`ichor-briefing@*` SOPS/tmpfs path had **6 stacked independent defects**;
it never worked in production. Sibling `ichor-session-cards@*` uses the
proven `EnvironmentFile=/etc/ichor/api.env` and starts fine.

1. Script absent → **P1** redeploy from repo `scripts/hetzner/ichor-decrypt-secrets` (RUNBOOK-020's "not in app repo / infra/ansible" was FALSE). sha256 parity verified.
2. Template never sets `SOPS_AGE_KEY_FILE` (`register-cron-briefings.sh:40-50`) vs `ichor-decrypt-secrets:33-34` hard-require → **P2** drop-in.
3. `ExecStartPre` ran as `ichor` (no `+`); age key `root:root 0600` → unreadable → **P3** `ExecStartPre=+` drop-in. **The age key was present & valid all along** (`/etc/sops/age/key.txt`, decrypts exit=0) — RUNBOOK-020/Agent-A "missing key, Eliot must restore" (A-ii) is **VOID** (they checked the sops _default_ path, not the design path). My own r86 first-pass turnkey was wrong here and is self-corrected.
4. `/opt/ichor/infra/secrets/` absent → deployed the SOPS-**encrypted** `cloudflare.env`+`local-passwords.env` (verified ciphertext line-by-line, git-clean, sha256 parity; Claude never touched plaintext or the key).
5. **Repo code bug**: `ichor-decrypt-secrets` SOPS-detection `grep -q '^sops:'` skips dotenv-format SOPS (`sops_version=`, no `sops:` line) → wrote a 0-byte bundle then exit 0 (silent success). Fixed `ichor-decrypt-secrets:57-62` → `grep -qE '^sops:|^sops_version='`; redeployed; empirically `wrote 2 secret bundle(s)` (1080 bytes).
6. **Architectural (open → ADR-100)**: `run_briefing.py` needs `ICHOR_API_*` config from `/etc/ichor/api.env`; the briefing template never loads it (the SOPS bundle carries bare-named infra creds, not `ICHOR_API_*`). `[journal: ValidationError ICHOR_API_CLAUDE_RUNNER_URL required, input_value={}]`.

**Security finding:** `ExecStartPost=shred` runs only on ExecStart
success → every failed briefing leaks the decrypted plaintext bundle on
`/dev/shm` (0600 ichor) until reboot. My controlled-test artefact was
responsibly shredded; latent design bug recorded in ADR-100.

## Applied this round (all reversible, Claude-safe, gated by Eliot's

delegated "decide & do the best, no error" mandate)

- Host (Hetzner, `ichor-briefing@*` only — already-failed units, zero
  serving blast radius): P1 (script `/usr/local/bin/ichor-decrypt-secrets`)
  - P2 (`age-key.conf` drop-in) + P3 (`execstartpre-root.conf` drop-in) +
    Step-A2 (`envfile-optional.conf` drop-in) + deployed encrypted
    `/opt/ichor/infra/secrets/{cloudflare,local-passwords}.env` (0640
    root:root). Each verified via `systemctl cat` + sha256 + controlled run.
    No `reset-failed` (honest broken state preserved).
- Repo (committed): `scripts/hetzner/ichor-decrypt-secrets` detection fix ;
  **ADR-100** (Proposed) ; RUNBOOK-020 r86 + r86-CONTINUED corrections ;
  this SESSION_LOG.

## NOT done (correctly — boundary)

- Cause B (claude-runner 403) — RUNBOOK-018, Eliot CF dashboard + Win11.
  Independent; still blocks even after ADR-100 (briefing would then start
  and hit the same 403 as session-cards).
- The ADR-100 mechanism switch (Option X = use `api.env` like
  session-cards) — RUNBOOK-020:84-86 + ADR-099 §D-4 reserve the
  secrets-at-rest posture decision for Eliot. Reversible implementation
  prepared, NOT applied, pending ratify.
- No secret fabricated/handled; age private key never read/moved.

## Honest state

Cause A is **Claude-resolved up to one clean architecture decision**
(ADR-100). The age-key blocker RUNBOOK-020 raised does not exist.
Remaining Eliot surface, total: **(1) ratify ADR-100 (~2 min) ;
(2) Cause B RUNBOOK-018 (~9 min CF)**. Until both: pré-Londres/pré-NY
serve stale (not fresh) analysis; no data loss; serving stack healthy.
RUNBOOK-020's original "DOWN since May 15, missing key, restore from
infra/ansible" was substantially wrong on the _how_ — corrected
in-place with the evolution trail preserved (the "tu es sûr = audit
harder" doctrine, applied to my own first pass too).

## Next

**Default sans pivot:** on Eliot's ADR-100 ratify (Option X recommended),
apply the reversible `api.env` drop-in + cleanup vestigial r86 drop-ins,
then Cause B via RUNBOOK-018, then Step C verify a fresh card. THEN
ADR-099 Tier 2.3 (R59 first: event-priced-vs-surprise gauge /
confluence-reweight / `_section_gbp_specific`). Session is deep (one long
triage) → /clear after this checkpoint is reasonable; this log + ADR-100

- pickup v26 are self-sufficient.
