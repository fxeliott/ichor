# SESSION_LOG 2026-05-16 — Round 73 (ADR-099 Tier 0.1: deploy /briefing)

> Round type: **production deploy** (additive, reversible). Branch
> `claude/friendly-fermi-2fff71`. ZERO Anthropic API spend. Voie D + ADR-017 held.
> Trigger: Eliot "continue" → ADR-099 D-3 Tier 0.1.

## What r73 did

Deployed the `apps/web2` `/briefing` dashboard to Hetzner — the audit's #1 gap
(it was deployed nowhere; Hetzner served only the frozen legacy `@ichor/web`).

- New artifact `scripts/hetzner/redeploy-web2.sh` — idempotent, self-verifying,
  rollback-able deploy script in the `redeploy-brain.sh` house pattern. Pure bash
  (Voie D). tar-over-ssh push (rsync absent from Win11 Git-Bash; server-side
  Step 1b still rsyncs). Embeds the two systemd units.
- **Additive, legacy untouched**: new `ichor-web2.service` (port **3031**,
  `ICHOR_API_URL=http://127.0.0.1:8000` per `api.ts:9`,
  `ICHOR_API_PROXY_TARGET=http://127.0.0.1:8000` per `next.config.ts:88`) +
  `ichor-web2-tunnel.service` (cloudflared quick tunnel → :3031). The legacy
  `ichor-web` (3030) + `ichor-api` were never modified.

## Empirical witnesses (R59 — "marche exactement", not just 200)

- Build OK on Hetzner (node v22.22.2, pnpm via corepack); `next build` produced
  `.next` + `node_modules/next/dist/bin/next` (script asserts both, fails loud).
- `curl localhost:3031/briefing` = **200**; public = **200**.
- **Public URL: `https://automobile-appearance-travelling-zum.trycloudflare.com/briefing`**
- `/briefing` HTML (61 671 B): all 5 assets (EUR/USD, GBP/USD, XAU/USD, S&P 500,
  Nasdaq) present; **zero API-offline / empty-state markers**; live synthesis
  vocabulary rendered (HAUSSIER / NEUTRE / conviction / biais / régime) →
  `verdict.ts` is consuming **real API data**, not the mock fallback.
- `/briefing/EUR_USD` deep-dive (140 272 B): conviction + scénario + invalidation
  - catalyseur rendered.
- `systemctl is-active`: ichor-api / ichor-web / ichor-web2 / ichor-web2-tunnel
  all **active**; API `/healthz` = 200. Legacy untouched (regression-free).

## KNOWN CAVEAT (honest disclosure, documented in the script)

The cloudflared **quick tunnel mints a NEW random `*.trycloudflare.com` URL on
every (re)start** of `ichor-web2-tunnel`. `/briefing` is REACHABLE now (Tier 0.1
goal met: Eliot can SEE it), but the URL is **not durable** across restarts/reboot.
A stable hostname is **ADR-099 Tier 0.2** (CF Pages secret OR a named cloudflared
tunnel — both Eliot-gated). This trade-off was the explicit Tier 0.1 scope.

## Rollback

`./scripts/hetzner/redeploy-web2.sh rollback` — stop+disable+rm both units,
daemon-reload (<30 s). Legacy `ichor-web` unaffected. `web2-deploy` dir left
(re-deploy is `--skip-build` fast).

## Next stage (on Eliot "continue")

ADR-099 **Tier 0.2** — prepare externally-gated runbooks (the 36-commit PR;
stable URL options: CF Pages `CLOUDFLARE_API_TOKEN`/`ACCOUNT_ID` GH secret OR
named tunnel; `ICHOR_CI_FRED_API_KEY`; rotate the FRED+CF creds leaked in
journald; PAT revoke) — Claude prepares to one-command + step-by-step; Eliot
performs the final irreversible gesture. Then Tier 1 (vision-coverage panels).

## Checkpoint

Commit: `redeploy-web2.sh` + this SESSION_LOG on `claude/friendly-fermi-2fff71`.
The deployed artifact lives on Hetzner (scp/tar-deploy, like the backend — not
in git). Memory pickup updated separately.
