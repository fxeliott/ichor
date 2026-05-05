# Guide manuel de déploiement — diff session 2026-05-05

Ce guide est conçu pour Eliot (débutant motivé). Chaque étape :
- les **commandes exactes** à copier-coller
- ce que tu dois **voir s'afficher**
- ce qu'il faut faire **si ça échoue**
- la **case à cocher** quand c'est validé

⏱️ Temps total estimé : 2-3 heures (1h sur ta machine, 30 min Hetzner, 30 min comptes externes).

---

## Étape 0 — Pré-flight (5 min)

**Objectif** : sauvegarder l'état actuel + comprendre la magnitude du diff.

```bash
cd /d/Ichor
git status --short | head -50
git diff --stat | tail -10
```

✅ Tu devrais voir : ~30+ fichiers modifiés, ~10 fichiers nouveaux. Si tu vois moins, ressaisir le shell.

📌 Si quelque chose te paraît bizarre, **ne commit pas tout de suite**. Demande à Claude une revue ciblée : `claude` puis "review the diff before commit".

---

## Étape 1 — Validation locale (15-30 min)

**Objectif** : prouver que tout compile + tous les tests passent AVANT de pousser sur Hetzner.

### 1.1 Setup venv apps/api

```bash
cd /d/Ichor/apps/api
uv venv
uv pip install -e ".[dev]"
```

✅ Tu devrais voir : "Built ichor-api ... installed N packages". Aucune ligne en rouge.

❌ Si erreur "websockets not found" : c'est normal avec l'ancienne version, le venv re-télécharge maintenant.

### 1.2 Mypy strict sur apps/api

```bash
uv run mypy src
```

✅ Tu devrais voir : `Success: no issues found in N source files`.

❌ Si erreurs :
- **Note les fichiers et lignes**
- Ouvre une session Claude : `claude` puis colle le bloc d'erreurs avec "fix these mypy errors without changing behavior, only type annotations"
- Re-run jusqu'à `Success`

### 1.3 Pytest apps/api (avec coverage)

```bash
uv run pytest -ra --cov=src --cov-report=term
```

✅ Tu devrais voir : `passed` sur la dernière ligne, **0 failed**, coverage ≥ 65 %.

❌ Si tests échouent :
- **N'ignore pas** — c'est exactement ce qu'on veut catcher avant push
- Pour les tests ML qui skippent (scipy/pandas absent) : OK, c'est attendu local
- Pour les autres : `claude` → colle le test failure → "diagnose and fix"

### 1.4 Tests packages/ml (optionnel — heavy deps)

```bash
cd /d/Ichor/packages/ml
uv venv
uv pip install -e ".[dev,ml]" 2>&1 | tail -5
uv run pytest -ra
```

✅ Si réussi : VPIN + SABR + FOMC chunking + bias models tous verts.
❌ Si install échoue (lightgbm/xgboost compilent souvent mal sur Windows) : skipper, ces tests tournent en CI Linux.

### 1.5 Lint + typecheck web2

```bash
cd /d/Ichor/apps/web2
pnpm install
pnpm lint
pnpm typecheck
pnpm build
```

✅ Tu devrais voir : `✓ Compiled successfully`, `0 errors, 0 warnings`.

❌ Si TypeScript errors : `claude` → colle l'erreur → "fix without changing behavior".

**Cases à cocher avant l'étape 2** :
- [ ] mypy apps/api : 0 erreur
- [ ] pytest apps/api : 0 failure
- [ ] pnpm typecheck apps/web2 : 0 erreur
- [ ] pnpm build apps/web2 : succès

⚠️ **Si une de ces cases n'est pas cochée, NE PAS PASSER À L'ÉTAPE 2**. Le risque de casser la prod est trop élevé.

---

## Étape 2 — Commit logique (10 min)

**Objectif** : 5-7 commits propres, un par groupe fonctionnel, plutôt qu'un mega-commit.

### Groupes suggérés (à committer dans cet ordre)

#### Commit 1 — ADR-022 + ADR amendment

```bash
git add docs/decisions/ADR-022-probability-bias-models-reinstated.md \
        docs/SESSION_LOG_2026-05-05.md \
        docs/ICHOR_DEPLOY_GUIDE_2026-05-05.md
git commit -m "docs: ADR-022 reinstating probability-only bias models + session log"
```

#### Commit 2 — Wave 1 quick wins

```bash
git add apps/api/src/ichor_api/main.py \
        apps/api/src/ichor_api/routers/__init__.py \
        apps/api/src/ichor_api/routers/yield_curve.py \
        apps/api/src/ichor_api/routers/sources.py \
        apps/api/src/ichor_api/routers/admin.py \
        apps/api/src/ichor_api/cli/run_briefing.py \
        apps/api/src/ichor_api/cli/run_collectors.py \
        apps/api/src/ichor_api/collectors/forex_factory.py \
        scripts/hetzner/register-cron-collectors-extended.sh \
        apps/web2/app/yield-curve/page.tsx \
        apps/web2/app/sources/page.tsx \
        apps/web2/lib/api.ts
git commit -m "feat(api+web): Wave 1 — divergence wired, /v1/yield-curve, /v1/sources, briefing 4 contexts, forex_factory persistence + cron fix"
```

#### Commit 3 — Wave 2 VPIN end-to-end

```bash
git add apps/api/migrations/versions/0020_fx_ticks.py \
        apps/api/src/ichor_api/models/__init__.py \
        apps/api/src/ichor_api/models/fx_tick.py \
        apps/api/src/ichor_api/collectors/polygon_fx_stream.py \
        apps/api/src/ichor_api/cli/run_fx_stream.py \
        apps/api/src/ichor_api/services/ml_signals.py \
        apps/api/pyproject.toml \
        scripts/hetzner/register-fx-stream.sh \
        packages/ml/src/ichor_ml/microstructure/vpin.py \
        packages/ml/tests/test_vpin.py
git commit -m "feat(ml+api): Wave 2 — VPIN end-to-end (BVC quote-tick, fx_ticks hypertable, polygon_fx_stream WebSocket, systemd unit)"
```

#### Commit 4 — Wave 3 ML signals

```bash
git add packages/ml/src/ichor_ml/vol/sabr_svi.py \
        packages/ml/src/ichor_ml/nlp/fomc_roberta.py \
        packages/ml/tests/test_sabr_svi.py \
        apps/api/src/ichor_api/services/post_mortem.py
git commit -m "feat(ml): Wave 3 — SABR-Hagan + SVI fits, FOMC long-text chunking, ADWIN drift in post_mortem, auto suggestions"
```

#### Commit 5 — Wave 4 mock removal

```bash
git add apps/api/src/ichor_api/schemas.py \
        apps/api/src/ichor_api/routers/sessions.py \
        apps/api/src/ichor_api/routers/today.py \
        apps/api/src/ichor_api/routers/macro_pulse.py \
        apps/api/src/ichor_api/services/cross_asset_heatmap.py \
        apps/web2/app/sessions/[asset]/page.tsx \
        apps/web2/app/scenarios/[asset]/page.tsx \
        apps/web2/app/today/page.tsx \
        apps/web2/app/macro-pulse/page.tsx
git commit -m "feat(web+api): Wave 4 — SessionCardOut typed enrichment, calibration 7d/90d, scenarios Pass4 tree, BestOpps live, macro heatmap endpoint"
```

#### Commit 6 — Wave 6.2 + 6.3 quality

```bash
git add apps/api/src/ichor_api/services/feature_flags.py
git commit -m "feat(api): Wave 6.2 — feature_flags Redis pub/sub cross-worker invalidation"
```

#### Commit 7 — Tests

```bash
git add apps/api/tests/test_session_card_extractors.py \
        apps/api/tests/test_cross_asset_heatmap.py \
        apps/api/tests/test_post_mortem_drift_suggestions.py \
        apps/api/tests/test_new_routers_smoke.py \
        apps/api/tests/test_app_import_sanity.py \
        apps/api/tests/test_briefing_context.py \
        apps/api/tests/test_cron_template_fix.py
git commit -m "test(api): 78 new tests covering Wave 1-6 (extractors, heatmap, post_mortem, smoke, import sanity, briefing, cron)"
```

#### Push final

```bash
git push origin main
```

✅ Tu devrais voir : `7 commits pushed to main`. CI s'enclenche automatiquement.

---

## Étape 3 — CI verts (10 min d'attente)

**Objectif** : observer la CI passer sur les 7 jobs.

```bash
gh run list --limit 1
gh run watch  # suit en temps réel
```

✅ Attendu : `node-lint`, `node-build`, `node-vitest`, `node-e2e`, `python-lint`, `python-types-tests`, `ansible-lint` tous verts.

❌ Si rouge :
- `gh run view --log-failed` pour voir les erreurs
- Le plus probable : un test apps/api qui passe local mais échoue en CI à cause de différences d'env
- Ouvre une session Claude avec le log d'erreur, demande "fix this CI failure"

---

## Étape 4 — Déploiement Hetzner (20 min)

⚠️ **Pré-requis** : tu dois savoir SSH sur ton Hetzner. Si tu ne te souviens plus de l'adresse / clé, regarde `infra/secrets/cloudflare.env` (déchiffré avec `sops`) ou `infra/ansible/inventory/hetzner.yml`.

### 4.1 SSH + pull du code

```bash
ssh ichor@<IP_HETZNER>
cd /opt/ichor
sudo -u ichor git pull origin main
```

✅ Tu devrais voir : `Fast-forward`, 7 commits intégrés.

### 4.2 Update venv apps/api (websockets dep)

```bash
cd /opt/ichor/api
sudo -u ichor uv pip install -e .
```

✅ Tu devrais voir : `+ websockets-X.Y.Z` (ou `Already satisfied: websockets>=14.0`).

### 4.3 Migration Alembic 0020

```bash
sudo -u ichor uv run alembic current
# Devrait afficher 0019 (la migration précédente)
sudo -u ichor uv run alembic upgrade head
sudo -u ichor uv run alembic current
# Devrait afficher 0020
```

✅ Tu devrais voir :
```
INFO  [alembic.runtime.migration] Running upgrade 0019 -> 0020, fx_ticks — Polygon Forex WebSocket quote ticks
0020 (head)
```

❌ Si erreur "table fx_ticks already exists" : la migration a été partiellement appliquée. Run `sudo -u ichor uv run alembic stamp 0020` pour marquer comme appliquée.

### 4.4 Restart le service API

```bash
sudo systemctl restart ichor-api
sudo systemctl status ichor-api --no-pager | head -10
```

✅ Tu devrais voir : `active (running)`.

❌ Si `failed` : `sudo journalctl -u ichor-api -n 50 --no-pager` pour les logs. Le plus probable : import error → corriger en local + repush.

### 4.5 Smoke-test les 3 nouvelles routes

```bash
curl -sf http://localhost:8001/v1/yield-curve | head -c 200
echo
curl -sf http://localhost:8001/v1/sources | head -c 200
echo
curl -sf http://localhost:8001/v1/macro-pulse/heatmap | head -c 200
```

✅ Chaque commande doit afficher du JSON, pas d'erreur 500.

### 4.6 Activation du FX quote stream (PRÉ-REQUIS : clé Polygon)

⚠️ **Avant de lancer**, vérifie que `/etc/ichor/api.env` contient bien `ICHOR_API_POLYGON_API_KEY=Meaxr6y_W4MspeotMc3hRGtcoHjiMgXX` (ou ta clé actuelle).

```bash
sudo grep POLYGON_API_KEY /etc/ichor/api.env
# Si absent : sudo nano /etc/ichor/api.env, ajouter la ligne, sauver
```

```bash
sudo bash /opt/ichor/scripts/hetzner/register-fx-stream.sh
sudo systemctl status ichor-fx-stream --no-pager | head -10
sudo journalctl -u ichor-fx-stream -n 20 --no-pager
```

✅ Tu devrais voir :
- `active (running)`
- Logs : `polygon_fx_stream.subscribed` avec les 6 paires

❌ Si `Connection refused` : la clé Polygon est probablement expirée ou le plan ne couvre pas WebSockets. Va sur https://polygon.io/account ou https://massive.com/account vérifier.

### 4.7 Vérifier que les ticks arrivent

```bash
sudo -u postgres psql ichor -c "SELECT count(*), max(ts) FROM fx_ticks WHERE ts > now() - interval '5 min';"
```

✅ Après 2-3 min de stream actif : count > 100, max(ts) très récent.

❌ Si count = 0 après 5 min : les heures de marché FX peuvent être fermées (week-end). Re-tester en semaine.

**Cases à cocher étape 4** :
- [ ] git pull réussi
- [ ] websockets dep installé
- [ ] Migration 0020 appliquée
- [ ] ichor-api restart OK
- [ ] 3 routes smoke 200 OK
- [ ] ichor-fx-stream active
- [ ] fx_ticks count > 0

---

## Étape 5 — CI ramp (Wave 5) après validation

⚠️ **Pré-requis** : étape 1 (validation locale) passée à 100 %, étape 4 OK depuis 24h.

### 5.1 mypy blocking sur apps/api

Édite [.github/workflows/ci.yml:312](.github/workflows/ci.yml) :

```yaml
# AVANT
continue-on-error: ${{ matrix.package != 'packages/shared-types' && matrix.package != 'packages/ml' }}

# APRÈS
continue-on-error: ${{ matrix.package == 'apps/claude-runner' || matrix.package == 'packages/agents' }}
```

→ rend mypy blocking sur `apps/api`, `packages/shared-types`, `packages/ml` ; warn-only sur `claude-runner` + `agents`.

### 5.2 pytest blocking sur packages/ml + agents

Édite [.github/workflows/ci.yml:320](.github/workflows/ci.yml) :

```yaml
# AVANT
continue-on-error: ${{ matrix.package != 'apps/api' }}

# APRÈS  
continue-on-error: ${{ matrix.package == 'apps/claude-runner' || matrix.package == 'packages/shared-types' }}
```

→ rend pytest blocking sur apps/api + packages/ml + packages/agents.

### 5.3 Coverage gate effective

Édite [.github/workflows/ci.yml:344](.github/workflows/ci.yml) :

```yaml
- name: Coverage gate (S4 — blocking)
  ...
  continue-on-error: false  # was true
```

```bash
git add .github/workflows/ci.yml
git commit -m "ci: Wave 5 ramp — mypy/pytest blocking on apps/api+ml, coverage gate effective"
git push
```

✅ Si la CI reste verte, le ramp est acquis.
❌ Si la CI passe rouge, **revert immédiat** : `git revert HEAD && git push`.

---

## Étape 6 — Wave 7 hors-autonomie (parallélisable)

5 tracks à compléter en parallèle. Aucune n'est bloquante pour le reste — chacune débloque une feature autonome.

### Track A — OANDA (FX practice, gratuit) ⏱️ 15 min

1. Va sur **https://developer.oanda.com/** (lien officiel, déjà cité dans `infra/secrets/oanda.env.example`)
2. Crée un compte Practice (gratuit, ne demande pas de carte)
3. Une fois loggé : **Account** → **Manage API Access** → **Generate** un Personal Access Token
4. Note ton **Account ID** (format `101-XXX-XXXXXXX-001`)
5. Sur Hetzner :
   ```bash
   sudo nano /etc/ichor/api.env
   # ajouter :
   # OANDA_API_TOKEN=<le token>
   # OANDA_ACCOUNT_ID=101-XXX-XXXXXXX-001
   # OANDA_ENV=practice
   sudo systemctl restart ichor-api
   ```
6. ✅ Validation : `curl -sf http://localhost:8001/v1/admin/status | jq '.tables'` doit montrer le compteur OANDA actif (zero ou non).

### Track B — FINRA Developer (gratuit) ⏱️ 20 min

1. Va sur **https://developer.finra.org/** (cité dans `collectors/finra_short.py`)
2. Crée un compte développeur (free, demande email seulement)
3. **Apps** → **Create New App** → choisir **regShoDaily** + **shortInterest** datasets
4. Une fois l'app créée : note **client_id** + **client_secret** (OAuth2)
5. Sur Hetzner :
   ```bash
   sudo nano /etc/ichor/api.env
   # FINRA_CLIENT_ID=<id>
   # FINRA_CLIENT_SECRET=<secret>
   sudo systemctl restart ichor-api
   ```
6. ✅ Validation : `journalctl -u ichor-collector-finra_short -n 20 --no-pager` au prochain run doit montrer `persisted N rows`.

### Track C — FlashAlpha (free GEX, 5 req/jour) ⏱️ 10 min

1. Va sur **https://flashalphalive.com/** (cité dans `collectors/flashalpha.py`)
2. Sign-up gratuit (free tier = 5 requêtes/jour, suffit pour SPX + NDX 2× par jour)
3. Génère ta clé API
4. Sur Hetzner :
   ```bash
   sudo nano /etc/ichor/api.env
   # ICHOR_API_FLASHALPHA_API_KEY=<clé>
   sudo systemctl restart ichor-api
   ```
5. ✅ Validation : `python -m ichor_api.cli.run_collectors flashalpha` (manuel) doit retourner SPX/NDX GEX.

### Track D — Domaine permanent (~$10/an, optionnel) ⏱️ 30 min

⚠️ Actuellement le tunnel pointe vers `*.trycloudflare.com` (random, change à chaque restart). Domaine fixe = stabilité.

1. Achète un domaine sur **Cloudflare Registrar** (https://www.cloudflare.com/products/registrar/) — typiquement le moins cher (~$10/an pour `.app` ou `.dev`).
2. Une fois enregistré, dans le dashboard Cloudflare :
   - **DNS** → **Add record** → CNAME `api` → `<ton-tunnel-uuid>.cfargotunnel.com` (UUID dans `infra/secrets/cloudflare.env` chiffré : `CF_TUNNEL_UUID=...`)
3. Édite `infra/cloudflare/tunnel-config.yml` localement :
   ```yaml
   ingress:
     - hostname: api.tonnouveaudomaine.app
       service: http://localhost:8001
   ```
4. Re-deploy : `cd infra/ansible && ansible-playbook site.yml -t cloudflared`
5. ✅ Validation : `curl -sf https://api.tonnouveaudomaine.app/healthz`

### Track E — GitHub `HETZNER_SSH_PRIVATE_KEY` (si auto-deploy souhaité) ⏱️ 5 min

⚠️ Ne fais cette étape QUE si tu veux du `git push → deploy auto`.

1. Sur ta machine : `cat ~/.ssh/id_ed25519` (ou la clé dont la pubkey est sur Hetzner)
2. GitHub → ton repo Ichor → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
3. Name : `HETZNER_SSH_PRIVATE_KEY`
4. Value : colle la clé privée complète (avec `-----BEGIN OPENSSH PRIVATE KEY-----` et `-----END OPENSSH PRIVATE KEY-----`)
5. ✅ Validation : push n'importe quel commit, le workflow `auto-deploy.yml` doit s'enclencher et SSH-deploy automatiquement.

⚠️ **Sécurité** : ne committe JAMAIS ta clé privée dans le repo. GitHub Secrets l'encrypte côté GitHub, c'est sûr.

**Cases à cocher Wave 7** :
- [ ] Track A — OANDA token + account_id
- [ ] Track B — FINRA client_id + client_secret
- [ ] Track C — FlashAlpha key
- [ ] Track D — Domaine permanent (optionnel)
- [ ] Track E — GitHub secret HETZNER_SSH (optionnel)

---

## Étape 7 — Validation post-deploy (10 min)

**Objectif** : prouver que tout marche en prod.

```bash
# Sur ta machine locale
HETZNER_API="https://<ton-tunnel-ou-domaine>"

# Health
curl -sf $HETZNER_API/healthz | jq .
curl -sf $HETZNER_API/readyz | jq .

# Nouvelles routes Wave 1+4
curl -sf $HETZNER_API/v1/yield-curve | jq '.shape, .slope_2y_10y'
curl -sf $HETZNER_API/v1/sources | jq '.n_live, .n_sources'
curl -sf $HETZNER_API/v1/macro-pulse/heatmap | jq '.rows[] | {row: .row, n_cells: (.cells | length)}'
curl -sf $HETZNER_API/v1/today | jq '.macro, .n_calendar_events, .n_session_cards'
curl -sf $HETZNER_API/v1/divergences | jq '.n_alerts'

# Admin status — fx_ticks doit apparaître
curl -sf $HETZNER_API/v1/admin/status | jq '.tables[] | select(.table == "fx_ticks")'
```

✅ Toutes les routes doivent renvoyer du JSON valide. Si certaines compteurs sont à 0, c'est OK (collectors pas encore tournés ou données manquantes).

---

## Étape 8 — Frontend web2 deploy (Cloudflare Pages, optionnel)

Si tu veux que `apps/web2` soit accessible publiquement :

```bash
cd /d/Ichor/apps/web2
pnpm build
# Cloudflare Pages auto-build sur push si le repo est connecté ;
# sinon : pnpm wrangler pages deploy out
```

✅ Validation : visite ton URL Pages, vérifie que les pages `/yield-curve`, `/sources`, `/macro-pulse`, `/sessions/eur-usd`, `/today` chargent et affichent le pill `▲ live`.

---

## Si quelque chose casse

1. **Garder son calme** — tout est commit-able + revert-able.
2. **Lire les logs** : `journalctl -u ichor-api -n 100 --no-pager` ou `gh run view --log-failed`.
3. **Revert** un commit :
   ```bash
   git revert <SHA>  # crée un commit inverse
   git push
   ```
4. **Demander à Claude** : ouvre une session, colle l'erreur, demande "diagnose root cause then propose fix".
5. **Restaurer la DB depuis backup** (cas extrême) : runbook `docs/runbooks/RUNBOOK-010-walg-restore-drill.md`.

---

## Récap rapide

```
Étape 1 — Validation locale          [⏱️ 30 min] [⚠️ critique]
Étape 2 — Commit logique             [⏱️ 10 min]
Étape 3 — CI verte                   [⏱️ 10 min]
Étape 4 — Deploy Hetzner             [⏱️ 20 min] [⚠️ critique]
Étape 5 — CI ramp                    [⏱️ 10 min] [optionnel J+1]
Étape 6 — Wave 7 hors-autonomie      [⏱️ 60 min, parallélisable]
Étape 7 — Validation post-deploy     [⏱️ 10 min] [⚠️ critique]
Étape 8 — Web2 deploy                [⏱️ 10 min] [optionnel]
```

**Critical path** : Étapes 1 → 2 → 3 → 4 → 7. Le reste est optionnel ou parallélisable.

🎯 **Ton premier objectif** : compléter étape 1 d'ici demain. Les autres peuvent attendre.
