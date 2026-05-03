# Dependency audit — Ichor monorepo

**Date**: 2026-05-03
**Auditor**: automated dep-audit pass (Claude Code)
**Scope**: pnpm workspaces (`apps/web`, `packages/ui`), Python workspaces (`apps/api`, `apps/claude-runner`, `packages/agents`, `packages/ml`, `packages/shared-types`), Docker images pinned in `infra/ansible/roles/{observability,langfuse,n8n}/files/docker-compose.yml`.
**Mode**: static review of manifests + lockfile + live `pnpm audit` / `pnpm outdated` / `pnpm licenses ls`. Python advisory data sourced from PyPI advisory feeds via web (no `pip-audit` available locally — see Limitations).

---

## Action items (punch list)

Ordered by blast radius first, fix urgency second.

1. **[CRITICAL] Bump n8n** `1.78.1 -> 1.123.27` (or current stable in 1.x line). Fixes CVE-2026-33660 (RCE via Merge-Node AlaSQL, CVSS 9.4) and at least 5 other 2026 advisories. `infra/ansible/roles/n8n/files/docker-compose.yml`.
2. **[CRITICAL] Migrate off `python-jose`** in `apps/claude-runner` to `pyjwt>=2.10` (or `joserfc`). Library is abandoned; CVE-2024-33663 (algorithm confusion) is unfixed upstream. **Also fix the call site**: `auth.py:92` uses `algorithms=[header.get("alg", "RS256")]` which trusts the token own `alg` header — this is the exact pattern the CVE exploits. Hardcode `algorithms=["RS256"]`.
3. **[HIGH] Voie D / ADR-009 violation**: `packages/agents` declares `pydantic-ai>=1.88,<2`. The full `pydantic-ai` meta-package transitively pulls `anthropic` SDK via `pydantic-ai-slim[anthropic]`. Replace with `pydantic-ai-slim[openai]` (Cerebras + Groq are OpenAI-compat anyway — see `providers.py`).
4. **[HIGH] Bump Grafana** `11.4.0 -> 11.4.3+`. Fixes CVE-2025-4123 (XSS, High) and CVE-2025-3260 (auth bypass on dashboard APIs, High).
5. **[HIGH] Bump MinIO** `RELEASE.2025-01-20T14-49-07Z -> RELEASE.2025-10-15T17-29-55Z` (or newer). Fixes CVE-2025-62506 (IAM privilege escalation). If you ever wire OIDC, also need `RELEASE.2026-03-17T21-25-16Z+` for the JWT alg confusion fix.
6. **[HIGH] Pin ClickHouse to a fixed patch** `24.12-alpine -> 24.12.5.65-alpine` (or newer 25.x). Floating `24.12-alpine` is reproducibility-poor and may have pulled a pre-fix image relative to CVE-2025-1385 (RCE in library-bridge).
7. **[HIGH] Postcss bump** in `apps/web` (transitive via Next.js): `<8.5.10 -> >=8.5.10` (GHSA-qx2v-qp2m-jg93, moderate XSS). Easiest path: `pnpm update next --latest` to a 15.5.x patch above 15.5.16, or override via `pnpm.overrides`.
8. **[MEDIUM] Bump Next.js** `15.5.15 -> 15.5.16+` if available. Current pin is above the React2Shell cluster fix (15.5.9), so not vulnerable to CVE-2025-55182, but stay current for the postcss issue and any new patches.
9. **[MEDIUM] Loosen NumPy cap** in `packages/ml/pyproject.toml`: drop `<2.0` — every pinned dep here supports NumPy 2.x at the versions you require (lightgbm >=4.4, xgboost >=2.1, sklearn >=1.5, torch >=2.5, transformers >=4.46). The cap will eventually create unsolvable resolutions.
10. **[MEDIUM] Drop `claude-agent-sdk`** from `packages/agents/pyproject.toml`. Dead dependency — grep on `packages/agents/src` returns nothing. The runtime path is `claude-runner` shelling out to the Claude Code CLI (subprocess), not this SDK.
11. **[LOW] Replace `vollib`** in `packages/ml/pyproject.toml` if you ever lift it from spec into code. The 1.0.7 revival exists, but `py_vollib` proper has had no release since 2017. Consider `fast-vollib` (2026, drop-in API).
12. **[LOW] License notes (informational)**: `@img/sharp-win32-x64` declares `Apache-2.0 AND LGPL-3.0-or-later`; `lightningcss` is `MPL-2.0`. Both are dynamic-link-friendly copyleft — not a problem for a private commercial-style project that does not distribute binaries, but flag for legal if Ichor ever ships a binary.

No action needed but worth knowing:

- No GPL, AGPL, or SSPL dependency in the JS tree (lockfile checked — see Licensing section).
- Redis self-hosted via `redis:7-alpine` (Langfuse stack) is still under BSD-3 (Redis 7 line). Redis 8.0 (May 2025) moved to AGPLv3/SSPL/RSALv2 tri-license — not relevant unless you upgrade.


---

## CRITICAL severity

### n8n 1.78.1 — multiple 2026 RCE / auth-bypass CVEs

**Pinned at**: `infra/ansible/roles/n8n/files/docker-compose.yml:5` -> `docker.n8n.io/n8nio/n8n:1.78.1`

Confirmed exposure to **CVE-2026-33660** (Merge-Node AlaSQL RCE, CVSS 9.4):

- Affected: all versions before 1.123.27. Current pin (1.78.1) is well within the affected range.
- Vector: authenticated user creates a workflow using "Combine by SQL" mode in the Merge node -> reads local files / RCE.
- Stop-gap mitigation: add `n8n-nodes-base.merge` to `NODES_EXCLUDE` env var (no Merge nodes in current workflows? then trivially safe to disable).
- Fix: bump to **1.123.27** (last 1.x patch) or 2.13.3+ / 2.14.1+ on the 2.x track.

Likely also exposed (need version-by-version check post-bump) to the April 2026 cluster:

- GHSA-hqr4-h3xv-9m3r — XML prototype-pollution -> RCE (Critical)
- GHSA-q5f4-99jv-pgg5 — XML webhook body parser pollution (Critical)
- GHSA-537j-gqpc-p7fq — XSS via MCP OAuth client (High)
- GHSA-r4v6-9fqc-w5jr — credential authorization bypass (High)
- GHSA-49m9-pgww-9vq6 — DoS via MCP (High)

Mitigating context for Ichor specifically: n8n is bound to `127.0.0.1:5678` and fronted by Cloudflare Access (per the compose env `N8N_BASIC_AUTH_ACTIVE=false  # auth handled by Cloudflare Access upstream`). That cuts the realistic attack surface to anyone who can pass CF Access — which today is just Eliot email — but the CVE chain still applies once an authenticated session exists, and n8n workflows themselves can call arbitrary nodes.

Upstream advisory: https://github.com/n8n-io/n8n/security/advisories/GHSA-58qr-rcgv-642v

---

### python-jose abandoned + CVE-2024-33663 + insecure call pattern in our code

**Pinned at**: `apps/claude-runner/pyproject.toml:14` -> `python-jose[cryptography]>=3.3.0`
**Used in**: `apps/claude-runner/src/ichor_claude_runner/auth.py:18-19`

Three-layer problem:

1. **Library is abandoned.** Last release 3.5.0 (mid-2024), repo issues stacking up. FastAPI itself dropped its python-jose recommendation in favour of PyJWT.
2. **CVE-2024-33663** (algorithm confusion via OpenSSH ECDSA / non-PEM-prefixed public keys) is unpatched upstream — the `invalid_strings` blacklist in `cryptography_backend.py` is incomplete and any key format that does not match a known prefix slips through.
3. **Our call site is vulnerable to alg confusion as written** — `auth.py:89-95` passes `algorithms=[header.get("alg", "RS256")]` to `jwt.decode`, which means the *allowlist* is read from the token own header. An attacker who obtains the JWKS public key (it is public by design) can sign an HS256 token with that public key as the secret, set `alg: HS256` in the header, and bypass verification.

Mitigating context: tokens come from Cloudflare Access (CF signs them, we verify). For an external attacker, forging requires either (a) Cloudflare being broken or (b) bypassing CF Access entirely — in either case they own you anyway. So this is more "defence in depth + abandonware risk" than "hot fire". But the migration is cheap.

Migration:

- `pyjwt[crypto]>=2.10` is the standard drop-in. Same signature shape; same `jwt.decode(token, key, algorithms=[...], audience=...)`.
- Hardcode `algorithms=["RS256"]` (CF Access uses RS256; verify with one production token).
- Drop `python-jose[cryptography]` from deps.

Upstream references:

- CVE: https://www.sentinelone.com/vulnerability-database/cve-2024-33663/
- Maintenance status: https://github.com/fastapi/fastapi/discussions/11345

