# RUNBOOK-019: ADR-099 Tier 0.2 — externally-gated items (Eliot final gesture only)

**Goal**: turn the 5 remaining Eliot-gated items into copy-paste one-liners
with zero ambiguity. Everything Claude could safely automate is already
done (audit, ADR-099, deploy r73, PR #138). What is left here **requires a
credential Claude must not fabricate or exfiltrate, or a browser dashboard
with no API**. Per ADR-099 §D-4: Claude prepared; Eliot performs the final
irreversible/shared-state gesture.

**Time**: ~25 min total Eliot wall-clock, split below. Most steps Claude
finishes once Eliot pastes back the opaque values (RUNBOOK-018 pattern).

## TL;DR — who does what

| #   | Item                                                        | Eliot (browser/secret)                                                              | Claude (after paste)                                               |
| --- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 1   | **Merge PR #138** (37 commits → main)                       | ~3 min: review + click _Merge_ (Squash or Merge-commit)                             | — (prod unaffected: scp-deploy)                                    |
| 2   | **Stable `/briefing` URL** (kill the rotating quick tunnel) | ~8 min: create a _named_ CF tunnel + DNS on `fxmilyapp.com` (Option A, recommended) | ~5 min: swap `ichor-web2-tunnel` to the named tunnel + verify      |
| 3   | **`ICHOR_CI_FRED_API_KEY`** GH secret (ADR-097 nightly)     | ~2 min: `gh secret set` with your FRED key                                          | — (then ADR-097 CI runs once T3.1 ships the script)                |
| 4   | **Rotate leaked creds** (FRED key + CF token in journald)   | ~6 min: regenerate both in their dashboards                                         | ~4 min: update Hetzner env + SOPS + restart (you paste new values) |
| 5   | **Revoke PAT** `ichor-session-2026-05-15-claude-autonomy`   | ~1 min: GitHub settings → revoke                                                    | —                                                                  |

**Security rule (RUNBOOK-018 pattern)**: any opaque secret stays only in
your password manager + Hetzner `/etc/ichor/api.env` (mode 0640) + GitHub
encrypted secrets. **Never pasted into chat beyond paste-and-act, never
committed.** Claude will never read or echo a secret value.

---

## Item 1 — Merge PR #138

PR: **https://github.com/fxeliott/ichor/pull/138** (`claude/friendly-fermi-2fff71` → `main`).

1. Open the PR. Skim the description (r50→r73 summary + audit disclosure).
2. Optional: wait for CI checks (`gh pr checks 138`).
3. Click **Merge** (any strategy — the branch is a clean fast-forward,
   `main` is an ancestor, **no conflicts possible**).

**Prod impact: none by construction.** The backend is scp-deployed
(`/opt/ichor` is not a git repo) and `/briefing` is deployed via
`redeploy-web2.sh`. Merging only syncs `main` to reality and unblocks CI
on the canonical branch. No deploy is triggered by the merge.

---

## Item 2 — Stable `/briefing` URL (recommended: named CF tunnel)

**Why**: r73 used a cloudflared _quick_ tunnel — the
`*.trycloudflare.com` URL **rotates on every service restart**. You need a
fixed hostname. You already own `fxmilyapp.com` on Cloudflare (it fronts
`claude-runner.fxmilyapp.com`), so a **named tunnel** reuses that infra and
keeps it private — preferred over CF Pages (which publishes a public
`*.pages.dev` by default).

### Step 2a — Eliot, Cloudflare dashboard (~8 min)

1. https://one.dash.cloudflare.com → **Networks** → **Tunnels** →
   **Create a tunnel** → **Cloudflared**.
2. Name: `ichor-web2`. Click **Save tunnel**.
3. On the "Install connector" screen, **copy the tunnel token** (the long
   string after `--token` in the shown command). Put it in your password
   manager. _Do not run their install command — Claude wires Hetzner._
4. **Public Hostname** tab → **Add a public hostname**:
   - Subdomain: `ichor` (or `briefing`)
   - Domain: `fxmilyapp.com`
   - Service: `HTTP` → `127.0.0.1:3031`
   - Save. (DNS CNAME is created automatically.)
5. **(Recommended) gate it behind CF Access** so the dashboard is not
   public — same as RUNBOOK-018: Zero Trust → Access → Applications →
   Add self-hosted app for `ichor.fxmilyapp.com`, policy = your email
   (Google/GitHub SSO) so only you can open it.

### Step 2b — Eliot pastes back, Claude finishes (~5 min)

Paste into chat (the token is opaque, single-use to register the connector):

```
ICHOR_WEB2_TUNNEL_TOKEN: <the --token string from Step 2a #3>
ICHOR_WEB2_HOSTNAME    : ichor.fxmilyapp.com   (or whatever you chose)
```

Claude then, on Hetzner:

```bash
# store token, rewrite ichor-web2-tunnel.service to a NAMED tunnel
ssh ichor-hetzner
sudo mkdir -p /etc/cloudflared
echo '<TOKEN>' | sudo tee /etc/cloudflared/ichor-web2.token >/dev/null
sudo chmod 0600 /etc/cloudflared/ichor-web2.token
sudo tee /etc/systemd/system/ichor-web2-tunnel.service >/dev/null <<'UNIT'
[Unit]
Description=Ichor web2 named Cloudflare tunnel (stable hostname)
After=ichor-web2.service network-online.target
Wants=ichor-web2.service network-online.target
[Service]
Type=simple
User=ichor
Group=ichor
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate run --token-file /etc/cloudflared/ichor-web2.token
Restart=on-failure
RestartSec=10
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload && sudo systemctl restart ichor-web2-tunnel
# verify
curl -fsS -o /dev/null -w '%{http_code}\n' https://<ICHOR_WEB2_HOSTNAME>/briefing
```

Expected: `200`. The URL is now **permanent across restarts/reboots**.
This closes the r73 SESSION_LOG caveat. Update `redeploy-web2.sh` to write
the named-tunnel unit by default (Claude does this as a code change +
commit once verified).

### Alternative (Option B, not recommended): CF Pages

Needs `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` as GitHub secrets
and publishes a public `*.pages.dev`. Rejected here because it conflicts
with your "ultra-private" directive and the SSR briefing needs a server
runtime (Pages = static/edge; the dashboard is `next start` SSR). Keep the
Hetzner named tunnel.

---

## Item 3 — `ICHOR_CI_FRED_API_KEY` GitHub secret

ADR-097's nightly FRED-liveness CI needs a FRED API key as a repo secret.
(Note: the workflow's target script is itself missing — that is **ADR-099
Tier 3.1**, a code fix Claude will ship; this secret is the ops half.)

Eliot, ~2 min — use the **same** FRED key the backend already uses (it is
in your records / FRED account at https://fredaccount.stlouisfed.org →
_API Keys_; do **not** paste it in chat):

```bash
gh secret set ICHOR_CI_FRED_API_KEY --repo fxeliott/ichor
# paste the key at the prompt (gh reads stdin, never echoes it)
```

Verify (value stays hidden):

```bash
gh secret list --repo fxeliott/ichor | grep ICHOR_CI_FRED_API_KEY
```

---

## Item 4 — Rotate leaked credentials (FRED key + CF token)

The audit found the FRED API key and a Cloudflare secret were printed into
`journald` logs at some point. Rotation makes the leaked copies useless
(simpler + safer than scrubbing logs).

### 4a — FRED key (Eliot, ~3 min)

1. https://fredaccount.stlouisfed.org → **API Keys** → **Request/▸
   Regenerate** a key. Old key dies immediately.
2. Put the new key in your password manager.
3. Paste back: `NEW_FRED_API_KEY: <value>` — Claude updates Hetzner
   `/etc/ichor/api.env` (backup first, mode 0640), updates the SOPS file
   `infra/secrets/*.env` if present, re-runs `gh secret set
ICHOR_CI_FRED_API_KEY`, restarts the FRED collectors, and verifies a
   live FRED fetch.

### 4b — Cloudflare token (Eliot, ~3 min)

1. https://dash.cloudflare.com → **My Profile** → **API Tokens** (or the
   token used by `wrangler-action`/`infra/secrets/cloudflare.env`).
   **Roll** it. Old token dies.
2. Scope minimally (the only repo use is `Account.Cloudflare Pages:Edit`
   per W100f audit; if Pages stays unused, you may delete the token
   entirely instead of rolling).
3. Paste back `NEW_CF_API_TOKEN: <value>` → Claude updates the SOPS file
   `infra/secrets/cloudflare.env`, commits the re-encrypted blob (the
   ciphertext is safe to commit), and verifies `curl
/user/tokens/verify` → 200.

After both rotations the journald-leaked copies are dead. Optional extra:
`sudo journalctl --rotate && sudo journalctl --vacuum-time=1s` on Hetzner
to drop old logs entirely (Claude can do this once you confirm).

---

## Item 5 — Revoke the autonomy PAT (Eliot, ~1 min)

The session PAT `ichor-session-2026-05-15-claude-autonomy` is no longer
needed (gh uses the keyring auth).

1. https://github.com/settings/tokens
2. Find `ichor-session-2026-05-15-claude-autonomy` → **Delete** / **Revoke**.
3. Confirm `gh auth status` still shows `Logged in ... (keyring)` (it does
   — that is a separate credential).

---

## Rollback

- Item 1: a merged PR is reverted with `git revert -m 1 <merge_sha>` on a
  new branch + PR. Prod is unaffected regardless (scp-deploy).
- Item 2: `scripts/hetzner/redeploy-web2.sh` (re-running it rewrites the
  quick-tunnel unit) or keep the named tunnel and just delete the CF
  tunnel in the dashboard to fall back.
- Items 3-5: secrets — re-add / re-create if a rotation broke something;
  RUNBOOK-015 (secrets rotation) covers the general recovery.

## References

- ADR-099 §D-3 Tier 0.2 + §D-4 autonomy boundary
- RUNBOOK-018 (the secret-paste-and-act pattern reused here)
- RUNBOOK-015 (secrets rotation generic)
- SESSION_LOG 2026-05-16 r73 (the quick-tunnel caveat this closes)
- PR: https://github.com/fxeliott/ichor/pull/138
- `scripts/hetzner/redeploy-web2.sh` (the deploy script Item 2 amends)
