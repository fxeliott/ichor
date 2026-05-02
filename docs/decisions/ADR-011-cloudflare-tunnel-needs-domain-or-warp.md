# ADR-011: Cloudflare Tunnel public exposure requires custom domain OR WARP Connector

- **Status**: Pending Eliot decision
- **Date**: 2026-05-02
- **Decider**: Eliot (re-engage when ready)

## Context

We tried to use Cloudflare Tunnel to expose `apps/claude-runner` (Win11 :8765)
to Hetzner WITHOUT a custom domain, expecting `<UUID>.cfargotunnel.com` to
serve as a stable public URL.

Reality: `<UUID>.cfargotunnel.com` resolves to IPv6 ULA addresses
(`fd10::/8` — Unique Local Addresses, RFC 4193). Those addresses are
explicitly **non-routable on the public Internet**. Cloudflare uses them
internally to route traffic from Cloudflare's edge to tunnels, but external
clients cannot reach them.

This is by design. To make a tunnel publicly reachable, Cloudflare requires
ONE of:

1. **DNS route on a Cloudflare-managed zone** (custom domain):
   ```
   cloudflared tunnel route dns <UUID> claude-runner.eliotsdomain.com
   ```
   This creates a CNAME → `<UUID>.cfargotunnel.com` ON YOUR ZONE. Requests
   to `claude-runner.eliotsdomain.com` then route to your tunnel.
   **Requires**: Eliot owns and has at least one domain on Cloudflare.

2. **Cloudflare Access + WARP Connector** on the calling machine (private
   network access):
   - Enable Cloudflare Access in the Zero Trust dashboard (1-click, free
     up to 50 users).
   - On Hetzner, install `cloudflared` in WARP-Connector mode.
   - Hetzner joins the same private mesh as the tunnel.
   - Hetzner can then reach `<UUID>.cfargotunnel.com` via the mesh routes.

3. **Quick Tunnel** (`cloudflared tunnel --url http://localhost:8765`):
   Generates a one-off `*.trycloudflare.com` URL on each launch.
   **URL changes every cloudflared restart** — incompatible with cron-driven
   periodic POSTs from Hetzner.

## Decision

**Defer the production tunnel setup until Eliot picks an option.**

Phase 0 deliverables:
- ✅ Tunnel created (`97aab1f6-bd98-4743-8f65-78761388fe77`) via API
- ✅ credentials.json + config.yml in `~/.cloudflared/`
- ✅ cloudflared verified to register 4 connections to Cloudflare edge (MRS)
- ❌ Public reachability requires Eliot's choice between options 1/2

`apps/claude-runner` Windows service stays running on `127.0.0.1:8765`.
`apps/api` on Hetzner has `ICHOR_API_CLAUDE_RUNNER_URL` set to a placeholder.
End-to-end Hetzner→Win11 path is intentionally cold until tunnel is reachable.

## Recommended option (when Eliot returns)

**Option 1 — buy `ichor.fyi` ($15.18/year via Cloudflare Registrar)**:
- Aligns with Phase 1 domain decision (was deferred ADR-002 — could un-defer
  partially)
- Use `claude-runner.ichor.fyi` as the tunnel hostname
- Future-proof: same domain serves the dashboard later (or use subdomain
  `app.ichor.fyi`)
- Total time: 5 min to register + 2 min to add DNS route

**Option 2 — Cloudflare Access + WARP Connector**:
- $0/month
- 1 click to enable Access in dashboard
- Then ~10 min to install + configure WARP on Hetzner (apt install)
- Hetzner enters Cloudflare's private mesh

If Eliot already owns ANY domain (even `.xyz` $1/year), point it at
Cloudflare and use option 1.

## Consequences

- Phase 0 W3 step 19 (tunnel routing) stays YELLOW until decided
- claude-runner service runs but receives no Hetzner traffic until tunnel
  is reachable
- The 33-alert engine + bias signals + briefing CLI work fine with
  sample/seed data — no dependency on tunnel for backend/frontend dev
- When tunnel is wired, swap `ICHOR_API_CLAUDE_RUNNER_URL` env var on
  Hetzner + restart `ichor-api`. No code change needed.

## References

- [Cloudflare Tunnel docs — public hostname routing](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/routing-to-tunnel/)
- [Cloudflare WARP Connector](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/private-net/cloudflared/)
- RFC 4193 (IPv6 ULA addresses)
