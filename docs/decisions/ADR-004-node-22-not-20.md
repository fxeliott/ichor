# ADR-004: Use Node 22 LTS instead of plan's Node 20

- **Status**: Accepted
- **Date**: 2026-05-02
- **Decider**: Eliot (autonomy delegation)

## Context

`docs/ARCHITECTURE_FINALE.md` line 133 lists `Node 20 + pnpm` for the Hetzner
Ansible playbook step 4.

Verified on 2026-05-02:

- **Node.js 20 LTS active support ends April 2026** — already past EOL window
  for active support; only critical security patches until April 2028.
- **Node.js 22 LTS** is the active LTS, supported until **April 2027**
  (active) and April 2029 (maintenance).
- **Node.js 24** released October 2025, became LTS October 2025 — even fresher.

Source: [Node.js release schedule](https://nodejs.org/en/about/previous-releases).

## Decision

Pin **Node 22 LTS** for all Ichor environments:

- `.nvmrc` → `22`
- `package.json` engines → `"node": ">=22.11.0"`
- `infra/ansible/group_vars/all.yml` → `node_major_version: "22"`
- `apps/web/package.json` peer types → `@types/node@22.x`
- GitHub Actions runner → `actions/setup-node@v4` with `node-version: 22`
- NodeSource apt repo URL → `https://deb.nodesource.com/node_22.x`

Rejected Node 24 even though newer:

- ML/data tooling JS bindings (puppeteer, playwright) sometimes lag major Node
  releases by 3-6 months
- 22 is "boring stable" — the right pick for a 2026 production codebase

## Consequences

- Local Win11 currently has Node 24.15 — fine for tooling (Turbo, prettier,
  eslint). Apps are built/tested in CI on Node 22 (matches production).
- Eliot can keep his Node 24 local; no need to downgrade.
- When Node 22 enters maintenance (April 2027), open new ADR to migrate to
  Node 24 LTS.

## Alternatives considered

- **Node 20** (per plan) — rejected: ended active support April 2026.
- **Node 24** (current) — rejected: too fresh for 2026 production stability;
  some ML/data tooling lags major Node bumps.

## References

- [Node.js Release Schedule](https://nodejs.org/en/about/previous-releases)
- `docs/ARCHITECTURE_FINALE.md` line 133
