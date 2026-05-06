# ADR-002: Defer `ichor.app` domain purchase to Phase 1+

- **Status**: Accepted
- **Date**: 2026-05-02
- **Decider**: Eliot (validated 2026-05-02)

## Context

`docs/ARCHITECTURE_FINALE.md` line 98 lists `Domain | ichor.app (Cloudflare
Registrar ~14€/an)` as Phase 0 Week 1 step 1.

On 2026-05-02 we verified:

- `ichor.app` resolves to `185.158.133.1` (nameservers `dns1/dns2.registrar-servers.com` = Namecheap)
- Live HTTPS site: project "ichor-vitality-nexus" built with [Lovable.dev](https://lovable.dev) (no-code AI builder, early-stage)
- No "for sale" notice, no public asking price → buyout would require WHOIS contact + open-ended negotiation
- Cloudflare Registrar `.app` price 2026-05-02: $14.20/yr ([cfdomainpricing.com](https://cfdomainpricing.com/))

Available alternatives verified via DNS NXDOMAIN check + Cloudflare price API:

| Domain         | DNS resolves?    | CF price/yr |
| -------------- | ---------------- | ----------- |
| `ichor.fyi`    | NXDOMAIN         | $15.18      |
| `getichor.com` | NXDOMAIN         | $10.46      |
| `ichor.com`    | resolves (taken) | —           |
| `ichor.io`     | resolves (taken) | —           |
| `ichor.dev`    | resolves (taken) | —           |
| `ichor.ai`     | resolves (taken) | —           |

## Decision

For **Phase 0**, purchase no domain. Operate Ichor on free Cloudflare
sub-domains:

- Frontend → `app-ichor.pages.dev` (auto-assigned by Cloudflare Pages on deploy)
- Hetzner ↔ local Win11 tunnel → `<TUNNEL-UUID>.cfargotunnel.com` via Named
  Cloudflare Tunnel (URL stable, accessible only via Cloudflare Access
  service-token gating)

For **Phase 1**, Eliot revisits the domain choice (negotiate `ichor.app`
buyout, or pick `ichor.fyi` / `getichor.com` / a fresh name).

## Consequences

- **Cloudflare Access Zero-Trust** (Phase 0 step 8) is **deferred to Phase 1+**:
  CF Access requires a custom Cloudflare DNS zone, which `*.pages.dev` and
  `*.cfargotunnel.com` are not. We rely on tunnel service-token authentication
  alone for now.
- All hostnames in `docs/ARCHITECTURE_FINALE.md` referencing `*.ichor.app`
  must be re-mapped at Phase 1 cutover. Documented in PHASE_0_LOG.md.
- **YubiKey MFA** on Cloudflare/Hetzner/GitHub/Anthropic (also step 8) stays
  in Phase 0 — independent of the domain.
- Quick Tunnels (`*.trycloudflare.com`) **rejected**: ephemeral URL changes
  on every `cloudflared` restart, incompatible with cron 4×/day from Hetzner.
- ~$15/yr saved during Phase 0 (negligible, but cleaner: no domain = no
  half-configured zone).

## Alternatives considered

- **Buy `ichor.fyi` ($15.18) now** — rejected by Eliot 2026-05-02: he wants
  to revisit naming with fresh perspective at Phase 1.
- **Negotiate `ichor.app` buyout** — rejected: open-ended timeline + cost,
  blocks Phase 0 day 1.
- **Buy `getichor.com` ($10.46) now** — rejected: same as above; "get" prefix
  feels dated.

## References

- [`docs/ARCHITECTURE_FINALE.md`](../ARCHITECTURE_FINALE.md) line 98
- DNS lookups via `nslookup ichor.app 1.1.1.1` (2026-05-02)
- WHOIS via [who.is/whois/ichor.app](https://who.is/whois/ichor.app)
- HTTP probe `curl -L https://ichor.app` returned 200 with Lovable.dev project
