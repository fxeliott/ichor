# RUNBOOK-012: Cloudflare quick tunnel down (`*.trycloudflare.com` URL gone)

- **Severity**: P1 if Eliot is actively trading; P2 otherwise
- **Last reviewed**: 2026-05-04
- **Time to resolve (target)**: 5 min to restart, 15 min if URL changed

## Trigger

- Browser shows "ERR_NAME_NOT_RESOLVED" or "Cloudflare 521 web server is down" for `https://<random-words>.trycloudflare.com`.
- iOS push notifications stop arriving.
- Hetzner cron `ichor-briefing-*.service` errors `claude_runner_call_failed`
  with DNS resolution failures (visible in `journalctl -u ichor-briefing-pre_londres.service -n 50`).
- Cmd+K palette shows "API offline" status dot.

## Background

The quick tunnel is what `cloudflared tunnel --url http://localhost:3000`
returns: a randomized `*.trycloudflare.com` hostname valid only for the
lifetime of the running `cloudflared` process. **It rotates on every
restart** — there's no DNS continuity.

Until [`auto-deploy.yml`](../../.github/workflows/) ships and Cloudflare
Pages serves a stable `app-ichor.pages.dev` URL (Phase D milestone, cf
[`SPEC.md §5 Phase D`](../../SPEC.md)), this runbook is the recovery path.

## Immediate actions (first 5 min)

### 1. Restart the tunnel on Win11

```powershell
# Identify the existing process (if any zombie):
Get-Process cloudflared -ErrorAction SilentlyContinue
# Kill if needed:
Stop-Process -Name cloudflared -Force

# Restart user-mode tunnel:
& "$env:USERPROFILE\Desktop\Ichor\scripts\windows\start-cloudflared-user.ps1"
```

The script prints the new `https://<random>.trycloudflare.com` URL on
stdout. **Copy it immediately.**

### 2. Update the URL where it matters

Three places consume the public URL:

a. `apps/web/.env.local` and `apps/web2/.env.local` (if used in dev):

```bash
# Edit ICHOR_API_PROXY_TARGET to the new URL
```

b. Hetzner `/etc/ichor/api.env` (if ENV var used at runtime):

```bash
ssh ichor-hetzner
sudo sed -i "s|^ICHOR_API_CLAUDE_RUNNER_URL=.*|ICHOR_API_CLAUDE_RUNNER_URL=https://<NEW>.trycloudflare.com|" /etc/ichor/api.env
sudo systemctl restart ichor-api
```

c. The user guide / README badge if you've copy-pasted it (avoid this in
the future — link to a stable URL only).

### 3. Verify end-to-end

```bash
# From Hetzner
curl -fsS https://<NEW>.trycloudflare.com/v1/usage | jq

# From your laptop
open "https://<NEW>.trycloudflare.com/healthz"
```

Both should return 200.

### 4. Briefly check Hetzner cron

The next scheduled briefing should succeed. If it's not due soon, manually
trigger:

```bash
ssh ichor-hetzner
sudo systemctl start ichor-briefing-pre_londres.service
journalctl -u ichor-briefing-pre_londres.service -f
```

## If restart doesn't help (15-min path)

### Symptom A — `cloudflared` exits immediately

```powershell
& cloudflared --version  # should show 2024.x or 2026.x
& cloudflared tunnel --url http://localhost:8766 --loglevel debug
```

Check the debug output for:

- `connection lost` → ISP / firewall blocking outbound 443. Verify `tracert -d 1.1.1.1`.
- `Failed authentication` → if you're using a named tunnel (not quick),
  re-auth: `cloudflared tunnel login`. Otherwise irrelevant for quick.
- `unable to start UDP server` → port 7844 already used; `Get-NetTCPConnection -LocalPort 7844`.

### Symptom B — tunnel up, runner unreachable

```powershell
curl http://localhost:8766/v1/usage  # locally
```

If 200 locally but tunnel returns 502: Cloudflare can't reach the runner
on `127.0.0.1:8766`. Check `infra/cloudflare/tunnel-config.yml:14` —
ingress should point to `:8766` (cf bug fix 2026-05-04).

### Symptom C — runner crashed

```powershell
Get-Process | ? Name -like "*python*"
# If nothing matches the runner, restart:
& "$env:USERPROFILE\Desktop\Ichor\scripts\windows\start-claude-runner-user.ps1"
```

Then re-run the verify step.

## Long-term fix (Phase D)

This runbook becomes obsolete once Phase D ships:

1. **Cloudflare Pages auto-deploy** for `apps/web2/` → stable
   `app-ichor.pages.dev` URL.
2. **Named Cloudflare Tunnel** with persistent UUID (already in
   [`scripts/windows/start-cloudflared-user.ps1:8`](../../scripts/windows/start-cloudflared-user.ps1)
   but UUID hardcoded — needs externalization to SOPS).
3. **DNS route** `claude-runner.ichor.app` → tunnel UUID (requires
   `ichor.app` purchase per [ADR-002](../decisions/ADR-002-domain-deferred.md)).

Until those land, accept the quick-tunnel volatility and run this runbook
on outage.

## References

- [`SPEC.md §2.2 #2, §2.2 #20, §5 Phase D`](../../SPEC.md)
- [`infra/cloudflare/tunnel-config.yml`](../../infra/cloudflare/tunnel-config.yml)
- [`scripts/windows/start-cloudflared-user.ps1`](../../scripts/windows/start-cloudflared-user.ps1)
- [ADR-011](../decisions/ADR-011-cloudflare-tunnel-needs-domain-or-warp.md)
- [RUNBOOK-008](RUNBOOK-008-anthropic-key-revoked.md) (companion if Claude
  also affected)
