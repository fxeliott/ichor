# SPEC v2 — Sécurité, tests, déploiement, documentation produit

**Date** : 2026-05-04
**Compagnon de** : `D:\Ichor\SPEC.md` (Phase 2 Ichor)
**Source** : recherche READ-ONLY web 2026 (Next.js 15, FastAPI, OWASP, Hypothesis, Playwright, k6, blue-green systemd, PostHog flags, Alembic zero-downtime, Changesets, Storybook 8, syft+grype)

## 1. Sécurité Next.js 15 + FastAPI hardening

### 1.1 CSP headers

État actuel : `D:\Ichor\apps\web\next.config.ts:1-23` ne contient **aucun header CSP** (seul `poweredByHeader: false`). Aucun `middleware.ts` n'existe.

**Pattern recommandé 2026** : middleware nonce-based + `strict-dynamic`. Directive minimale :

```
default-src 'self'; script-src 'self' 'nonce-{N}' 'strict-dynamic';
style-src 'self' 'nonce-{N}'; img-src 'self' blob: data:;
font-src 'self'; connect-src 'self' https://*.cfargotunnel.com wss://*.pages.dev;
object-src 'none'; base-uri 'self'; form-action 'self';
frame-ancestors 'none'; upgrade-insecure-requests;
report-to csp-endpoint;
```

**Tradeoff critique** : nonce force `dynamic = 'force-dynamic'`, casse PPR/ISR/edge-cache. Pour Ichor (single-user, pas de SEO public), acceptable. **Démarrer en `Content-Security-Policy-Report-Only` 1 semaine, puis enforcement**.

### 1.2 Cookies + HSTS + SRI

- Préfixe `__Host-` obligatoire (`Secure; SameSite=Strict; Path=/; HttpOnly`)
- HSTS : `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
- SRI : non-applicable (Ichor n'a pas d'asset CDN externe d'après `next.config.ts`)
- À ajouter dans `next.config.ts` via clé `headers()`

### 1.3 Rate limiting FastAPI

Aucun rate-limit dans `apps/api` (grep `slowapi|RateLimit` = 0 hit hors `apps/claude-runner`). Le runner a un `HourlyRateLimiter` in-memory (`apps/claude-runner/src/ichor_claude_runner/rate_limiter.py:16-46`) — non distribué, pas adapté à FastAPI Hetzner.

**Choix recommandé** : **slowapi + backend Redis** (`redis_url` déjà en config). Pattern décorateur `@limiter.limit("60/minute")` + `Retry-After` automatique. Custom Lua token-bucket = sur-ingénierie pour single-user. Garder le `HourlyRateLimiter` côté runner (cap Max 20x).

### 1.4 JWT JWKS verification

`apps/claude-runner/.../auth.py:79-101` est correct :

- `algorithms=["RS256"]` épinglé
- `audience` + `issuer` validés
- `require_exp/iat`
- JWKS cache 1h (`_JWKS_TTL_SEC = 3600`)

**Manque** : pas de `require_nbf`, pas de retry sur 401 après JWKS rotation. **À durcir** : si décodage échoue, invalider cache et re-fetch une fois (gestion key-rollover Cloudflare).

### 1.5 Audit logs

**Aucun audit log** (grep `audit_log|AuditLog` = 0 hit). À créer migration `0014_audit_log.py` :

```sql
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor TEXT NOT NULL,    -- email CF Access ou 'system'
  action TEXT NOT NULL,   -- 'briefing.published', 'meta_prompt.pr_created'
  resource TEXT,          -- briefing_id, card_id
  request_id UUID,
  ip INET,
  metadata JSONB
);
CREATE INDEX ON audit_log (ts DESC);
CREATE INDEX ON audit_log (actor, ts DESC);
```

**Rétention 365j** (purge nightly). Logger via dependency FastAPI sur tous les `POST/DELETE`.

### 1.6 Prompt injection pipeline

`RUNBOOK-006` suggère `injection_filter.py` + Critic Cerebras — pas implémenté. Stack 2026 conseillée (OWASP, PromptGuard) :

1. **Layer 1 regex/normalize** : décodage Base64/Unicode, lowercase, blocklist `ignore previous|disregard system|reveal hidden|<\|im_start\|>` (catch ~90 % attaques basiques, latence <1ms).
2. **Layer 2 length + URL whitelist par source** (Reddit user-content = haute risque, RSS Reuters = basse).
3. **Layer 3 LLM-as-judge** Haiku 4.5 (cheap) sur sources haute-risque uniquement (Reddit + scrape) : prompt structuré "respond 1 if violates intent, else 0". Coût : ~$0/mois via Max 20x quota.
4. **Layer 4 output validation** : regex sur briefing markdown avant `status='completed'` (URLs externes hors whitelist, persona drift).

**À créer** : `apps/api/src/ichor_api/safety/injection_filter.py` + tests Hypothesis (homoglyphes, encoding bypasses).

### 1.7 Secrets rotation

Stack actuelle SOPS+age. **Cadence proposée** :

- age master key : **12 mois**
- SOPS-encrypted env (anthropic, polygon, cerebras, groq, vapid) : **90j**
- `HETZNER_SSH_PRIVATE_KEY` GitHub secret : **60j** (recommandation 2026 ED25519)

**Procédure** : `sops updatekeys` après rotation age, `sops -r infra/secrets/*.env` pour ré-encrypt. À ajouter `RUNBOOK-014-secrets-rotation.md`.

## 2. Tests state-of-art 2026

### 2.1 Property-based testing (Hypothesis) — 10 propriétés Ichor

1. `confluence_weights_optimizer` : `sum(weights) ≈ 1.0 ± 0.01` ∀ input ∈ [0.05, 0.5]
2. `brier_score` : ∈ [0, 1] ∀ (pred, outcome) ∈ [0,1]²
3. `divergence` : symétrique `f(a,b) = f(b,a)`
4. `regime_classifier` HMM : `sum(posteriors) ≈ 1.0`
5. `rr_analysis` : si entry < SL, alors `pips_risk > 0`
6. `hourly_volatility` : `RV ≥ 0`
7. `polymarket_impact` : `strength ∈ [0, 1]`
8. `narrative_tracker` TF normalized : `sum ≈ 1`
9. `correlations` Pearson : ∈ [-1, 1]
10. Sanitization : `injection_filter(safe_input) == safe_input` (idempotence)

### 2.2 Snapshot testing UI

Vitest snapshots prioritaires :

- `<SessionCard>`, `<RegimeQuadrant>`, `<TradeplanPanel>`, `<AlertBadge>`, `<ConvictionMeter>`
- `<TimeMachineSlider>`, `<KnowledgeGraph>`, `<PolymarketImpactRow>`, `<AmbientOrbs>`, `<MobileBlocker>`

Stocker baselines dans `apps/web2/__snapshots__/`.

### 2.3 Visual regression

**Choix budget $0** : **Playwright `toHaveScreenshot()` sur GitHub Actions ubuntu-24.04** (guide 2026). Baselines committées, runner Linux only évite OS-rendering issue.

**Chromatic free tier** (5k snapshots/mo) reste viable si Storybook devient central — réserver pour Phase A semaine 6+.

**Cadence** : sur chaque PR + nightly main.

### 2.4 Load testing — k6

**k6 préféré** pour Ichor single-user (k6 vs Locust 2026) : single-machine efficace, JS scripts, intégration GHA simple.

**Scénarios** :

1. 10 RPS sur `/v1/sessions/EUR_USD` 5 min
2. WebSocket 1 client + 1k events/min
3. `/v1/counterfactual` burst x3 (limite latence p99 < 30s, modèle Pass 5)
4. `/v1/data_pool/build` warm cache

### 2.5 Contract testing OpenAPI

FastAPI génère `/openapi.json` natif. Utiliser **schemathesis** (Hypothesis-backed) sur `/v1/*` :

```bash
schemathesis run http://api/openapi.json --checks all
```

Couvre statuses, schémas response, headers. Génère `apps/web2/lib/api-client/` via `orval`.

### 2.6 E2E Playwright — 10 happy paths

1. Matin Eliot pré-Londres (login → /today → drill EUR/USD)
2. Counterfactual Pass 5 trigger + result rendering
3. Time-machine slider 7j replay
4. Crisis Mode UI flip (mock VIX +30 %)
5. Alert push subscription accept + receive
6. Glossary `/learn/glossary` search
7. Walkthrough first-time skip-able
8. Knowledge Graph drill node
9. Polymarket whales filter > $50k
10. Mobile drawer + MobileBlocker on drill-down

POM (Page Object Model) sous `apps/web2/tests/e2e/pages/`, fixtures auth CF Access mockée.

### 2.7 Couverture cible

- Services Python > **70 %**
- Routers FastAPI > **60 %**
- UI components > **40 %**
- Agents Couche-2 > **65 %**

Tests routers HTTP **manquent** (28 fichiers tests parsers seulement dans `apps/api/tests/`).

## 3. Déploiement durci

### 3.1 Blue-green Hetzner systemd

**Pattern recommandé 2026** : units templated `ichor-api@blue.service` (port 8001) + `ichor-api@green.service` (port 8002), nginx upstream avec map cookie + symlink swap :

```nginx
upstream app {
  server 127.0.0.1:8001 max_fails=1 fail_timeout=5s;
  server 127.0.0.1:8002 backup;
}
```

**Script deploy** :

1. `systemctl start ichor-api@green`
2. curl `:8002/readyz` jusqu'à 200 (timeout 60s)
3. `ln -sf upstream-green.conf upstream-active.conf && nginx -s reload`
4. sleep 30s drain
5. `systemctl stop ichor-api@blue`

**Coût** : 2× RAM le temps de la bascule (~600MB Hetzner).

### 3.2 Feature flags

**PostHog feature flags free tier 1M req/mo** — largement suffisant single-user (~80 calls Claude/jour ≈ 2.4k/mo).

**Alternative custom** : table `feature_flags(key TEXT, enabled BOOL, rollout_pct INT)` + cache Redis 60s.

**Recommandation** : **custom DB** pour Phase 2 (zero dep externe, contrôle total, simplicité). PostHog si volume utilisateur multi-tenant Phase 3.

### 3.3 Canary releases

Single-user → canary inutile au sens classique. Pattern adapté :

- **Shadow mode** sur background jobs (run nouveau modèle ML en parallèle, ne sert pas, log différence)
- Pour le frontend, déployer `apps/web2` sur `next.app-ichor.pages.dev` (preview deployment Cloudflare illimités) avant promotion sur `app-ichor.pages.dev`

### 3.4 Health probes

État actuel : `apps/api/.../main.py:122-165` a `/healthz` (Postgres+Redis ping) et `/healthz/detailed`.

**Pattern 2026 recommandé** :

- `/livez` : process alive only (return `{"alive": true}`, pas de DB)
- `/readyz` : DB + Redis + claude-runner reachable + migrations à jour (`alembic current == head`)
- `/startupz` : pgvector index loaded, embeddings warm

**Renommer `/healthz` actuel en `/readyz`, créer `/livez` minimal**.

### 3.5 Auto-rollback

**Trigger** : Prometheus alert `ichor_api_5xx_rate > 5% over 2min` OR `ichor_api_p99_latency > 10s over 5min` → script `rollback.sh` qui re-symlinke `upstream-active.conf → blue` et restart blue.

Nécessite : Prometheus alertmanager webhook → script local. Rétention old service : 24h avant `systemctl disable`.

### 3.6 GitHub Actions auto-deploy — pattern sécurisé

État actuel `.github/workflows/deploy.yml:1-79` utilise `HETZNER_SSH_PRIVATE_KEY` long-lived (non configuré actuellement).

**Pattern durci 2026** :

- Migrer vers **ED25519** + rotation 60j
- Utiliser `webfactory/ssh-agent@v0.9.1` (auto-cleanup) au lieu d'écriture manuelle
- GitHub environment `production` avec **required reviewer Eliot**
- OIDC vers Hetzner : **non disponible nativement** — rester sur SSH key
- Restreindre la clé à `command="rsync ..."` dans `~/.ssh/authorized_keys` côté Hetzner

### 3.7 Zero-downtime Alembic migrations

**Pattern obligatoire 2026** :

- `transaction_per_migration=True` dans `migrations/env.py`
- `op.execute("SET lock_timeout = '4s'; SET statement_timeout = '30s'")` en début de chaque `upgrade()`
- Index : `op.create_index(..., postgresql_concurrently=True)` + flag `is_transactional=False`
- **Expand-Migrate-Contract** pour rename/drop : 3 migrations distinctes, déploiements séparés
- Lint **Squawk** en CI sur `migrations/versions/*.py`
- Migration runner dédié (pas dans `ExecStartPre` API) : `systemd oneshot` avant blue-green start
- `alembic check` en CI pour détecter modèles non-migrés

## 4. Documentation produit

### 4.1 CHANGELOG

**Changesets recommandé** car repo pnpm + monorepo (apps/api Python aussi mais Changesets gère polyglot via `ignore`). pnpm lui-même utilise Changesets.

**Workflow** :

1. `pnpm changeset` côté dev → fichier `.changeset/*.md` committé
2. CI `changeset version` génère CHANGELOG.md + bump versions
3. PR auto

Release-please viable si full conventional commits, mais Changesets force qualité humaine de chaque description.

### 4.2 API reference

FastAPI génère `/docs` (Swagger) + `/redoc` natifs.

**Recommandation** : exposer `/redoc` (lecture) en read-only via CF Access, `/docs` désactivé en prod (`docs_url=None`).

Dump OpenAPI nightly → `apps/web2/lib/api-client/` via orval (typage TS auto).

### 4.3 Storybook 8 layout

Structure `apps/web2/.storybook/` :

- `preview.tsx` initialise MSW global + handler factories typés depuis `lib/api-client`
- Hierarchy stories : `Atoms/`, `Molecules/`, `Organisms/`, `Pages/`
- Layout par défaut `padded`, `centered` pour atoms, `fullscreen` pour pages

**Addons obligatoires** : `@storybook/addon-a11y`, `msw-storybook-addon`, `@storybook/addon-interactions`.

### 4.4 Design system docs

Page `/docs/design-system/` dans `web2` (hors Storybook) :

- Tokens (couleurs cobalt+navy+ambre §3.4 SPEC.md)
- Typographie Inter+JetBrains
- Motion principles "vivant utile"
- Do/don't visuels

**Storybook = composants ; cette page = principes**.

### 4.5 ADR

Template existant `docs/decisions/ADR-001-stack-versions-2026-05-02.md` à conserver.

**Cadence** : ADR par décision irréversible (choix lib, archi). Numérotation séquentielle.

**Frontmatter** : `status: proposed|accepted|superseded`, `date`, `supersedes`.

**Phase 2 livrés 2026-05-04** (renumérotés 018-021 pour éviter collision avec ADRs 008-011 déjà Accepted depuis 2026-05-02) : [ADR-018 frontend rebuild Phase 2](decisions/ADR-018-frontend-rebuild-phase-2.md), [ADR-019 pgvector HNSW](decisions/ADR-019-pgvector-hnsw-not-ivfflat.md), [ADR-020 RAG embeddings BGE-small](decisions/ADR-020-rag-embeddings-bge-small.md), [ADR-021 Couche-2 via Claude](decisions/ADR-021-couche2-via-claude-not-fallback.md).

### 4.6 Runbooks

Template existant `docs/runbooks/README.md:29-58` correct (Severity / Trigger / Immediate / Diagnosis / Recovery / Post-incident).

**Ajouts Phase 2** :

- RUNBOOK-012 CF tunnel down (déjà annoncé SPEC §5 phase D)
- RUNBOOK-013 Max quota saturé
- RUNBOOK-014 secrets rotation
- RUNBOOK-015 prompt injection sur Reddit/scrape (différent de 006 qui couvre output Claude)

## 5. CI/CD strict

### 5.1 Cache

État actuel `.github/workflows/ci.yml:42-51` : pnpm store cache OK.

**Manque** :

- `actions/cache` pour `~/.cache/uv` (Python). `setup-uv@v4` ligne 97 a `enable-cache: true` — bon
- Docker layer cache si Phase 2 introduit images
- Cache Playwright browsers (`~/.cache/ms-playwright`) à ajouter

### 5.2 Required checks main

**Cible S4** (SPEC §3.10) :

- `node` matrix
- `python` matrix (5 packages)
- `ansible`
- **`pip-audit`** (strict)
- **`pnpm audit --audit-level=high`** (strict)
- **`trivy fs`** (CRITICAL,HIGH fail)
- **`schemathesis`**
- **`playwright e2e`**
- **`alembic check`**
- **`squawk migrations/`**

Aujourd'hui tout en `|| true` / `continue-on-error` (`ci.yml:59-157`, `audit.yml:53,76,91`) — passer en strict semaine 4.

### 5.3 Dependabot auto-merge

**Pattern safe** : auto-merge **patch** uniquement (`semver-patch`) si **CI vert + 24h cool-down**.

Workflow `dependabot-auto-merge.yml` :

```yaml
- if: github.event.pull_request.user.login == 'dependabot[bot]'
- if: update_type == 'version-update:semver-patch'
```

Minor/major restent manuels.

### 5.4 SBOM + CVE scan

**syft + grype** via `anchore/sbom-action@v0`.

Workflow :

```bash
syft . -o cyclonedx-json=sbom.json
grype sbom:sbom.json --fail-on high
```

Upload SBOM en release asset auto. Trivy reste utile en parallèle (`audit.yml:78-100`) mais éval risque supply-chain.

### 5.5 Concurrence + parallelism

`concurrency: group: ci-${{ github.ref }} cancel-in-progress: true` déjà OK.

Python matrix `fail-fast: false` à conserver. Playwright : `--workers=4` sur GHA ubuntu-24.04 (4 vCPU).

## 6. Backup + DR Phase 2

### 6.1 pgvector backup

wal-g 3.0.8 capture déjà cluster entier (extension + index ivfflat inclus).

**Validation** : ajouter test `RUNBOOK-010` post-restore :

- `SELECT count(*) FROM pg_extension WHERE extname='vector'` doit retourner 1
- `SELECT * FROM rag_chunks_index LIMIT 1` doit fonctionner

**Risque** : index ivfflat doit être `REINDEX` après restore (centroïdes calculés sur snapshot). HNSW pas de centroïdes — si on passe à HNSW comme recommandé, pas de souci. Documenter dans RUNBOOK-003.

### 6.2 PWA user data

Push subscriptions stockées DB → backup wal-g couvre.

localStorage settings UI = perte acceptable single-user, OU sync via endpoint `POST /v1/user/settings` côté Eliot. Restore = re-login + re-subscribe push (UX 1 clic).

### 6.3 DR drill cadence

Trimestriel confirmé (SPEC §5 Phase D). RUNBOOK-010 existe.

**Ajouter checklist post-Phase 2** :

- pgvector REINDEX (si ivfflat) ou no-op (si HNSW)
- RAG smoke test (top-5 retrieval)
- Couche-2 restart cycle

## 7. Nouveaux fichiers à créer

| Path                                                     | Rôle (1 ligne)                                |
| -------------------------------------------------------- | --------------------------------------------- |
| `apps/web2/middleware.ts`                                | génère nonce + injecte CSP strict-dynamic     |
| `apps/web2/next.config.ts`                               | headers HSTS + permissions-policy + COOP/COEP |
| `apps/api/src/ichor_api/safety/injection_filter.py`      | layers regex+normalize+LLM-judge              |
| `apps/api/src/ichor_api/safety/audit.py`                 | dependency FastAPI write to audit_log         |
| `apps/api/src/ichor_api/middleware/rate_limit.py`        | slowapi + Redis backend                       |
| `apps/api/migrations/versions/0014_audit_log.py`         | table audit_log                               |
| `apps/api/migrations/versions/0015_feature_flags.py`     | table feature_flags custom                    |
| `apps/api/src/ichor_api/routers/health.py`               | split `/livez` `/readyz` `/startupz`          |
| `infra/nginx/upstream-blue.conf` + `upstream-green.conf` | blue-green switch                             |
| `infra/ansible/roles/blue_green/`                        | rôle deploy.sh + symlink                      |
| `.github/workflows/sbom.yml`                             | syft + grype + upload                         |
| `.github/workflows/schemathesis.yml`                     | contract testing OpenAPI                      |
| `.github/workflows/playwright.yml`                       | E2E + visual regression                       |
| `.changeset/config.json`                                 | Changesets monorepo config                    |
| `docs/runbooks/RUNBOOK-014-secrets-rotation.md`          | sops rotate workflow                          |
| `docs/runbooks/RUNBOOK-015-prompt-injection-source.md`   | différencie de 006 (output)                   |
| `apps/web2/tests/e2e/pages/`                             | POM Playwright (10 happy paths)               |
| `apps/api/tests/property/`                               | tests Hypothesis (10 propriétés)              |

## 8. Recommandations concrètes pour SPEC.md

À ajouter §3.10 (CI) :

- Préciser que S4 strict inclut **schemathesis + playwright + alembic check + squawk + syft/grype**, pas juste lint+typecheck+test+audit
- Ajouter cadence rotation secrets (90j env, 60j SSH key)

À ajouter §5 Phase D :

- **`/livez` `/readyz` `/startupz` séparés** au lieu de `/healthz` monolithique actuel
- **Blue-green systemd** comme livrable explicite (units templated + nginx upstream + script deploy.sh + RUNBOOK)
- **migrations/env.py durci** : `transaction_per_migration=True` + `lock_timeout=4s` + `statement_timeout=30s` + Squawk lint en CI
- **CSP middleware Next.js + HSTS preload + audit_log table + slowapi+Redis** dans le bloc "Ops hardening"
- **Changesets bootstrap** côté docs (CHANGELOG auto)
- **OIDC GitHub→Hetzner non disponible** → clarifier que SSH key ED25519 + rotation 60j est la voie

À ajouter §10 Risques :

- **CSP nonce force `force-dynamic`** : casse cache edge, augmente charge SSR. Mitigation : single-user, latence acceptable Hetzner
- **PostHog free tier 1M req/mo** couvre ; mais custom DB recommandé pour zéro dep externe

## Sources principales

- [Next.js 15 CSP guide](https://nextjs.org/docs/app/guides/content-security-policy)
- [next-safe-middleware](https://github.com/nibtime/next-safe-middleware)
- [SlowAPI rate-limiting FastAPI 2025](https://medium.com/@connect.hashblock/5-fastapi-rate-limiter-designs-that-actually-scale-49e467854b11)
- [Token bucket FastAPI Redis](https://www.freecodecamp.org/news/token-bucket-rate-limiting-fastapi/)
- [OWASP LLM Prompt Injection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
- [PromptGuard 2026](https://www.nature.com/articles/s41598-025-31086-y)
- [Hypothesis Python](https://hypothesis.readthedocs.io/)
- [Playwright VRT GitHub Actions](https://www.amazeelabs.com/blog/visual-regression-testing-with-playwright-and-github-actions/)
- [Chromatic vs Percy 2026](https://percy.io/blog/visual-regression-testing-tools)
- [k6 vs Locust 2026](https://medium.com/@alirezaaedalat/in-depth-exploration-k6-vs-locust-for-comprehensive-load-testing-9b657eba5314)
- [FastAPI blue-green nginx 2026](https://medium.com/@ThinkingLoop/5-fastapi-deployment-patterns-blue-green-canaries-safe-ssl-a23cbaa3f1d3)
- [PostHog feature flags free tier](https://posthog.com/pricing)
- [Alembic zero-downtime migrations](https://goldlapel.com/grounds/replication-scaling-cloud/alembic-zero-downtime-migrations)
- [Changesets pnpm monorepo 2026](https://jsdev.space/complete-monorepo-guide/)
- [Storybook 8 + MSW Red Hat 2026](https://developers.redhat.com/articles/2026/04/29/how-we-turned-storybook-behavioral-verification-engine)
- [Syft + Grype 2026 guide](https://www.jit.io/resources/appsec-tools/a-guide-to-generating-sbom-with-syft-and-grype)
- [Anchore sbom-action](https://github.com/anchore/sbom-action)
- [Kubernetes health probes pattern](https://kubernetes.io/docs/reference/using-api/health-checks/)
- [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/)
- [Hetzner GHA SSH deploy 2026](https://copyprogramming.com/howto/github-actions-deploy-user-ssh-key-code-example)
