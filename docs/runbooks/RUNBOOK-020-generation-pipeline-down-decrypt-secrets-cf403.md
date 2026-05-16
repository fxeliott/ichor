# RUNBOOK-020: Generation pipeline DOWN — missing decrypt-secrets + claude-runner 403

**Severity**: HIGH. The two windows Ichor's whole product is built around
— **pré-Londres and pré-NY** — are NOT generating fresh AI briefings or
session-cards. The dashboard still serves _older persisted_ cards (so it
is not visibly empty), which is exactly why this degraded **silently**.

**Discovered**: 2026-05-16 (r85 "tu es sûr" verification audit). **NOT
introduced by the r72→r84 session** — the failures date back to ≥
2026-05-15 (the r72 audit itself flagged "8 failed services @ r49,
status indeterminate" and it was deferred and never re-treated across 13
rounds — that deferral is the real process miss this RUNBOOK closes).

**Scope**: 7 failed systemd units (104 active), all on the _generation_
loop — the _serving_ stack (`ichor-api`, `ichor-web2`, the `/briefing`
dashboard, all read endpoints) is fully healthy and unaffected.

## ⚠️ r86 RE-VERIFICATION & TURNKEY (2026-05-16) — read before §Recovery

A skeptical 2-agent re-audit on 2026-05-16 (r86: read-only Hetzner SSH +
repo provenance, doctrine R59 / "tu es sûr"=audit-harder) **confirmed all
four structural claims live** but corrected three points and produced an
exact turnkey. These corrections **supersede** the conflicting prose in
§"Root cause" / §"Step A" below (originals kept for audit trail).

> ### ⚠️⚠️ r86 CONTINUED — the turnkey in THIS section was itself superseded
>
> The empirical triage (one controlled `ichor-briefing@pre_ny` run after
> each fix) went deeper and **disproved the "A-ii age key — Eliot only"
> item below**: the age key **is present and valid** at
> `/etc/sops/age/key.txt` (`-rw------- root root`, decrypts `exit=0`). The
> original audit checked the sops _default_ path
> `/root/.config/sops/age/keys.txt`, not the design path. **A-ii is VOID —
> Eliot does NOT need to restore any key.**
>
> The `ichor-briefing@*` SOPS path had **6 stacked defects**. r86 fixed 5
> (all reversible, Claude-safe): **P1** redeploy script + **P2**
> `SOPS_AGE_KEY_FILE` drop-in + **P3** `ExecStartPre=+` (run as root) +
> deployed the encrypted `/opt/ichor/infra/secrets/` + **fixed a script
> bug** (`ichor-decrypt-secrets` `^sops:`-only detection silently skipped
> dotenv-SOPS files → 0-byte bundle ; now `grep -qE '^sops:|^sops_version='`,
> empirically `wrote 2 secret bundle(s)`). Defect #6 is **architectural**:
> `run_briefing.py` needs the `ICHOR_API_*` config from `/etc/ichor/api.env`
> (which the working `ichor-session-cards@*` loads) — the briefing template
> never loads it. **That single remaining Cause-A decision is now
> [ADR-100](../decisions/ADR-100-briefing-secrets-provisioning-align-api-env.md)
> (Proposed, Eliot ratify — recommended Option X: use `api.env` like
> session-cards).** Plus a security finding: `ExecStartPost=shred` runs only
> on ExecStart _success_ → failed briefings leak the plaintext bundle on
> `/dev/shm` until reboot (Option X removes this surface entirely).
>
> **Net Eliot surface after r86: (1) ratify ADR-100 (~2 min decision) ;
> (2) Cause B claude-runner 403 (RUNBOOK-018, ~9 min CF dashboard).** Both
> A-ii and "redeploy from infra/ansible" are void. Cause A is otherwise
> fully Claude-resolved & reversible. Read ADR-100; the P1-A-ii subsection
> below is kept only for the evolution trail.

### Corrections

1. **The decrypt script IS in the repo** (not host-only, not Ansible). Full
   83-line working script: `scripts/hetzner/ichor-decrypt-secrets`. The
   briefing systemd template that calls it: `scripts/hetzner/register-cron-briefings.sh:33-51`
   (manual SSH-run installer; no Ansible role deploys either —
   `infra/ansible/roles/secrets/tasks/main.yml` decrypts to Ansible
   _facts_, a different mechanism, not `/dev/shm`). ⟹ Step A1 is a
   **redeploy of an existing non-secret repo artefact**, not a
   reconstruction. (§"Step A" lines below saying "restore from
   Ansible/provisioning source ... not the app repo" are **wrong**.)

2. **NEW confirmed latent bug — `SOPS_AGE_KEY_FILE` is never set for the
   briefing units.** The script hard-requires it:
   `scripts/hetzner/ichor-decrypt-secrets:33-34` →
   `fail "SOPS_AGE_KEY_FILE not set" 2`. The briefing template `[Service]`
   block (`register-cron-briefings.sh:40-50`) sets `EnvironmentFile=` +
   `ExecStartPre=` but **no `Environment=SOPS_AGE_KEY_FILE=`**. ⟹ even
   with the script + age key restored, `ichor-briefing@*` still
   `exit 2` unless a drop-in supplies it (fix **P2** below). Encrypted
   files live at `/opt/ichor/infra/secrets/*.env`
   (`ichor-decrypt-secrets:25`); design key path is `/etc/sops/age/key.txt`
   (`.sops.yaml:26` + `infra/ansible/roles/secrets/tasks/main.yml:26,45`).

3. **"DOWN since May 15" → "degraded/intermittent, escalating".** Live
   `select max(created_at) from session_card_audit` = **2026-05-16 22:16**
   (a card persisted today). Failure escalated: May 15 the script existed
   but decrypt failed (key/perm); by May 16 the binary itself is gone.
   Accurate framing: the **two core windows (pré-Londres 06:00, pré-NY
   12:00 Paris) serve stale/not-fresh analysis** — still HIGH severity
   (the product's core read is stale on its two key windows), but not a
   flat outage.

### Key recovery fact — multi-recipient SOPS (`.sops.yaml:32-49`)

Every `infra/secrets/*.env` is age-encrypted to **two** recipients:
(1) Eliot's Win11 key `age1rgrex…l08xaj` (private: USB
`E:\age-key-ichor-2026-05-02.txt` + `%APPDATA%\sops\age\keys.txt`);
(2) the separate Hetzner server key `age1dqhae…t5dch` (private:
`/etc/sops/age/key.txt` root:root 0600 — deliberately kept off Eliot's
machine, `.sops.yaml:28-30`). The host currently has neither the script
nor any key. **Either** private key can decrypt (multi-recipient) — that
is what gives Eliot a fast path and a clean path in A-ii below.

### TURNKEY — exactly who does what

**Cause A — `ichor-briefing@*` (4 units). Three Claude-safe sub-fixes +
one Eliot-only secret:**

- **P1 — redeploy the repo script** (Claude-safe: non-secret git artefact,
  reversible; gated on Eliot "validate" per the autonomy boundary):

  ```bash
  # local, from the friendly-fermi worktree root
  scp scripts/hetzner/ichor-decrypt-secrets ichor-hetzner:/tmp/ichor-decrypt-secrets
  ssh ichor-hetzner 'sudo install -m 0755 -o root -g root /tmp/ichor-decrypt-secrets /usr/local/bin/ichor-decrypt-secrets && command -v sops && command -v age'
  ```

  Reversible: `sudo rm /usr/local/bin/ichor-decrypt-secrets`. If
  `sops`/`age` absent → `sudo apt-get install -y age && sudo snap install sops`
  (Eliot/ops if apt needs interaction).

- **P2 — systemd drop-in for the missing `SOPS_AGE_KEY_FILE`** (Claude-safe,
  reversible, path only — no secret; gated on validation):

  ```bash
  ssh ichor-hetzner 'sudo mkdir -p /etc/systemd/system/ichor-briefing@.service.d && printf "[Service]\nEnvironment=SOPS_AGE_KEY_FILE=/etc/sops/age/key.txt\n" | sudo tee /etc/systemd/system/ichor-briefing@.service.d/age-key.conf && sudo systemctl daemon-reload'
  ```

  Reversible: `rm` the drop-in + `daemon-reload`.

- **Step-A2 — `EnvironmentFile` graceful-degrade** (Claude-safe, reversible;
  gated): the original RUNBOOK-020 hardening (see §"Step A2" below) — the
  `-` prefix so a future decrypt-miss soft-fails instead of hard-failing.

- **A-ii — restore a working age private key to `/etc/sops/age/key.txt`
  (root:root, `chmod 600`). ELIOT ONLY — secret material, Claude must NOT
  touch or fabricate.** Pick ONE:
  - **Fast (posture-downgrade — your explicit call):** copy Eliot's own
    private key from USB `E:\age-key-ichor-2026-05-02.txt` to host
    `/etc/sops/age/key.txt`. Works immediately (recipient #1). ⚠️ Places
    Eliot's master key on the server, which `.sops.yaml:28-30` deliberately
    avoided. Acceptable stopgap; rotate after.
  - **Clean (preserves design):** restore the **Hetzner** key
    (`age1dqhae…`) private backup to `/etc/sops/age/key.txt`. If lost:
    on host `sudo age-keygen -o /etc/sops/age/key.txt && sudo chmod 600 /etc/sops/age/key.txt`,
    take the printed `# public key:`, replace recipient #2 in
    `.sops.yaml:37,43,49`, `sops updatekeys infra/secrets/*.env` locally
    (Eliot's Win11 key authorizes it), commit the re-encrypted files,
    redeploy them to `/opt/ichor/infra/secrets/`. Claude can do the
    `.sops.yaml` edit + redeploy once you give the new public key; the
    private key never leaves the host.

**Cause B — `ichor-session-cards@*` (3 units): claude-runner 403. ELIOT
~9 min (see RUNBOOK-018).**

- Shortcut check first (`RUNBOOK-018:46-61`):
  `one.dash.cloudflare.com → Access → Applications` — if a `claude-runner`
  app already exists you may only need the 4 values from the existing
  service token (skip dashboard Steps 1-3).
- Else RUNBOOK-018 Steps 1-3 (~9 min): enable CF Access + note team
  domain · create Service Token `ichor-hetzner-orchestrator` (copy
  CLIENT_ID + CLIENT_SECRET once to your password manager) · create
  Self-hosted Access app on `claude-runner.fxmilyapp.com` + Service-Auth
  policy + `/healthz` Bypass + note 64-hex AUD tag.
- Paste the 4 values (format `RUNBOOK-018:33-38`) → Claude wires
  `/etc/ichor/api.env` + restarts (Steps 4-6).
- Also confirm the Win11 claude-runner runs in `production`
  (RUNBOOK-018 Step 5 / RUNBOOK-014) — if NSSM-Paused or the standalone
  uvicorn is down, healthz stays unreachable even with the token wired.

**Step C — verify (Claude, after A-ii + B done).** One consolidated SSH:
`sudo systemctl reset-failed 'ichor-*'`, start `ichor-session-cards@pre_londres`

- `ichor-briefing@pre_londres`, watch journal for a clean run + a fresh
  `session_card_audit` row.

### Order of operations (minimal Eliot effort)

1. **Eliot:** A-ii (age key — fast or clean) + RUNBOOK-018 Steps 1-3,
   paste the 4 values.
2. **Claude (on Eliot "validate"):** P1 + P2 + Step-A2 (one consolidated
   SSH), then RUNBOOK-018 Steps 4-6.
3. **Claude:** Step C verify read-only, surface the first fresh
   pré-Londres/pré-NY card honestly.

Until A-ii + B are done, the two core windows keep serving stale analysis
(no data loss; degraded freshness only).

## Symptom

`systemctl --failed | grep ichor` →

- `ichor-briefing@{ny_close,ny_mid,pre_londres,pre_ny}.service`
- `ichor-session-cards@{ny_mid,pre_londres,pre_ny}.service`

## Root cause (evidence-verified, R59)

**Cause A — `ichor-briefing@*` (4 units): host provisioning gap.**
`systemctl cat ichor-briefing@pre_ny` shows:

```
EnvironmentFile=/dev/shm/ichor-secrets.env        # NO '-' prefix → hard-fail if missing
ExecStartPre=/usr/local/bin/ichor-decrypt-secrets # supposed to CREATE that file
ExecStart=.../python -m ichor_api.cli.run_briefing %i
ExecStartPost=/usr/bin/shred -u /dev/shm/ichor-secrets.env
```

`ls /usr/local/bin/ichor-decrypt-secrets` → **No such file or directory**.
No SOPS/age key at `/etc/ichor/*.sops.*`, `/etc/ichor/age*`,
`/root/.config/sops/age/keys.txt`. So: the decrypt-secrets provisioning
script (and its key) is **absent from the host** → `ExecStartPre`
cannot spawn → `/dev/shm/ichor-secrets.env` is never created →
`EnvironmentFile=` (no `-` prefix) hard-fails →
`result 'resources'`. Journal: `Failed to spawn 'start-pre' task: No
such file or directory` then `Failed to load environment files`.

**Cause B — `ichor-session-cards@*` (3 units): claude-runner 403.**
These use `EnvironmentFile=/etc/ichor/api.env` (exists) so they START,
then fail `result 'timeout'` (≈48s CPU then timeout). `curl
https://claude-runner.fxmilyapp.com/healthz` → **HTTP 403**. The Win11
`claude-runner` is gated/down (CF Access not satisfied or NSSM-`Paused`
fragility — the long-documented W102 / RUNBOOK-018 item). Even if Cause
A were fixed, `ichor-briefing@*` would then also hit this 403.

**Both causes pre-date the r72→r84 session and are Eliot/ops-gated**:
recreating a secrets-decrypt script + age key, or fixing CF-Access /
the Win11 runner, requires credentials/dashboards Claude must not
fabricate or touch autonomously (security guardrails + W102 boundary).
Claude's autonomous deploys this session were additive (`ichor-web2`)

- `ichor-api`-only (`redeploy-api.sh`) and never touched these units,
  `/usr/local/bin`, `/dev/shm`, or the secrets infra (verified: failure
  timestamps May 15 predate the May 16 session).

## TL;DR — who does what

| #   | Step                                                                                                                                                     | Who                                                          | Why                                                            |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------- |
| A1  | Restore `/usr/local/bin/ichor-decrypt-secrets` + the SOPS/age key                                                                                        | **Eliot/ops**                                                | Secrets infra — Claude must not fabricate a decrypt script/key |
| A2  | (hardening) `EnvironmentFile=-/dev/shm/ichor-secrets.env` (add `-`) so a future decrypt miss degrades gracefully instead of hard-failing                 | Eliot approves → Claude can apply (systemd-only, reversible) | Latent robustness bug, independent of the secret content       |
| B1  | Fix `claude-runner.fxmilyapp.com` 403 (CF Access service token + Win11 runner)                                                                           | **Eliot** (~15 min)                                          | RUNBOOK-018 / RUNBOOK-019 Item 2 — CF dashboard + Win11        |
| C   | After A+B: `sudo systemctl reset-failed 'ichor-*' && sudo systemctl start ichor-session-cards@pre_londres ichor-briefing@pre_londres` then watch journal | Claude (once A+B done, automatable)                          | verify recovery on the 2 critical windows                      |

## Recovery — detailed

### Step A — restore decrypt-secrets (Eliot/ops)

> **⚠️ SUPERSEDED by §"r86 RE-VERIFICATION & TURNKEY" above.** The next
> paragraph's "not the app repo / confirm in infra/ansible/" is **wrong**:
> the script is `scripts/hetzner/ichor-decrypt-secrets` (in the repo).
> Follow the r86 turnkey (P1/P2/Step-A2/A-ii), not the prose below.

The `ichor-briefing@*` design decrypts secrets to a tmpfs file just for
the run, then shreds it. The script `/usr/local/bin/ichor-decrypt-secrets`
is the missing piece. Eliot must restore it from the Ansible/provisioning
source (it is part of host provisioning, not the app repo — confirm in
`infra/ansible/`), along with the SOPS age key it uses. If the design is
to be simplified, the supported alternative already used by
`ichor-session-cards@*` is `EnvironmentFile=/etc/ichor/api.env` (plain
0640 file, exists) — switching `ichor-briefing@*` to that same mechanism
would remove the decrypt-secrets dependency entirely (decision for
Eliot; it changes the secrets-at-rest posture on the host).

### Step A2 — graceful-degradation hardening (Claude, once Eliot approves)

```bash
ssh ichor-hetzner
sudo mkdir -p /etc/systemd/system/ichor-briefing@.service.d
sudo tee /etc/systemd/system/ichor-briefing@.service.d/envfile-optional.conf >/dev/null <<'EOF'
[Service]
# Make the tmpfs secrets file optional at load time — the '-' prefix
# means "skip if missing" instead of hard-failing the unit before
# ExecStartPre has had a chance to create it.
EnvironmentFile=
EnvironmentFile=-/dev/shm/ichor-secrets.env
EOF
sudo systemctl daemon-reload
```

Reversible: `rm` the drop-in + `daemon-reload`. NB: this only converts a
hard-fail into a soft-fail; the run still needs the secrets (Step A) +
claude-runner reachable (Step B) to actually succeed.

### Step B — claude-runner 403 → see RUNBOOK-018 / RUNBOOK-019 Item 2.

### Step C — verify (Claude, after A+B)

```bash
ssh ichor-hetzner
sudo systemctl reset-failed 'ichor-*'
sudo systemctl start ichor-session-cards@pre_londres.service
sudo journalctl -u ichor-session-cards@pre_londres.service -f   # expect: cards persisted, no 403/timeout
# then the next scheduled pre_londres/pre_ny timer fire should succeed
```

## Impact while DOWN

- `/briefing` keeps rendering **real but not-fresh** cards (the freshest
  persisted card was 2026-05-16 ~17:26 — some non-broken window still
  runs; but `pre_londres` + `pre_ny`, the product's core windows, are
  NOT producing fresh analysis).
- All read endpoints + the 8 dashboard layers are unaffected (serving
  stack healthy).
- Honest user-facing consequence: on the broken windows the trader sees
  the previous window's / yesterday's analysis, not a fresh pre-session
  read. The `BriefingHeader` relative-timestamp + the r84 pocket-skill
  staleness surface this somewhat, but a future round should add an
  explicit "card age" / "génération en échec" banner (candidate
  Tier-3 autonomy-hardening item — see ADR-099).

## References

- ADR-099 §D-3 Tier 3 (autonomy hardening) — this is now its #1 item.
- RUNBOOK-018 (CF Access service token — Cause B).
- RUNBOOK-019 Item 2 (claude-runner stable URL / CF — Cause B).
- RUNBOOK-014 (claude-runner Win11 down).
- Original r72 10-subagent audit ("8 failed services @ r49, status
  indeterminate") — the deferred finding this RUNBOOK closes.
- Verified read-only 2026-05-16 r85: `systemctl --failed`,
  `systemctl cat ichor-briefing@pre_ny`, `ls /usr/local/bin/ichor-decrypt-secrets`
  (absent), `curl claude-runner/healthz` (403), journal `result
'resources'` / `'timeout'`.
