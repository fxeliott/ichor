# ADR-100: `ichor-briefing@` secrets provisioning — align with the proven `api.env` mechanism

- **Status**: Proposed (round-86, 2026-05-16). Authored from the r86 RUNBOOK-020 empirical triage (6 stacked defects peeled with a controlled-run-per-layer methodology). The mechanism choice changes the briefing secrets-at-rest posture on the host → RUNBOOK-020:84-86 + [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md) §D-4 autonomy boundary explicitly reserve this for **Eliot ratification**. Claude has fixed every Claude-safe defect (reversible) and prepared the reversible implementation for both options; neither mechanism switch is applied pending ratify.
- **Date**: 2026-05-16
- **Decider**: Claude r86 (proposal, empirically grounded) ; **Eliot (ratify — secrets-at-rest posture)**
- **Relates**: [RUNBOOK-020](../runbooks/RUNBOOK-020-generation-pipeline-down-decrypt-secrets-cf403.md) (this ADR closes its §"Step A" decision) ; [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md) §Tier-3 #1 ; RUNBOOK-018 (Cause B, independent)
- **Supersedes**: none

---

## Context

The r85 "tu es sûr" audit found the generation pipeline degraded (the two
core windows pré-Londres/pré-NY serve stale analysis). RUNBOOK-020
attributed `ichor-briefing@*` failure to "missing decrypt script + missing
age key, restore from infra/ansible". The r86 triage **disproved most of
that** and peeled the real chain by applying one verified fix at a time and
re-running a single controlled `ichor-briefing@pre_ny` after each.

### The `ichor-briefing@*` SOPS/tmpfs path had 6 stacked independent defects

| #   | Defect                                                                                                                                                                                                                                                                                                                                                                                     | Evidence                                                                                                                                                                                                                                                    | r86 disposition                                                                                                                                                                                                                                                                                                                                                  |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `/usr/local/bin/ichor-decrypt-secrets` absent                                                                                                                                                                                                                                                                                                                                              | `[journal: Failed to spawn 'start-pre' task: No such file]` ; script **is in repo** `scripts/hetzner/ichor-decrypt-secrets` (RUNBOOK-020's "not in app repo / infra/ansible" was wrong)                                                                     | **FIXED P1** — redeployed from repo (sha256 parity verified). Claude-safe (non-secret git artefact, reversible)                                                                                                                                                                                                                                                  |
| 2   | Template never sets `SOPS_AGE_KEY_FILE`; script hard-requires it                                                                                                                                                                                                                                                                                                                           | `register-cron-briefings.sh:40-50` (no `Environment=`) vs `ichor-decrypt-secrets:33-34` (`exit 2`) ; `[journal: FATAL: SOPS_AGE_KEY_FILE not set]` post-P1                                                                                                  | **FIXED P2** — drop-in `Environment=SOPS_AGE_KEY_FILE=/etc/sops/age/key.txt`. Reversible, path-only                                                                                                                                                                                                                                                              |
| 3   | `ExecStartPre` runs as `ichor` (no `+`); age key is `root:root 0600` → unreadable                                                                                                                                                                                                                                                                                                          | `[ls -l /etc/sops/age/key.txt = -rw------- 1 root root]` ; unit `User=ichor` ; `[journal: FATAL: SOPS_AGE_KEY_FILE not readable]` ; script designed for root (`ichor-decrypt-secrets:77` chowns to ichor)                                                   | **FIXED P3** — drop-in `ExecStartPre=+...` (run privileged setup as root). Reversible. **NB: the age key was present & valid all along — RUNBOOK-020's "Eliot must restore the age key" (A-ii) is VOID** (the original audit checked the sops _default_ path `/root/.config/sops/age/keys.txt`, not the design path `/etc/sops/age/key.txt` per `.sops.yaml:26`) |
| 4   | `/opt/ichor/infra/secrets/` absent on host                                                                                                                                                                                                                                                                                                                                                 | `[journal: FATAL: secrets dir not found: /opt/ichor/infra/secrets]`                                                                                                                                                                                         | **FIXED** — deployed the SOPS-**encrypted** `cloudflare.env`+`local-passwords.env` (verified ciphertext line-by-line, `git status` clean, sha256 parity ; Claude never handled plaintext or the key). Reversible                                                                                                                                                 |
| 5   | Script SOPS-detection `grep -q '^sops:'` incompatible with **dotenv-format** SOPS                                                                                                                                                                                                                                                                                                          | `[grep -c '^sops:' = 0 ; '^sops_version=' = 1]` ; `[journal: skip cloudflare.env (not SOPS-encrypted) … wrote 0 secret bundle(s)]` — wrote a 0-byte bundle then **exit 0** (silent success, the worst kind)                                                 | **FIXED** — repo code fix `ichor-decrypt-secrets:57-62` → `grep -qE '^sops:\|^sops_version='`, redeployed ; empirically `[journal: decrypt cloudflare.env … wrote 2 secret bundle(s)]`, bundle 1080 bytes ; host key decrypts (`[sops --decrypt exit=0, 11 lines]`)                                                                                              |
| 6   | **Architectural (this ADR's subject):** even with 1-5 fixed and the bundle correctly decrypted, `run_briefing.py` requires the `ICHOR_API_*`-prefixed app config (`ICHOR_API_CLAUDE_RUNNER_URL` …) which lives in `/etc/ichor/api.env`, **not** in the SOPS bundle (bare-named infra creds `CLAUDE_RUNNER_URL`/`R2_*`). The briefing template has no `EnvironmentFile=/etc/ichor/api.env`. | `[journal: ValidationError ICHOR_API_CLAUDE_RUNNER_URL is required in production, input_value={}]` ; `[grep -c '^ICHOR_API_CLAUDE_RUNNER_URL=' /etc/ichor/api.env = 1]` ; `[systemctl cat ichor-session-cards@pre_ny → EnvironmentFile=/etc/ichor/api.env]` | **OPEN — this ADR decides it**                                                                                                                                                                                                                                                                                                                                   |

Six independent defects on one path ⇒ the `ichor-briefing@*` SOPS/tmpfs
mechanism **never worked in production**. The sibling `ichor-session-cards@*`
units use the plain `EnvironmentFile=/etc/ichor/api.env` (0640 `ichor:ichor`,
exists since 2026-05-12) — identical to `ichor-api` — and **start fine**;
their only failure is Cause B (claude-runner 403, independent, Eliot-gated,
RUNBOOK-018).

### Security finding (reinforces the decision)

`ExecStartPost=/usr/bin/shred -u /dev/shm/ichor-secrets.env` runs **only on
ExecStart success** (systemd semantics). Every _failed_ briefing therefore
leaves the decrypted plaintext bundle on `/dev/shm` (`0600 ichor`, tmpfs,
until reboot). `[ls -l /dev/shm/ichor-secrets.env = 1080 bytes after a
failed run]`. The r86 controlled test's artefact was responsibly shredded;
the latent design bug remains for any real failed run on the SOPS path.

## Decision

**Recommended — Option X: switch `ichor-briefing@.service` to
`EnvironmentFile=/etc/ichor/api.env`** (the exact mechanism
`ichor-session-cards@*` + `ichor-api` already use in production), and
**deprecate the SOPS/tmpfs decrypt `ExecStartPre` for briefings**.

Rationale:

- `/etc/ichor/api.env` is **already the production secrets-at-rest posture**
  for the rest of the stack (session-cards + api). Option X is _posture
  alignment / consistency_, **not a new exposure** — this materially
  narrows the RUNBOOK-020:84-86 "changes the posture, Eliot decides"
  concern (the posture is unchanged for the host as a whole; only the
  briefing units join the existing norm).
- Removes all 6 defects **and** the plaintext-leak-on-failure surface in
  one reversible 1-file systemd drop-in.
- `marche exactement` parity: briefing then behaves exactly like the
  proven session-cards path.

**Option Y (fallback, not recommended as default): keep the SOPS path.**
Defects 1-5 are already fixed r86; Y additionally needs (a) an _additive_
`EnvironmentFile=-/etc/ichor/api.env` so the app config loads, (b) moving
the `shred` to `ExecStopPost=` (runs regardless of outcome) to close the
tmpfs-leak. Keep Y only if Eliot specifically wants the briefing infra
creds SOPS-encrypted-at-rest _in addition to_ api.env. More surface, more
moving parts; the SOPS bundle then duplicates creds already in api.env.

This is the posture/architecture decision RUNBOOK-020:84-86 and ADR-099
§D-4 reserve for Eliot. The reversible implementation for **either** option
is prepared (a single `…/ichor-briefing@.service.d/*.conf` drop-in);
**not applied pending Eliot ratify**.

## Consequences

- **If X ratified**: apply the `EnvironmentFile=/etc/ichor/api.env` drop-in
  (+ remove the now-vestigial r86 drop-ins `age-key.conf` /
  `execstartpre-root.conf` / `envfile-optional.conf`, and the unused
  `/usr/local/bin/ichor-decrypt-secrets` + `/opt/ichor/infra/secrets/`).
  All reversible. The r86 script-detection fix stays committed (correctness;
  harmless if the script is unused).
- **Cause B is independent and still blocks after X.** With X, the briefing
  units will _start_ (config loads) and then hit the same claude-runner 403
  as session-cards. **Full pre-Londres/pre-NY recovery = ADR-100 X (or Y) +
  RUNBOOK-018 Cause B (Eliot ~9 min CF dashboard).** ADR-100 alone does not
  restore fresh generation.
- The r86 fixes (P1/P2/P3/secrets-dir/script-detection) are all reversible
  and currently leave the SOPS path internally correct up to defect #6 —
  the cleanest possible state to hand the decision from.
- Voie D + ADR-017 untouched. No Anthropic API. No secret fabricated or
  handled by Claude (only SOPS ciphertext + a path; the age private key was
  never read/moved).

## Verification (r86, empirical, read-only between mutations)

Controlled `systemctl start ichor-briefing@pre_ny` after each fix; the
error advanced exactly as the root cause predicted at every layer
(`spawn:No such file` → `SOPS_AGE_KEY_FILE not set` → `not readable` →
`secrets dir not found` → `wrote 0` → `wrote 2` + `ICHOR_API_CLAUDE_RUNNER_URL
required`). `systemctl --failed` left **unreset** (honest broken state until
real recovery). No `reset-failed`, no serving-stack touch (ichor-api /
ichor-web2 / dashboard unaffected throughout).
