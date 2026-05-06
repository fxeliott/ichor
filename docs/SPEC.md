# SPEC — Ichor

**Date** : 2026-05-02
**Auteur** : Eliot (interview Claude Code via skill `/spec`)
**Référence amont** : [ICHOR_PLAN.md](./ICHOR_PLAN.md) (vision macro, 26 axes data, 12 moteurs, 15 instruments, archi multi-agent, roadmap 7 phases)
**Statut** : prêt pour Phase 0 implémentation après `/clear` + nouvelle session

---

## 1. Vision en une phrase

Ichor est un moteur d'analyse trading multi-domaine (hors AT) qui produit des biais probabilistes calibrés (haussier/neutre/baissier %) + briefings audio + 27 types d'alertes sur 15 instruments (forex majors, indices US, métaux, énergie) en couvrant 80% du process pré-trade d'Eliot, sans jamais émettre de signal BUY/SELL.

## 2. Contexte

- **Owner unique** : Eliot, débutant motivé, France (Cournonterral). Single-user en V1, multi-tenant scaffold Phase 7.
- **Budget** : 0 € sauf Twitter strategic 30-50 €/mois max (whitelist ~30-50 comptes officiels CB/agences) + domaine ichor.app ~14 €/an.
- **Ressources Yone disponibles** : Hetzner `root@178.104.39.201`, Cloudflare API token (Workers AI + Workers + Pages), Claude Max 20x + clé API backup, ElevenLabs Brian multilingual_v2, OANDA Practice + FRED + Finnhub + Twelve Data, Telegram bots, Langfuse local Hetzner, n8n local Hetzner.
- **Conformité** : AMF — information générale non personnalisée, jamais de signaux tranchants, disclaimer obligatoire chaque vue + chaque export.

## 3. Stack technique (décisions verrouillées)

### 3.1 Backend & runtime

| Couche    | Choix                                                                                                                                                | Rationale                                                                                                                                                                           |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend   | **FastAPI (Python 3.12)**                                                                                                                            | Toute la stack ML/quant est Python (DSPy, LlamaIndex Workflows, Letta, Pydantic AI, hmmlearn, river, FinBERT, NumPyro, dtaidistance). Une seule pile à maintenir, OpenAPI 3.1 auto. |
| API style | **OpenAPI auto + `orval` client TS**                                                                                                                 | Type-safe end-to-end sans Node côté serveur. FastAPI génère le schéma, `orval` génère le client TanStack Query côté Next.js.                                                        |
| Real-time | **WebSocket natif FastAPI**                                                                                                                          | Suffisant single-user, pas de dépendance lourde (Socket.IO retiré). Hook React custom avec reconnect strategy côté front.                                                           |
| Agents    | **Claude Agent SDK Python v0.1.72** + DSPy v3.2.0 + LlamaIndex Workflows v0.14.21 + Letta v0.16.7 + Pydantic AI v1.89.1                              | Stack validée plan Lot 3. MIT/Apache, MCP natif.                                                                                                                                    |
| LLMs      | Claude Opus 4.7 (orchestrator), Sonnet 4.6 (CB-NLP, Critic), Haiku 4.5 (News-NLP), Cerebras Llama-70 (Macro), Groq Llama-70 (Sentiment, Positioning) | Plan Yone — 5 modèles, 5 rôles, 0 € hors Claude Max.                                                                                                                                |

### 3.2 Frontend

| Couche              | Choix                                                                                                    |
| ------------------- | -------------------------------------------------------------------------------------------------------- |
| Framework           | **Next.js 15 App Router**                                                                                |
| CSS                 | **Tailwind CSS v4**                                                                                      |
| Composants          | **shadcn/ui + Radix UI**                                                                                 |
| Charts              | **lightweight-charts TradingView v5** (Apache 2.0, attribution + logo TradingView en footer obligatoire) |
| Knowledge graph viz | **react-force-graph** (rendu)                                                                            |
| Animations          | **Framer Motion v11**                                                                                    |
| Icons               | **Lucide React**                                                                                         |
| State               | **Zustand + TanStack Query**                                                                             |
| Tableaux            | **TanStack Table v8**                                                                                    |
| Theme               | **next-themes** (dark default, light togglable)                                                          |
| Toasts              | **Sonner**                                                                                               |
| Command palette     | **cmdk** (Cmd+K Linear-like)                                                                             |
| PWA                 | **@serwist/next** (manifest + service worker + Web Push)                                                 |
| Hôtesse             | **Cloudflare Pages**                                                                                     |

### 3.3 Stockage data

| Couche                  | Choix                                                                                                             |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------- |
| DB primaire             | **PostgreSQL 16 + TimescaleDB 2.x** (Hetzner self-host)                                                           |
| Cache                   | **Redis 7** (Hetzner self-host)                                                                                   |
| Knowledge graph         | **Kuzu embedded** (fichier `.kz`, MIT, Cypher-like)                                                               |
| Features brutes         | Wide tables TimescaleDB hypertables par axe (`features_macro`, `features_sentiment`, `features_volatility`, etc.) |
| Features dérivées       | **Parquet** par actif/jour : `data/features/{symbol}/{YYYY-MM-DD}.parquet`                                        |
| Archives long-terme     | **Hetzner `/var/lib/ichor/archives/`** Parquet mensuel **+ sync hebdo Cloudflare R2** (gratuit ≤10 GB/mois)       |
| Compression TimescaleDB | Compression after **30 jours**, rétention **infinie**                                                             |
| Phase 2+ analytics      | DuckDB + Parquet à ajouter si besoin réel ; **pas dans Phase 1**                                                  |

### 3.4 Archivage HY/IG OAS — CRITIQUE J0

> FRED limite `BAMLH0A0HYM2` + `BAMLC0A0CM` à **3 ans glissants depuis avril 2026**. Sans archivage immédiat = perte historique long irréversible.

- **Cron J0** : `*/30 * * * *` toutes les 30 min, append daily values vers `/var/lib/ichor/archives/oas/{YYYY}/{YYYY-MM}.parquet`
- **Format Parquet** : colonnes `date`, `series_id`, `value`, `vintage_at`, `source` ; partition mensuelle
- **Manifest** : `archives/oas/MANIFEST.json` met à jour la dernière vintage par série
- **Sync R2** : `rclone sync` chaque dimanche 02:00 UTC vers bucket `ichor-archives` (versioning activé)
- **Backup logique** : pg_dump weekly du même état dans Postgres (table `oas_archive`) pour query SQL rapide

### 3.5 ML / quant

| Composant                                    | Lib                                                                                                                                                  |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| HMM régimes 3 états (calm/elevated/stressed) | **hmmlearn**                                                                                                                                         |
| DTW analogues historiques                    | **dtaidistance**                                                                                                                                     |
| Concept drift detection                      | **river** (ADWIN + page-Hinkley)                                                                                                                     |
| Bayesian inference                           | **NumPyro** + **PyMC** (CBN)                                                                                                                         |
| Tournament 6 modèles                         | **Logistic Regression (sklearn)**, **LightGBM**, **XGBoost**, **Random Forest (sklearn)**, **Bayesian Logistic (NumPyro)**, **MLP simple (PyTorch)** |
| Calibration                                  | **Isotonic Regression** par défaut (`CalibratedClassifierCV(method='isotonic', cv=5)`), recalibration mensuelle 90j glissants                        |
| Brier scoring                                | Implémentation maison (formule standard, decomposition reliability/resolution/uncertainty)                                                           |
| Triple-barrier / CPCV / PBO                  | **Réimplémentation maison** depuis López de Prado (mlfinlab passé propriétaire)                                                                      |
| NLP CB                                       | **gtfintechlab/FOMC-RoBERTa** + **ZiweiChen/FinBERT-FOMC** (HF), méthodologies Hansen-McMahon (JIE 2016) + Aruoba-Drechsel (NBER WP 32417 2024)      |
| NLP général                                  | **FinBERT-tone (yiyanghkust)**, **FinGPT (AI4Finance)**                                                                                              |
| Topic modeling                               | **BERTopic** + **LDA** (gensim)                                                                                                                      |

### 3.6 Repo & dev workflow

- **Monorepo Turborepo** :
  ```
  ichor/
  ├── apps/
  │   ├── web/              # Next.js 15 (PWA, dashboard, asset cards)
  │   └── api/              # FastAPI (agents, ML, collectors orchestration)
  ├── packages/
  │   ├── collectors/       # Python — sources data (FRED, ECB, Polymarket, ...)
  │   ├── agents/           # Python — Claude Agent SDK orchestration
  │   ├── ml/               # Python — modèles, tournament, calibration, HMM
  │   ├── shared/           # TypeScript — types partagés (générés depuis OpenAPI)
  │   └── ui/               # TypeScript — design system shadcn customisé
  ├── infra/
  │   ├── hetzner/          # Ansible/scripts setup serveur
  │   ├── cloudflare/       # Wrangler config, Pages, Access, R2, Workers
  │   └── docker/           # Compose dev local (Postgres+TS+Redis+Kuzu)
  ├── docs/                 # Markdown — runbooks, architecture, schemas
  ├── scripts/              # Maintenance (archivage OAS, backup, restore)
  ├── .github/workflows/    # CI/CD
  ├── turbo.json
  ├── pnpm-workspace.yaml
  ├── pyproject.toml        # uv (gestionnaire Python moderne)
  └── ICHOR_PLAN.md, SPEC.md
  ```
- **Gestionnaire Python** : `uv` (Astral, ultra rapide, lock file reproductible)
- **Gestionnaire JS** : `pnpm` workspaces
- **Linters** : `ruff` (Python), `eslint` + `prettier` (TS), `biome` en alternative à évaluer
- **Tests** : `pytest` (Python), `vitest` (TS), `playwright` (E2E)
- **CI/CD** : **GitHub Actions** — workflows `ci.yml` (lint+test+typecheck), `deploy-pages.yml` (Cloudflare Pages auto sur main), `deploy-api.yml` (Hetzner via SSH+rsync+systemctl restart)

### 3.7 Hetzner — reprise + wipe contrôlé

> Décision Eliot : « reprend le serveur mais nettoie le à 0 ».

**Procédure Phase 0** :

1. **Backup avant wipe** :
   - `pg_dumpall` Langfuse data → `D:\Ichor\backups\hetzner\langfuse_pre_wipe_2026-05-02.sql`
   - `n8n export:workflow --all --output=...` workflows → `n8n_workflows_pre_wipe.json`
   - `tar` `/etc`, `/home`, clés SSH, certs Let's Encrypt
2. **Wipe** : Hetzner Robot console → réinstallation **Ubuntu 24.04 LTS** (clean image)
3. **Re-provision** via Ansible playbook `infra/hetzner/playbook.yml` :
   - Hardening SSH (port custom, key-only, fail2ban, ufw)
   - Install Postgres 16 + TimescaleDB 2.x + Redis 7
   - Install Python 3.12 + uv + Node 20 + pnpm
   - Install Docker + docker-compose (pour Loki + Grafana)
   - Install Langfuse self-host (re-import data depuis backup)
   - Install n8n (re-import workflows)
   - Systemd units : `ichor-api.service`, `ichor-collectors.service`, `ichor-archiver.service` (cron OAS J0)
4. **Vérification** : tests de fumée chaque service, ports ouverts uniquement nécessaires.

### 3.8 Sécurité & ops

| Domaine                     | Choix                                                                                                                                                                                                                   |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Secrets                     | **SOPS + age** (`.env.sops` chiffré committable, clé age en `~/.config/sops/age/keys.txt`) + **systemd LoadCredential** côté Hetzner (`/etc/ichor/secrets/` chmod 600) + **Cloudflare Pages env vars** côté front       |
| Auth V1                     | **Cloudflare Access Zero-Trust** (login email magic-link / Google / Passkey, gratuit ≤50 users) — **0 ligne d'auth dans le code Phase 1**, migrable Phase 7                                                             |
| Observabilité               | **Langfuse** (déjà installé Hetzner port 13000) pour traces LLM + tokens/coût + **OpenTelemetry SDK Python** (traces app + DB + HTTP) → exporter OTLP → **Tempo + Loki + Grafana** self-host Hetzner via docker-compose |
| Logs                        | journald → Loki via promtail. Rétention 30j hot, 1 an cold (compression).                                                                                                                                               |
| Métriques                   | **Prometheus** node_exporter + custom metrics FastAPI → Grafana dashboards (api latency, ML inference time, brier score live, regime current)                                                                           |
| Alerts ops                  | Grafana → email Eliot + PWA push (canal séparé du push utilisateur)                                                                                                                                                     |
| Sanitation prompt injection | Tout pipeline NLP qui ingère contenu externe (RSS, Reddit, scrapes) DOIT passer par **`promptsanitize` maison** : strip control chars, escape markdown injections, max length, watchlist red-flag patterns              |

### 3.9 Domaine

- **ichor.app** acheté Phase 0 via **Cloudflare Registrar** (~14 €/an, HTTPS auto, DNSSEC)
- **Sous-domaines** :
  - `app.ichor.app` → Next.js PWA (Cloudflare Pages)
  - `api.ichor.app` → FastAPI (Hetzner via Cloudflare proxy + tunnel ou A record)
  - `docs.ichor.app` → docs internes (Mintlify ou Nextra)
- **Fallbacks** si `ichor.app` pris : `ichor.fyi`, `getichor.com`
- **À retirer** : tout couplage avec `fxmilyapp.com` (« on oublie Yone formation, on reprend tout de 0 »)

## 4. Architecture multi-agent (rappel + précisions)

```
┌──────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR (Claude Opus 4.7, 1M ctx)                           │
│ — décompose, route, synthétise                                   │
│ — mémoire long-terme via Letta                                   │
│ — observabilité Langfuse (traces, tokens, coût)                  │
└──┬──────────────┬──────────────┬─────────────┬──────────────────┘
   │              │              │             │
┌──▼──┐     ┌────▼──┐      ┌────▼──┐     ┌────▼──┐
│MACRO│     │SENTIM.│      │POSITION│    │CB-NLP │
│Cere-│     │Groq   │      │Groq    │    │Sonnet │
│bras │     │Llama  │      │Llama   │    │4.6    │
└──┬──┘     └───┬───┘      └────┬───┘    └────┬──┘
   │            │               │              │
   └────────────┴───────────────┴──────────────┴──────► NEWS-NLP (Haiku 4.5)
                            │
                            ▼
              ┌─────────────────────────────┐
              │ BIAS AGGREGATOR             │
              │ Brier-weighted ensemble     │
              │ Bayesian + Logistic + LGBM  │
              │ + XGBoost + RF + MLP        │
              │ Regime-aware (HMM 3 états)  │
              └──────────┬──────────────────┘
                         │
                         ▼
              ┌─────────────────────────────┐
              │ CRITIC AGENT (Sonnet 4.6)   │
              │ challenge, contre-arguments │
              │ flag overconfidence         │
              └──────────┬──────────────────┘
                         │
                         ▼
              ┌─────────────────────────────┐
              │ JOURNALIST AGENT (Opus 4.7) │
              │ briefings, asset cards,     │
              │ voice scripts ElevenLabs    │
              └─────────────────────────────┘
```

## 5. UI/UX (rappel + précisions)

### 5.1 Identité visuelle

- **À designer Phase 0** via skills Anthropic `canvas-design` + `brand-guidelines` :
  - Logo monogramme géométrique + pulse dot animé
  - Palette validée plan : haussier `#4ADE80`, baissier `#F87171`, neutre `#94A3B8`, alerte `#FB923C`, crisis `#E879F9`, confidence haute `#22D3EE`, fonds zinc/slate
  - Typo : Inter (UI) + JetBrains Mono (chiffres)
  - Aucun emoji UI, icônes Lucide/Tabler
  - Mockups asset cards générés Phase 0 → revue Eliot avant code

### 5.2 Timezone — règle non négociable

- **Backend** stocke tout en **UTC**.
- **UI** affiche tout en **Europe/Paris** avec gestion DST automatique (`date-fns-tz` ou `Temporal API` polyfill).
- Tous les timestamps visibles utilisateur (briefings, alerts, calendriers, last-update markers, charts X-axis labels) en heure Paris.
- Cron tasks définis en UTC (cohérence serveur), affichage ETA en heure Paris dans UI.
- Briefings cron :
  | Cron UTC | Heure Paris (été CEST UTC+2) | Heure Paris (hiver CET UTC+1) | Logique |
  |---|---|---|---|
  | `0 6 * * *` | 08h00 | 07h00 | Pre-Londres |
  | `0 12 * * *` | 14h00 | 13h00 | Pre-NY |
  | `0 17 * * *` | 19h00 | 18h00 | NY mid |
  | `0 22 * * *` | 00h00 (lendemain) | 23h00 | NY close |
  | `0 18 * * 0` | 20h00 dim. | 19h00 dim. | Weekly review |

### 5.3 Pages principales (sitemap V1 Phase 1)

`/` Dashboard live · `/asset/:symbol` Asset card profonde · `/scenarios/:symbol` 7 scenarios · `/macro` · `/central-banks` · `/sentiment` · `/positioning` · `/volatility` · `/cross-asset` · `/calendar` · `/alerts` · `/briefings` · `/settings`

(Phase 2+ : `/world`, `/energy`, `/geopolitics`, `/shipping`, `/narratives`, `/research`, `/knowledge-graph`, `/performance`, `/fraud-watch`)

### 5.4 12 composants design system (à coder Phase 0/1)

`<BiasBar />`, `<AssetCard />`, `<Heatmap />`, `<RegimeIndicator />`, `<EventTimeline />`, `<ScenarioBars />`, `<ContributionList />`, `<MetricCard />`, `<NarrativePill />`, `<AlertToast />`, `<SourceBadge />`, `<ConfidenceBand />`

### 5.5 Persona Ichor v1

- **Ton** : sobre analyste institutionnel + ultra compréhensible, expliqué.
- **Toggle UI** : « Verbose » (off par défaut) → ajoute paragraphes pédagogiques expliquant le « pourquoi » derrière chaque biais et le mécanisme de transmission.
- **Règles dures** :
  - Toujours quantifier l'incertitude : « biais haussier modéré 65% (confiance 0.72) »
  - Jamais d'hyperboles (« révolutionnaire », « ultime », « certain »)
  - Jamais de signaux BUY/SELL tranchants
  - Cite ses sources (badge `<SourceBadge />` avec lien vers donnée brute)
  - Signale ses doutes explicitement (« données discordantes : Polymarket 75% Fed-cut vs COT spec long extrême »)
  - Publie ses erreurs (page `/performance` : Brier scores live, hits/misses calibrés)
  - Format dates/heures **toujours Europe/Paris**

### 5.6 Pipeline audio Brian — exigence qualité maximale

- **TTS** : ElevenLabs `eleven_multilingual_v2`, voix **Brian**, langue **français** (vérifier qualité native FR à acquisition compte ; si insuffisante, switch voix FR-native d'ElevenLabs avec validation Eliot).
- **Pré-processing texte obligatoire** :
  - Normalisation nombres : `65%` → `soixante-cinq pour cent`, `2,4 pp` → `deux virgule quatre points de pourcentage`
  - Acronymes finance via **dictionnaire phonétique custom** : `EURUSD` → `euro-dollar`, `FOMC` → `F-O-M-C` (épelé), `OPEC+` → `OPEP plus`, `ECB` → `B-C-E`, `BoJ` → `B-O-J`, `DXY` → `dixie`, `bp/bps` → `point(s) de base`, `pp` → `point(s) de pourcentage`, `IV30` → `vol implicite trente jours`, etc. Dictionnaire JSON versionné `packages/agents/voice/lexicon_fr.json`.
  - Dates : `2026-05-02` → `vendredi 2 mai 2026`
  - Pauses SSML `<break time="500ms"/>` entre sections, `<emphasis>` sur les niveaux clés
  - Strip markdown/emojis, escape XML
- **Robustesse** :
  - Retry 3× avec backoff sur 5xx ElevenLabs
  - Fallback : si TTS échoue 3×, génère version texte uniquement + alerte ops Grafana
  - Cache TTS local Hetzner par hash(texte) — évite régénérations coûteuses
- **Voice Q&A** : différé Phase 5 conformément au plan.

### 5.7 Notifications

- **Primaire** : **PWA Web Push (VAPID)** via service worker @serwist/next + endpoints VAPID FastAPI. iOS 16.4+ et Android tous compatibles.
- **Secondaire** : email (mailgun free 100/jour ou Cloudflare Email Routing → Resend free tier).
- **Telegram retiré V1** (préférence Eliot : « notifications app c'est plus pro »).
- **Canaux** :
  - `urgent` : crisis mode, threshold breach, calendar T-5min → push instantané
  - `briefings` : briefings prêts → push doux
  - `alerts` : 27 types d'alertes, granularité réglable par type dans `/settings`

### 5.8 Disclaimers (compliance AMF)

- **Modal au 1er login** (acceptation requise stockée + datée) — texte complet article L.541-1 CMF
- **Footer permanent** sur toutes les pages — version compacte
- **En-tête sur tout export** PDF/email/audio (préfixe spoken au début du briefing audio)

## 6. Comportement attendu — Phase 1 happy paths

### 6.1 Démarrage matin Eliot (pre-Londres 07h-08h Paris)

1. Cron 06:00 UTC déclenche `journalist-agent` qui :
   - Lit dernier état `bias_aggregator` pour EURUSD + XAUUSD + NAS100
   - Génère briefing texte (Opus 4.7, ~800 mots)
   - Passe par Critic agent (Sonnet 4.6) qui challenge → si critique majeure, regen
   - Pré-process texte → TTS Brian FR
   - Stocke audio MP3 + transcript dans `briefings/{date}/preLondon.{mp3,md}`
2. PWA push notification "Briefing Pre-Londres prêt" → ouvre `/briefings/2026-05-02-preLondon`
3. Dashboard `/` actualisé : régime courant, biais 3 actifs, top 5 events du jour (heure Paris)

### 6.2 Consultation asset card EURUSD

- Eliot ouvre `/asset/eurusd`
- Affiche :
  - `<BiasBar>` haut : haussier 62% / neutre 23% / baissier 15% (ConfidenceBand)
  - `<RegimeIndicator>` : régime « elevated » (HMM)
  - 12 moteurs en `<ContributionList>` : chaque moteur avec son biais individuel + poids actuel + drivers principaux
  - `<ScenarioBars>` : 7 scenarios probabilisés avec triggers + targets + invalidation
  - 8 stress tests live (CPI surprise +0.3pp, NFP miss, FOMC hawkish surprise, ECB cut, VIX spike, etc.)
  - 3-5 historical analogues DTW (régimes passés similaires) cliquables → comparaison
  - Chart lightweight-charts 4H + 1D + 1W avec overlays GEX, VPIN, Polymarket Fed-cut prob
  - `<EventTimeline>` calendar (heure Paris) avec impacts attendus
  - Tous les `<SourceBadge>` cliquables → lien donnée brute (FRED page, Polymarket market, etc.)

### 6.3 Alerte critique Crisis Mode

- VIX +30% intraday détecté par `monitor-agent`
- Trigger Crisis Mode : top bar UI passe rouge, dashboard reorganisé pour mettre cross-asset stress en haut, frequency push notifications x3
- Briefing Crisis ad-hoc généré sans attendre cron
- Audio Brian Crisis (ton plus urgent, vocabulary `« attention immédiate »`)

## 7. Edge cases & erreurs

| Cas                                       | Comportement attendu                                                                                                                                                 |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API source down (FRED/EIA)                | Retry exponential backoff (1s, 2s, 4s, 8s, 16s) ; après 5 échecs, log + Grafana alert + UI affiche `<SourceBadge variant="stale">` avec délai depuis dernière donnée |
| TTS ElevenLabs 5xx                        | 3 retries ; si total échec, briefing texte servi + ops alert                                                                                                         |
| Cloudflare Access bloque login            | Magic-link email fallback ; si KO total, accès direct Hetzner via SSH tunnel admin (documenté runbook)                                                               |
| Postgres slow query (>2s)                 | Log + EXPLAIN ANALYZE auto-archivé ; circuit breaker côté FastAPI évite cascade                                                                                      |
| WebSocket déconnexion                     | Frontend reconnect exponential backoff + replay missed events depuis API REST `/sync?since=`                                                                         |
| Brier score se dégrade (>0.25 sur 30j)    | Trigger ré-entraînement accéléré ; si persistance 60j, alerte Self-Reflection hebdo + revue manuelle                                                                 |
| Concept drift (river ADWIN)               | Switch automatique sur model challenger ; baseline reste comparé pour 30j                                                                                            |
| Prompt injection détectée dans source NLP | Sanitization + log + flagging source ; pattern récurrent → blacklist source                                                                                          |
| HY/IG OAS series gap >24h                 | Critique : ops alert immédiate, vérification manuelle FRED rate limit / format change                                                                                |
| Cloudflare R2 sync échoue                 | Retry hourly ; après 24h échecs, ops alert + tentative S3 backup secondary                                                                                           |

## 8. Critères d'acceptation Phase 0

Phase 0 est **done** quand TOUS les critères suivants passent :

- [ ] Domaine `ichor.app` acheté + DNS Cloudflare configuré
- [ ] Hetzner wipé + Ubuntu 24.04 fresh + Postgres 16 + TimescaleDB + Redis + Python 3.12 + uv + Node 20 + pnpm installés via Ansible playbook
- [ ] Langfuse + n8n re-déployés sur Hetzner avec données restaurées
- [ ] Repo `ichor/` GitHub privé créé, monorepo Turborepo init (`apps/web`, `apps/api`, `packages/*`, `infra/*`)
- [ ] CI GitHub Actions verte sur main : lint + typecheck + test stub
- [ ] SOPS+age secrets : `.env.sops` committé déchiffrable par clé Eliot, systemd LoadCredential testé sur Hetzner
- [ ] Cloudflare Access activé sur `*.ichor.app` (login Eliot via magic-link OK)
- [ ] FastAPI minimal `/healthz` qui se déploie sur Hetzner via GitHub Actions
- [ ] Next.js minimal Cloudflare Pages déployé sur `app.ichor.app` (page d'accueil placeholder + dark mode + disclaimer modal)
- [ ] Service worker PWA + VAPID push test (notification reçue sur iOS + Android Eliot)
- [ ] **Archivage HY/IG OAS opérationnel** : cron systemd `ichor-archiver.service` lancé, premier Parquet écrit, sync R2 vérifié manuellement
- [ ] Clés API testées via script `scripts/check_api_keys.py` (OK : FRED, EIA, Polymarket Gamma, OANDA Practice, Tradier free, Finnhub, ElevenLabs, Cloudflare API, GitHub PAT)
- [ ] ElevenLabs Brian voix FR : 1 phrase test prononcée + dictionnaire phonétique custom v0 prouvé sur 10 termes finance
- [ ] Persona Ichor v1 prompt finalisé + documenté `packages/agents/personas/ichor.md`
- [ ] Logo + palette + 3 mockups asset cards générés via canvas-design + validés Eliot
- [ ] Runbook ops `docs/runbook.md` à jour : reboot Hetzner, restore backup, rotate secrets, revoke access

## 9. Sources data Phase 1 — 10 blocks priorisés

Pour les 3 actifs MVP **EURUSD + XAUUSD + NAS100**.

| Block                                        | Sources                                                                                                                                                                                 | Priorité Phase 1 |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| **A. Macro core FRED**                       | `WALCL`, `RRPONTSYD`, `WTREGEN`, `BAMLH0A0HYM2`, `BAMLC0A0CM`, `T5YIE`, `T10YIE`, `T5YIFR`, `THREEFYTP10`, `T10Y2Y`, `DGS10`, `DGS2`, `SAHMREALTIME`, `USEPUINDXD`, `DTWEXBGS`          | Sem 1            |
| **B. Sentiment & positioning**               | Polymarket Gamma API (Fed-cut, recession, election markets), CFTC COT (`cot_reports`), Reddit OAuth (r/forex, r/Gold, r/StockMarket, r/wallstreetbets), Google Trends (pytrends)        | Sem 1-2          |
| **C. Volatilité & options**                  | VIX, VVIX, VIX9D, VIX3M, VIX6M (FRED), MOVE, OVX, GVZ (yfinance), Tradier free options chains pour SPX/NDX (GEX 0DTE), VRP calc maison                                                  | Sem 2            |
| **D. Cross-asset & corrélations**            | DXY broad, US10Y, gold, oil WTI, copper (FRED + yfinance), rolling 30j corrs matrix, HMM régime                                                                                         | Sem 2            |
| **E. Énergie (NAS100 cyclicals + risk-off)** | EIA API v2 STEO, weekly stocks, Cushing inventory                                                                                                                                       | Sem 3            |
| **F. CB NLP**                                | Fed (FOMC statements, minutes, Beige Book, dot plot, Powell pressers `/mediacenter/files/`), ECB (statements, minutes, speeches), `gtfintechlab/FOMC-RoBERTa`, `ZiweiChen/FinBERT-FOMC` | Sem 3-4          |
| **G. News & academic**                       | Reuters / AP / Bloomberg public RSS, GDELT DOC 2.0, arXiv q-fin RSS daily, NBER WP RSS                                                                                                  | Sem 4            |
| **H. EURUSD specifics**                      | Rate diff calc FRED+ECB, EU PMI, BIS effective EUR, COT EUR                                                                                                                             | Sem 4            |
| **I. XAUUSD specifics**                      | TIPS real yields (FRED), DXY, Gold ETF flows SPDR Gold (web scrape SPDR holdings), WGC quarterly CB purchases (PDF parse), gold/silver ratio                                            | Sem 5            |
| **J. NAS100 specifics**                      | Mega-cap earnings (Finnhub free) — AAPL/MSFT/GOOGL/AMZN/META/NVDA/TSLA, AI capex narrative (BERTopic sur news), GEX SPX/NDX, US10Y inverse                                              | Sem 5-6          |

Sem 7-8 : intégration multi-block dans Bias Aggregator, calibration tournament, premier briefing audio Brian end-to-end, dashboard live.

## 10. Hors scope V1 (différé Phase 2+)

- ❌ Voice Q&A interactif (Whisper STT + Claude + Brian TTS bidirectionnel) — Phase 5
- ❌ Knowledge Graph navigable interactif — Phase 3
- ❌ World State Hub daily synthesis — Phase 2
- ❌ Crisis Mode complet (V1 = trigger + briefing ad-hoc, pas de mode UI dédié reorganisé)
- ❌ Tournament étendu + active learning + concept drift complet — Phase 5
- ❌ Fraud Watch (AMF/SEC/FINRA/SEBI/BaFin cross-check) — Phase 6
- ❌ Recherche académique synthesizer hebdomadaire dimanche — Phase 6
- ❌ DuckDB+Parquet analytics layer — Phase 2+ si besoin réel
- ❌ Multi-tenant scaffold — Phase 7
- ❌ 12 actifs supplémentaires (Phase 2 : +5 ; Phase 3 : +5 ; reste Phase 4)
- ❌ Twitter strategic whitelist (30-50 comptes) — Phase 2 (budget activé après MVP validé)
- ❌ Knowledge graph causal Bayesian Networks complet — Phase 3
- ❌ MIDAS regression + Kalman filter latent factors — Phase 4
- ❌ Counterfactual reasoning agent — Phase 5

## 11. Décisions documentées (tableau récap avec rationale)

| Sujet         | Choix                                                | Pourquoi                                               |
| ------------- | ---------------------------------------------------- | ------------------------------------------------------ |
| Backend       | FastAPI Python                                       | Stack ML 100% Python, une seule pile                   |
| Repo          | Monorepo Turborepo                                   | Solo dev, refactor cross-package, cache build          |
| Hetzner       | Wipe + Ubuntu 24.04 propre                           | « Reprend le serveur mais nettoie le à 0 »             |
| CI/CD         | GitHub Actions                                       | Standard, gratuit, intégré GitHub PAT                  |
| DB            | Postgres 16 + TimescaleDB                            | Hypertables compress, query SQL, retention infinie     |
| Features      | Hybride SQL + Parquet                                | Live SQL + analytics Parquet                           |
| OAS archive   | Hetzner Parquet + R2 sync hebdo                      | Critique J0, redondance                                |
| Compression   | 30j + retention infinie                              | Analogues historiques 10+ ans nécessaires              |
| Charts        | lightweight-charts TV                                | Standard pro trading, perf canvas, attribution OK      |
| KG            | Kuzu embedded                                        | Pas de service, fichier `.kz`, Cypher-like             |
| API           | OpenAPI + orval client TS                            | Type-safe sans tRPC (backend Python)                   |
| Real-time     | WS natif FastAPI                                     | Suffisant single-user, pas de Socket.IO                |
| HMM           | hmmlearn                                             | Stable, sklearn-like, consensus académique             |
| DTW           | dtaidistance                                         | Spécialisé, perf C bindings                            |
| Tournament    | Logistic + LGBM + XGBoost + RF + Bayesian + MLP      | Couverture linéaire/non-linéaire/Bayesian/ensemble     |
| Calibration   | Isotonic + recal mensuelle 90j                       | Standard moderne non-paramétrique                      |
| Persona       | Sobre + verbose togglable                            | « Le plus complet possible mais ultra compréhensible » |
| Briefings     | 5 cron UTC, UI heure Paris                           | Sessions trading + lisibilité Eliot                    |
| Voice Q&A     | Phase 5                                              | Plan original respecté, MVP plus rapide                |
| Audio TTS     | Brian FR + lexique custom + retry+fallback           | « Articule et prononciation parfaite »                 |
| Notifications | PWA Web Push VAPID                                   | « C'est plus pro mieux » qu'un Telegram                |
| Telegram      | Retiré V1                                            | Remplacé par PWA push                                  |
| Secrets       | SOPS+age + systemd creds + Cloudflare env            | Pro-grade gratuit                                      |
| Observability | Langfuse + OTel + Loki/Grafana                       | Pro-grade, Langfuse déjà installé                      |
| Auth          | Cloudflare Access Zero-Trust                         | 0 ligne d'auth dans le code, gratuit ≤50 users         |
| Domain        | ichor.app                                            | Court, mémorable, .app HTTPS auto                      |
| Disclaimers   | Modal 1er login + footer permanent + en-tête exports | Compliance AMF max, friction min                       |

## 12. Ressources Yone — mapping (rappel)

| Ressource                        | Statut                    | Usage Ichor V1                                                                        |
| -------------------------------- | ------------------------- | ------------------------------------------------------------------------------------- |
| Hetzner `root@178.104.39.201`    | À wipe                    | Backend FastAPI + Postgres + Redis + Langfuse + n8n + Loki/Grafana + cron archiver    |
| Cloudflare API token             | OK                        | Pages (front) + Access (auth) + R2 (archives) + Registrar (ichor.app) + Email Routing |
| Claude Max 20x                   | OK                        | Tous les agents (orchestrator Opus, CB-NLP/Critic Sonnet, News-NLP Haiku)             |
| Anthropic API key backup         | OK                        | Fallback si Max throttled                                                             |
| Groq Cloud free 14400/jour       | OK                        | Sentiment + Positioning agents                                                        |
| Cerebras free 60/min             | OK                        | Macro agent                                                                           |
| HuggingFace                      | OK                        | FOMC-RoBERTa, FinBERT-FOMC, FinBERT-tone downloads                                    |
| OANDA Practice                   | OK                        | Forex/indices/métaux prix temps réel                                                  |
| FRED API                         | OK                        | Macro core (block A)                                                                  |
| Finnhub free                     | OK                        | Earnings + sentiment news                                                             |
| Twelve Data                      | OK                        | Backup quotes                                                                         |
| ElevenLabs Brian multilingual_v2 | OK                        | Briefings audio FR                                                                    |
| Langfuse Hetzner port 13000      | À ré-installer post-wipe  | Traces LLM                                                                            |
| n8n Hetzner port 5678            | À ré-installer post-wipe  | Workflows scheduling secondaires                                                      |
| GitHub PAT (fxeliott)            | OK                        | Repo `ichor/` privé + GitHub Actions                                                  |
| Oracle Cloud Always Free         | OK (réserve)              | Pas utilisé V1, dispo si besoin DR                                                    |
| Gemini                           | ⚠ Lockdown billing        | Non utilisé Ichor (incident 2026-04, vigilance)                                       |
| OpenAI                           | ❌ Interdit règle interne | N/A                                                                                   |

## 13. Risques & questions ouvertes (non bloquants)

1. **Brian voix FR qualité** : à valider Phase 0 avec 10 phrases test couvrant acronymes finance + nombres + dates. Si insuffisant, switch voix FR-native ElevenLabs avec accord Eliot avant production.
2. **Cloudflare Access free 50 users** : assumé suffisant V1. Migration Clerk/Supabase Auth à prévoir Phase 7.
3. **Hetzner disque** : vérifier capacité Phase 0 avant wipe (Postgres + archives + Loki retention 30j). Cible : ≥100 GB libres pour confort 1 an.
4. **Polymarket Gamma API rate limits** : pas documentés officiellement, monitorer en Phase 1, fallback Kalshi si throttling.
5. **`ichor.app` disponibilité** : à vérifier J0 sur Cloudflare Registrar. Fallbacks documentés (`ichor.fyi`, `getichor.com`).
6. **Senate LDA → LDA.gov migration 2026-06-30** : pas d'impact V1 (smart money block décalé Phase 4) mais wrapper config bascule à prévoir.
7. **Compliance Malaisie** : Eliot futur résident MY <1 an. À reconfirmer avocat MY 2-3 mois avant Phase 7.

## 14. Phase 0 — Plan d'attaque concret (post-`/clear`)

> Ce plan sera repris en début de session Phase 0 implémentation après `/clear`.

**Semaine 1 — Infrastructure**

1. Achat `ichor.app` Cloudflare Registrar
2. Backup Hetzner pre-wipe (Langfuse + n8n + /etc + clés)
3. Wipe + réinstall Ubuntu 24.04
4. Ansible playbook : Postgres+TS+Redis+Python+Node+Docker+Langfuse+n8n+Loki/Grafana
5. Init repo `ichor/` GitHub privé, structure monorepo Turborepo
6. CI GitHub Actions stub vert
7. SOPS+age secrets setup
8. Cloudflare Access zero-trust sur `*.ichor.app`

**Semaine 2 — App squelettes + archivage critique** 9. **Cron systemd `ichor-archiver.service` HY/IG OAS J0** (priorité max) 10. FastAPI minimal `/healthz` deploy Hetzner 11. Next.js minimal Cloudflare Pages deploy `app.ichor.app` 12. Disclaimer modal + footer + dark mode toggle 13. Service worker PWA + VAPID push test 14. Logo + palette + mockups asset cards (canvas-design) 15. ElevenLabs Brian voix FR test 10 phrases finance 16. Persona Ichor v1 prompt + lexique phonétique v0 17. Script `scripts/check_api_keys.py` — toutes clés vertes

**Gate Phase 0 → Phase 1** : tous les 16 critères §8 cochés + revue Eliot.

---

## 15. Recommandation finale

✅ **SPEC.md écrit** : `D:\Ichor\SPEC.md` (~600 lignes)

**PROCHAINE ÉTAPE** :

1. **Eliot relit SPEC.md tranquillement** (15-20 min) — modifie/ajoute/supprime selon préférence
2. **Validation explicite** ou édition manuelle
3. **`/clear`** la session courante (contexte interview pollue Phase 0)
4. **Nouvelle session Claude Code** depuis `D:\Ichor\`
5. **Premier message** : « Implémente Phase 0 d'Ichor selon SPEC.md §8 et §14. Commence par Semaine 1, étape 1 (achat ichor.app), confirme avant chaque étape destructive (wipe Hetzner notamment). »

Pourquoi nouvelle session : le contexte d'interview (~30k tokens) pollue la phase implémentation. Une session vierge avec SPEC.md + ICHOR_PLAN.md comme références donne une qualité supérieure.

---

_Document maintenu par Claude. Mettre à jour à chaque évolution majeure de la spec ou des décisions._
