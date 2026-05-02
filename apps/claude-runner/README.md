# `apps/claude-runner` — Local Win11 Claude Code subprocess wrapper

Runs on Eliot's Windows 11 desktop, never on Hetzner.

Exposes a FastAPI on `:8765` accessible only via Cloudflare Tunnel
(`<TUNNEL-UUID>.cfargotunnel.com`) protected by Cloudflare Access service-token
gating Hetzner outbound calls.

## Why a local subprocess wrapper?

Anthropic Max 20x ($200/mo flat) is meant for individual developer use of
Claude Code. To run automation jobs that consume Max 20x quota without using a
paid API key, we invoke `claude -p --output-format json` as a subprocess from
Eliot's locally-authenticated Claude Code installation.

Hetzner's cron triggers a webhook to this local FastAPI 4× per day at 06h/12h/
17h/22h Paris (briefing windows). Latency budget: 3-6 min per briefing.

## Risks accepted (documented in `docs/ARCHITECTURE_FINALE.md`)

- Anthropic may detect automation patterns and ban the Max 20x account.
  → Fallback chain: Cerebras free → Groq free → static template.
- Local PC sleep / Windows update / power outage.
  → Power Plan never sleep + gpedit Windows Update window 04-05h Paris.

## Phase 0 status

🚧 Skeleton only. Real subprocess invocation in Phase 0 Week 3 (steps 18-23).
