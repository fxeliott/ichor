# `infra/cloudflare` — Cloudflare Tunnel + Access (Hetzner ↔ Win11)

This is the connectivity glue of Voie D (ADR-009).

## Architecture

```
   ┌─────────────────────┐                       ┌─────────────────────┐
   │  Hetzner cron       │                       │  Eliot's Win11      │
   │  (every 6h)         │                       │  apps/claude-runner │
   │                     │                       │  FastAPI :8765      │
   │  curl POST          │   ┌───────────────┐   │       ↑             │
   │  https://<UUID>     │──>│  Cloudflare   │──>│  cloudflared        │
   │    .cfargotunnel    │   │     edge      │   │  (Windows service)  │
   │    .com/v1/         │   │               │   │  outbound :443 only │
   │    briefing-task    │   │  Access app + │   │                     │
   │  + service-token    │   │  service tok  │   │                     │
   └─────────────────────┘   └───────────────┘   └─────────────────────┘
```

- **No inbound port opened on Win11.** cloudflared opens an outbound HTTPS
  tunnel to Cloudflare edge (NAT-friendly, residential ISP friendly).
- **No custom domain needed.** The named tunnel is reachable at
  `<TUNNEL-UUID>.cfargotunnel.com` (Cloudflare-managed, free, stable URL).
- **Cloudflare Access service token** gates the tunnel: only Hetzner has the
  pair `CF-Access-Client-Id` + `CF-Access-Client-Secret`. Anyone hitting the
  tunnel URL without the headers gets blocked at the edge.

## One-time setup (Eliot, ~15 min)

### 1. Install cloudflared on Win11

```powershell
# Download .msi from https://github.com/cloudflare/cloudflared/releases/latest
# Look for the asset: cloudflared-windows-amd64.msi
# Or via winget (if available):
winget install --id Cloudflare.cloudflared
```

Verify:

```powershell
cloudflared --version
```

### 2. Authenticate cloudflared with Cloudflare account

```powershell
cloudflared tunnel login
```

Opens a browser → Cloudflare login → choose your zone (any zone — even a
domain you don't own; we won't use DNS routing). Stores cert at
`%USERPROFILE%\.cloudflared\cert.pem`.

### 3. Create the named tunnel

```powershell
cloudflared tunnel create ichor-claude-runner
```

Output:

```
Created tunnel ichor-claude-runner with id <TUNNEL-UUID>
Saved credentials to %USERPROFILE%\.cloudflared\<TUNNEL-UUID>.json
```

**Note the UUID** — that's our stable URL: `<UUID>.cfargotunnel.com`.

### 4. Apply config

```powershell
# Use the template in this directory as a starting point
copy infra\cloudflare\tunnel-config.yml %USERPROFILE%\.cloudflared\config.yml

# Edit config.yml: replace <TUNNEL-UUID> with the UUID from step 3
notepad %USERPROFILE%\.cloudflared\config.yml
```

### 5. Install as Windows service

```powershell
# Run as Administrator
cloudflared service install
```

Verify:

```powershell
Get-Service cloudflared
# Status should be Running
```

### 6. Create Cloudflare Access application + service token

In the Cloudflare Zero Trust dashboard
(https://one.dash.cloudflare.com/<account>/access/applications):

a. **Add an application** → Self-hosted
b. Name: `ichor-claude-runner`
c. Application domain: leave blank (we use the cfargotunnel URL via Settings → Tunnel UUID)
d. Identity providers: Service Auth only
e. Save

Then: Access → Service Auth → Service tokens → **Create Service Token**

- Name: `ichor-hetzner-prod`
- Duration: leave default (years)
- Save → copy `Client ID` + `Client Secret`

Add policy on the application: **Allow** when `Service Auth Token = ichor-hetzner-prod`.

Store the token pair in `infra/secrets/cloudflare.env`:

```
CF_ACCESS_CLIENT_ID=...
CF_ACCESS_CLIENT_SECRET=...
CF_TUNNEL_UUID=...
CF_ACCESS_AUD_TAG=...   # from Application > Settings > AUD tag
CF_ACCESS_TEAM_DOMAIN=...  # e.g. "eliot" → eliot.cloudflareaccess.com
```

Then `sops --encrypt --in-place infra/secrets/cloudflare.env`.

### 7. Test from Hetzner

```bash
ssh ichor-hetzner
curl -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
     -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
     https://<TUNNEL-UUID>.cfargotunnel.com/healthz
```

Expected: JSON body with `{"status": "ok", "claude_cli_available": true, ...}`.
