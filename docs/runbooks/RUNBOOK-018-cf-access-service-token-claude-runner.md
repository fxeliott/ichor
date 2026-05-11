# RUNBOOK-018: Activate Cloudflare Access service token on claude-runner

**Goal**: close the W102 / ADR-082 priority-0 security gap. As of
2026-05-11 the local Win11 claude-runner is exposed on the public
internet via `https://claude-runner.fxmilyapp.com` with
`require_cf_access=false`. Anyone who guesses the URL can spam Claude
calls and drain Eliot's Max 20× quota.

**Time**: 15-20 minutes total. ~10 min in the Cloudflare Zero Trust
dashboard, ~5 min on Hetzner SSH, ~3 min on Win11 to restart the
runner.

**Pre-requisite**:

- Cloudflare account `fxmily.com` (or whichever owns the
  `claude-runner.fxmilyapp.com` hostname).
- SSH access to `ichor-hetzner` (`ssh ichor-hetzner` should work
  out-of-the-box).
- Local administrator on the Win11 PC that runs the claude-runner
  uvicorn standalone (so we can edit its `.env` and restart).
- An open terminal for verification curls at the end.

**Why this matters**:

The `verify_cf_access` middleware in
`apps/claude-runner/src/ichor_claude_runner/auth.py` already validates
the `Cf-Access-Jwt-Assertion` header on every endpoint **except**
`/healthz`. The lifespan check refuses to start in production when
`require_cf_access=false`. The orchestrator `HttpRunnerClient` already
injects `CF-Access-Client-Id` + `CF-Access-Client-Secret` headers on
every call. **All the code is wired** — the only remaining work is
ops + dashboard.

---

## Step 1 — Enable Cloudflare Access (one-time, ~2 min)

If `https://one.dash.cloudflare.com` already loads your Zero Trust
team dashboard, skip to Step 2.

1. Open https://one.dash.cloudflare.com .
2. If first-time : pick a free **team domain** (≤ 32 chars, alphanumeric +
   hyphen). Example : `fxmily` → resulting team subdomain
   `fxmily.cloudflareaccess.com`.
3. Select the free plan (50 users included). No payment method
   required.
4. **Note the team domain string** (you will paste it in Step 4).

---

## Step 2 — Create a service token (~3 min)

1. In the Zero Trust dashboard → **Access** → **Service Auth** →
   **Service Tokens** → **Create Service Token**.
2. Name it `ichor-hetzner-orchestrator` (so the access logs make it
   obvious who hit the runner).
3. Duration : `Non-expiring` (or 1 year if you want forced rotation).
4. Click **Generate token**.
5. **You will see CLIENT ID + CLIENT SECRET exactly once. Copy both
   into a password manager NOW**, before clicking away. Cloudflare
   does not show the secret again.

The CLIENT ID looks like `<uuid>.access` (e.g.
`abcd1234-ef56-7890-abcd-ef1234567890.access`). The CLIENT SECRET is
a long opaque string ~ 64 chars.

---

## Step 3 — Create the Access application (~4 min)

1. In Zero Trust dashboard → **Access** → **Applications** → **Add an
   application** → **Self-hosted**.
2. Name : `claude-runner`.
3. Session duration : `24 hours` (default OK).
4. **Application domain** : add ONE rule :
   - Subdomain : `claude-runner`
   - Domain : `fxmilyapp.com`
   - Path : leave **empty** (catches the whole hostname).
5. **Identity providers** : tick **Service Auth** (so service-token
   callers do not also need a human SSO login). Untick the rest unless
   you also want a UI gate.
6. Click **Next** → **Add policy** :
   - Policy name : `allow-ichor-hetzner-orchestrator`.
   - Action : **Service Auth**.
   - **Include rule** : `Service Token` → pick
     `ichor-hetzner-orchestrator` (the one you created in Step 2).
   - Save.
7. (Optional but recommended) **Add a second policy** to bypass auth
   for `/healthz` so Hetzner's `systemd healthchecks` still work :
   - Add another application (Self-hosted) for the exact path
     `/healthz` with action **Bypass**, OR add a Cloudflare WAF rule
     `(http.request.uri.path eq "/healthz")` → Action `Skip` → `Skip
Cloudflare Access`.
   - If you skip this, Hetzner's healthcheck script must inject the
     service-token headers too — fine, but more wiring.
8. Click **Next** → **Save application**.
9. **Note the Application AUD (audience) tag** : visible in the app's
   detail page, 64 hex chars. Paste in Step 5.

---

## Step 4 — Wire Hetzner orchestrator with the service token (~5 min)

```bash
ssh ichor-hetzner

# Backup the env file before editing
sudo cp /etc/ichor/api.env /etc/ichor/api.env.bak.$(date +%Y%m%d-%H%M)

# Append (or replace if present) — keep mode 0640 owner ichor:ichor
sudo tee -a /etc/ichor/api.env > /dev/null <<'EOF'
ICHOR_API_CF_ACCESS_CLIENT_ID=<paste CLIENT ID from Step 2>
ICHOR_API_CF_ACCESS_CLIENT_SECRET=<paste CLIENT SECRET from Step 2>
EOF

# Sanity-check perms
sudo chown ichor:ichor /etc/ichor/api.env
sudo chmod 0640 /etc/ichor/api.env

# Restart all systemd services that read api.env
sudo systemctl restart ichor-api.service
sudo systemctl restart ichor-batch-session-cards.service ichor-briefing-pre_londres.service ichor-briefing-pre_ny.service ichor-briefing-ny_mid.service ichor-briefing-ny_close.service 2>/dev/null || true

# Verify the env vars are populated for the api process
sudo systemctl show ichor-api.service --property=Environment | grep -E "CF_ACCESS_CLIENT_(ID|SECRET)" || echo "vars not exported via systemctl — check api.env was read"
```

`ICHOR_API_CLAUDE_RUNNER_URL` should already be set to
`https://claude-runner.fxmilyapp.com` from previous waves. If empty,
add :

```bash
ICHOR_API_CLAUDE_RUNNER_URL=https://claude-runner.fxmilyapp.com
```

---

## Step 5 — Switch Win11 claude-runner to production + CF-Access-on (~3 min)

On the Win11 PC, edit the standalone runner's `.env` (location depends
on how you installed it ; if you use the standalone batch file
`D:\Ichor\scripts\windows\start-claude-runner-standalone.bat`, the
`.env` is in `D:\Ichor\apps\claude-runner\.env`).

```powershell
# Backup
Copy-Item D:\Ichor\apps\claude-runner\.env D:\Ichor\apps\claude-runner\.env.bak

# Set values (open in VS Code or Notepad)
code D:\Ichor\apps\claude-runner\.env
```

Required values (env prefix is `ICHOR_RUNNER_`) :

```
ICHOR_RUNNER_ENVIRONMENT=production
ICHOR_RUNNER_REQUIRE_CF_ACCESS=true
ICHOR_RUNNER_CF_ACCESS_TEAM_DOMAIN=fxmily          # from Step 1 (the part before .cloudflareaccess.com)
ICHOR_RUNNER_CF_ACCESS_AUD_TAG=<paste 64-hex AUD>  # from Step 3 #9
```

Restart the standalone runner :

```powershell
# Stop the running uvicorn process (find it via tasklist)
Get-Process | Where-Object { $_.ProcessName -eq "python" -and $_.Path -like "*ichor*" } | Stop-Process -Force
Start-Process -FilePath "D:\Ichor\scripts\windows\start-claude-runner-standalone.bat"

# Verify it started and is enforcing CF Access
Start-Sleep -Seconds 3
Invoke-WebRequest -Uri http://127.0.0.1:8766/healthz | Select-Object -ExpandProperty Content
```

The startup log line should show `require_cf_access=True` and
`environment=production`. If lifespan refuses to start, the error
message tells you exactly which variable is missing.

---

## Step 6 — Verification (~2 min)

From any machine with internet (not Win11, not Hetzner) :

```bash
# Without service-token headers : should return 401
curl -sS -o /dev/null -w "%{http_code}\n" https://claude-runner.fxmilyapp.com/v1/usage
# Expected : 401 (Cf-Access-Jwt-Assertion missing) — Cloudflare blocks at the edge

# With service-token headers : should return 200
curl -sS -H "CF-Access-Client-Id: <CLIENT_ID>" \
       -H "CF-Access-Client-Secret: <CLIENT_SECRET>" \
       https://claude-runner.fxmilyapp.com/v1/usage
# Expected : 200 + JSON body with in_flight, rate_limit_remaining, etc.

# /healthz bypass policy (Step 3 #7) should still work without auth
curl -sS https://claude-runner.fxmilyapp.com/healthz
# Expected : 200 + JSON body. If 401, the bypass policy is missing.
```

From `ichor-hetzner`, trigger one real briefing to confirm end-to-end :

```bash
sudo systemctl start ichor-briefing-pre_ny.service
sudo journalctl -u ichor-briefing-pre_ny.service -f
# Expected : briefing completes, no 401 errors. Cards appear in
# session_card_audit within ~3 minutes.
```

---

## Rollback

If briefings break after Step 5 :

1. Edit the Win11 `.env` and set `ICHOR_RUNNER_REQUIRE_CF_ACCESS=false`.
2. Restart the standalone runner.
3. The CF Access app stays in place (denies traffic harmlessly) — the
   runner just no longer validates the JWT. **The runner is again
   public ; this is a temporary state**.
4. File a fresh ticket : "W102 CF Access blocked briefings — root cause
   ?". Usually it's a typo in `CF_ACCESS_TEAM_DOMAIN` or `AUD_TAG`.

To **fully revert** (return to pre-W102 state) :

1. In Zero Trust dashboard → delete the `claude-runner` Access
   application.
2. Delete the `ichor-hetzner-orchestrator` service token.
3. Remove the two `ICHOR_API_CF_ACCESS_*` lines from
   `/etc/ichor/api.env`, restart `ichor-api`.
4. Set `ICHOR_RUNNER_REQUIRE_CF_ACCESS=false` on Win11.

---

## Why we did not also pin by IP

The Hetzner egress IP is stable
(178.104.39.201 + 2a01:4f8:...) and could be allow-listed via Cloudflare
WAF instead of (or in addition to) service tokens. We do not, because :

- Service tokens give per-caller audit visibility in Cloudflare logs
  (vs. an IP allow-list which is anonymous).
- Service tokens rotate independently of network topology — if Hetzner
  swaps the IP for a different VPS or adds an IPv6 second address,
  no auth re-wiring is needed.
- IP allow-lists do not protect against compromise of the Hetzner host
  itself (a malicious process on the VPS could still hit the runner) ;
  service tokens are stored in `api.env` mode 0640 and a malicious
  process there is already game-over for everything else too, so the
  marginal protection is identical.

We may revisit and add an IP allow-list as a defence-in-depth second
layer once W102 is fully validated and Eliot wants extra rigor.

---

## References

- ADR-082 (W102 priority 0 security rationale)
- ADR-083 D2 (next waves dependent on this)
- `apps/claude-runner/src/ichor_claude_runner/auth.py` — JWT verifier
- `apps/claude-runner/src/ichor_claude_runner/config.py` — env vars
- `packages/ichor_brain/src/ichor_brain/runner_client.py:176-180` —
  orchestrator-side header injection (already wired)
- Cloudflare docs : https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
