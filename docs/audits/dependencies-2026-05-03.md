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
3. **Our call site is vulnerable to alg confusion as written** — `auth.py:89-95` passes `algorithms=[header.get("alg", "RS256")]` to `jwt.decode`, which means the _allowlist_ is read from the token own header. An attacker who obtains the JWKS public key (it is public by design) can sign an HS256 token with that public key as the secret, set `alg: HS256` in the header, and bypass verification.

Mitigating context: tokens come from Cloudflare Access (CF signs them, we verify). For an external attacker, forging requires either (a) Cloudflare being broken or (b) bypassing CF Access entirely — in either case they own you anyway. So this is more "defence in depth + abandonware risk" than "hot fire". But the migration is cheap.

Migration:

- `pyjwt[crypto]>=2.10` is the standard drop-in. Same signature shape; same `jwt.decode(token, key, algorithms=[...], audience=...)`.
- Hardcode `algorithms=["RS256"]` (CF Access uses RS256; verify with one production token).
- Drop `python-jose[cryptography]` from deps.

Upstream references:

- CVE: https://www.sentinelone.com/vulnerability-database/cve-2024-33663/
- Maintenance status: https://github.com/fastapi/fastapi/discussions/11345

---

## HIGH severity

### Voie D violation: `pydantic-ai` meta-package pulls `anthropic` SDK

**Pinned at**: `packages/agents/pyproject.toml:7` -> `pydantic-ai>=1.88,<2`

Per ADR-009 ("Voie D — no API consumption"), the Anthropic SDK must not appear in the prod Python tree. The `pydantic-ai` umbrella package depends on `pydantic-ai-slim[anthropic]==<same version>`, so installing `pydantic-ai` brings `anthropic>=...` transitively as a hard dependency.

Source review confirms the agent code does not need the Anthropic provider:

- `packages/agents/src/ichor_agents/providers.py` only constructs `OpenAIModel` + `OpenAIProvider` pointed at Cerebras / Groq base URLs.
- `packages/agents/src/ichor_agents/fallback.py` imports `Agent`, `ModelHTTPError`, `UserError` — all in core slim package.

**Fix** (single-line change): replace the line `"pydantic-ai>=1.88,<2",` in the `dependencies = [...]` block with `"pydantic-ai-slim[openai]>=1.88,<2",` then `uv lock --upgrade` and verify `anthropic` is gone from the lockfile.

Note also the comment in `pyproject.toml` lines 12-14 saying anthropic is intentionally not in production. The comment is correct in _intent_ but currently misleading: `anthropic` IS being installed today, just via the meta-package. Fix the dep, then the comment is accurate again.

---

### Grafana 11.4.0 — high-severity 2025 CVEs patched in 11.4.x line

**Pinned at**: `infra/ansible/roles/observability/files/docker-compose.yml:32` -> `grafana/grafana:11.4.0`

- **CVE-2025-4123** (XSS, High) — affects 11.2 through 12.0.
- **CVE-2025-3260** (dashboard auth bypass on `/apis/dashboard.grafana.app/*`, High) — affects 11.4 through 11.6.
- **CVE-2025-6023 / CVE-2025-6197** (XSS / open redirect) — affects 11.4.x.

Fix: bump to `grafana/grafana:11.4.3` at minimum (or a current 11.x line). Pure patch bump, no schema migration.

Mitigating context: bound to `127.0.0.1:3001` and behind CF Access. XSS still matters once Eliot is logged in (CF Access does not strip request bodies).

Upstream: https://grafana.com/security/security-advisories/

---

### MinIO `RELEASE.2025-01-20` — IAM privilege escalation

**Pinned at**: `infra/ansible/roles/langfuse/files/docker-compose.yml:67` -> `minio/minio:RELEASE.2025-01-20T14-49-07Z`

- **CVE-2025-62506** — service account / STS session-policy bypass: the IAM check uses "DenyOnly" instead of "explicit allow", so a restricted service account can create an unrestricted child service account. Fixed in `RELEASE.2025-10-15T17-29-55Z`.
- **OIDC JWT algorithm confusion** (advisory date 2026-03-17) — only matters if you wire OpenID Connect on this MinIO instance, which you do not currently. Fix is `RELEASE.2026-03-17T21-25-16Z`.

For Ichor: this MinIO is purely Langfuse object storage, single root user, not federated. Risk is low because there is only one principal. Still worth bumping to current.

Upstream: https://github.com/minio/minio/security/advisories/GHSA-jjjj-jwhf-8rgr

---

### ClickHouse `24.12-alpine` floating tag — CVE-2025-1385 risk

**Pinned at**: `infra/ansible/roles/langfuse/files/docker-compose.yml:42` -> `clickhouse/clickhouse-server:24.12-alpine`

Issue is structural: the `24.12-alpine` tag is a moving pointer to "latest patch in 24.12 line". Two problems:

1. **Reproducibility**: a `docker compose pull` six months from now may yield a different image than today. Pin to a digest (`@sha256:...`) or to a full patch (`24.12.5.65-alpine`).
2. **CVE-2025-1385** (clickhouse-library-bridge RCE on localhost API): fixed minimum `24.12.5.65`. Floating `24.12-alpine` _might_ have pulled a pre-fix image when you first deployed.

Mitigating context: the bridge is a localhost-only HTTP API in the container, and there is no library file mounted into the container. Real exploitability is near-zero in this configuration. Still, pin the tag.

Upstream: https://github.com/ClickHouse/ClickHouse/security/advisories/GHSA-5phv-x8x4-83x5

---

### postcss <8.5.10 — XSS via unescaped style tag in CSS stringify

**Path**: `apps/web > next > postcss` (transitive). Reported by `pnpm audit`:

> postcss <8.5.10 — GHSA-qx2v-qp2m-jg93 (moderate)

- Severity: moderate per advisory, but `pnpm audit` flagged it without an explicit fix path because Next.js controls the postcss version transitively.
- Fix: bump Next.js to a current 15.5.x patch that ships postcss 8.5.10+ (one minor newer than current 15.5.15), OR add a `pnpm.overrides` block in root `package.json` mapping `postcss` to `>=8.5.10`. Test `pnpm build` after — postcss is at the heart of the Tailwind 4 oxide pipeline.

Advisory: https://github.com/advisories/GHSA-qx2v-qp2m-jg93

---

## MEDIUM severity

### Out-of-date majors (JS)

`pnpm outdated -r` output:

| Package               | Current  | Latest  | Major lag | Notes                                                                                                                                                            |
| --------------------- | -------- | ------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `next`                | 15.5.15  | 16.2.4  | 1 major   | App Router stable, but 16 changes RSC default behavior; defer until RSC story stabilises post-React2Shell ecosystem fallout.                                     |
| `typescript`          | 5.9.3    | 6.0.3   | 1 major   | TS 6 has breaking inference changes around narrowing; non-blocking but plan for it.                                                                              |
| `@types/node`         | 22.19.17 | 25.6.0  | 3 majors  | Tracks Node.js; you are on Node 22 LTS so 22.x is correct. Do not bump to 25.x while runtime is 22.                                                              |
| `eslint`              | 10.3.0   | 10.3.0  | none      | Pinned correct.                                                                                                                                                  |
| `turbo`               | 2.9.7    | 2.9.8   | patch     | Trivial.                                                                                                                                                         |
| `@types/react`        | 19.0.0   | 19.2.14 | minor     | Bump for newer React 19 type fixes.                                                                                                                              |
| `@types/react-dom`    | 19.0.0   | 19.2.3  | minor     | Same.                                                                                                                                                            |
| `react` / `react-dom` | 19.0.0   | 19.2.5  | minor     | Includes React 19 RSC patches CVE-2025-55183 / CVE-2025-55184 — though Next.js 15.5.15 already pulls patched react via its own resolution. Bump for consistency. |

**Recommended bump set** (low risk): `react@19.2.5`, `react-dom@19.2.5`, `@types/react@19.2.14`, `@types/react-dom@19.2.3`, `turbo@2.9.8`.

Defer for now:

- `next@16` — wait for Next.js 16.x ecosystem to settle; current 15.5.x pin is patched against the recent CVE cluster.
- `typescript@6` — minor productivity gain, real migration cost.
- `@types/node@25` — would mismatch the Node 22 LTS runtime.

### Out-of-date / risky Python deps

These were not checked with `pip-audit` (see Limitations) but are worth a manual look during the next maintenance window:

| Package                       | Where                | Concern                                                                                                                                                                                    |
| ----------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `numpy>=1.26.0,<2.0`          | `packages/ml`        | The `<2.0` cap is now obsolete and will block resolutions soon. All your other ML deps support NumPy 2. Lift the cap.                                                                      |
| `python-jose[cryptography]`   | `apps/claude-runner` | Already covered above (CRITICAL).                                                                                                                                                          |
| `vollib>=1.0.7`               | `packages/ml`        | The 1.0.7 series is the revival; older `py_vollib` is dead. Spec-only today (see grep). Re-evaluate when used.                                                                             |
| `dowhy>=0.12`, `econml>=0.15` | `packages/ml`        | Both alive but slow-moving causal-inference libs; verify before lifting from spec.                                                                                                         |
| `mlflow>=3.11.1`              | `packages/ml`        | MLflow 3.x has had a steady stream of CVEs around model-registry endpoints — make sure the tracking server is bound to localhost or behind CF Access (it should be by your usual pattern). |

---

## LOW severity / informational

### Licensing audit (JS)

Output of `pnpm licenses ls` analysed. Distribution:

- **MIT**: ~85% of the tree (Next.js, React, Tailwind, TanStack, react-markdown, remark-gfm, motion, zustand, lucide-react...)
- **Apache-2.0**: ESLint family, `@swc/helpers`, Tailwind plugin pieces, sharp, TypeScript itself, lightweight-charts.
- **ISC**: lucide-react, picocolors, semver, etc.
- **BSD-2-Clause / BSD-3-Clause**: ESLint internals (`espree`, `esquery`), `source-map-js`.
- **0BSD**: `tslib`.
- **BlueOak-1.0.0**: `minimatch` (permissive, OK).
- **CC-BY-4.0**: `caniuse-lite` data file (OK — data, not code).
- **MPL-2.0**: `lightningcss`, `lightningcss-win32-x64-msvc`. **File-level copyleft** — modifications to MPL-licensed source files must be redistributed under MPL, but linking is fine. Safe for closed-source consumption.
- **Apache-2.0 AND LGPL-3.0-or-later**: `@img/sharp-win32-x64`. The LGPL portion covers the libvips bindings on Windows — dynamic linking is fine, do not statically link sharp into a redistributed binary.

**Zero** GPL-2.0, GPL-3.0, AGPL-3.0, or SSPL packages found in the tree. The Voie D / private-commercial posture is preserved.

### Licensing audit (Python)

Not run programmatically (no `pip-licenses` or `licensecheck` available locally). Manual spot-check of the declared deps:

- **Permissive (MIT / BSD / Apache-2.0)**: fastapi, uvicorn, pydantic, sqlalchemy, asyncpg, alembic, redis-py, httpx, structlog, opentelemetry-\*, pytest, ruff, mypy, anyio, lightgbm, xgboost, scikit-learn, numpy, pandas, scipy, statsmodels, transformers, torch, mlflow, evidently, mapie, shap, **interpret** (MIT, recently-released 0.7.8 Mar 2026 — actively maintained).
- **Watch**:
  - `python-jose[cryptography]` -> MIT, but abandoned (covered above).
  - `dowhy`, `econml` -> MIT, slower-moving but maintained.
  - `vollib` -> MIT (1.0.7 revival), but `py_vollib` 0.x was BSD; clarify which version uv resolves.

### Bloat candidates

- **`claude-agent-sdk` in `packages/agents`** — declared, never imported. The Claude Code CLI is bundled with this package by upstream design, but you do not use the SDK at all (Voie D = subprocess to `claude -p`, done in `apps/claude-runner/src/ichor_claude_runner/subprocess_runner.py`). **Drop the dep.**
- **No JS bloat suspects** at first pass — every direct dep in `apps/web` (`react-markdown`, `remark-gfm`, `motion`, `lightweight-charts`, `zustand`, `@tanstack/react-query`) is actively used per the SPEC. Did not run dead-import analysis (would need `ts-prune` or `knip`).
- **`uvicorn[standard]`** in API + claude-runner — `standard` extras include `httptools`, `uvloop`, `watchfiles`, `python-dotenv`, `websockets`. If you do not use websockets in claude-runner (likely — it is a request/response JSON API), `uvicorn` (no extras) saves a few MB and a couple of native builds. Not worth touching today.

### Duplicates / version conflicts

- pnpm hoists fine — nothing pulls duplicate React or duplicate Next.js. Lockfile is clean (~85 KB, modest).
- No two-major-version coexistence in `node_modules/.pnpm` for any package I sampled.

### Abandonware check

- **`python-jose`** — confirmed abandoned (covered).
- **`py_vollib`** (NOT `vollib`) — abandoned since 2017; you are on the renamed-revival `vollib>=1.0.7` so this is OK _if_ uv resolves to the right project.
- **All other Python deps** I sampled (lightgbm, xgboost, transformers, torch, mlflow, sklearn, statsmodels, mapie, shap, interpret, river, hmmlearn, dtaidistance, dowhy, econml, evidently, numpyro, arch, pyextremes) have releases in the last 12 months per their respective registries.
- **JS deps** — Next.js, React, Tailwind 4, TanStack, lightweight-charts, motion, react-markdown, remark-gfm: all weekly to monthly cadence.

---

## Summary

| Metric                                        | Value                                                                                                               |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| JS direct deps (production)                   | 11 (across `apps/web` + `packages/ui`)                                                                              |
| JS direct deps (dev)                          | 8                                                                                                                   |
| JS transitive deps in lockfile                | ~110 (per `pnpm-lock.yaml` size)                                                                                    |
| Python direct deps (production, all packages) | ~45                                                                                                                 |
| Docker images pinned                          | 11 (across 3 compose files)                                                                                         |
| **Critical CVEs / abandonware**               | **2** (n8n, python-jose)                                                                                            |
| **High severity**                             | **5** (pydantic-ai/anthropic, Grafana, MinIO, ClickHouse, postcss)                                                  |
| **Medium**                                    | **3** (Next 15.5.15->.16+, NumPy cap, ML deps lacking pip-audit)                                                    |
| Out-of-date (JS, any lag)                     | 8                                                                                                                   |
| Licence conflicts                             | **0** GPL/AGPL/SSPL. 1 MPL (lightningcss, OK), 1 LGPL-component (sharp on win32, OK if not statically distributed). |
| Voie D / ADR-009 violations                   | **1** (`pydantic-ai` pulls `anthropic` transitively). Plus 1 dead dep (`claude-agent-sdk`).                         |

---

## Limitations (what was NOT checked)

- **`pip-audit` was not run.** No `uv` and no `pip-audit` in PATH; the repo `.venv-tooling/` does not have it either. Installing it would have been a network action that I declined to take without explicit ask. Python CVE coverage in this report relies on web-sourced advisories for the high-profile packages only — minor / less-common Python deps were not individually checked. Recommend running `uv tool install pip-audit` and then `pip-audit -r requirements.txt` per package once `uv` is on the box.
- **Dead-import analysis for JS** was not run (`knip` / `ts-prune`). Bloat assessment is by manifest review only.
- **Dead-import analysis for Python** was a manual `grep` only — confirms `claude-agent-sdk` is unused but does not catch deeper dead chains.
- **Docker base image scanning** (Trivy / Grype) was not run. Only the headline CVEs for the _application_ images were checked, not the base layers (Alpine, Debian, etc.). The Langfuse v3.162 issue thread (GHSA scan results) is a useful template if you want to wire Trivy into CI later.
- **Bundlephobia / actual bundle-size impact** of `react-markdown` + `remark-gfm` not measured. Both are reasonable, around 50 KB gzipped each, but if you only use markdown in one route, dynamic-import them.
- **Tooling versions used**:
  - `pnpm` (via corepack) 10.33.2
  - `node` 24.15.0 (note: project pins `node>=22.11.0`; corepack resolved fine)
  - No `uv`, no `pip-audit`, no `safety`, no `Trivy`.
