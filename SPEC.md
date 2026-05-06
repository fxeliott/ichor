# SPEC — Ichor Phase 2 (refonte + extension omnisciente)

**Date** : 2026-05-04
**Auteur** : Eliot (interview Claude Code via skill `/spec`)
**Statut** : prêt pour implémentation après `/clear` + nouvelle session
**Supersede** : aucune décision antérieure n'est annulée ; ce document étend l'app livrée Phase 1 Step 2 vers une cible « ultra-omnisciente » avec refonte frontend complète.
**Référence amont** : [`docs/SPEC.md`](docs/SPEC.md) (Phase 0 originale, conservée pour historique), [`docs/VISION_2026.md`](docs/VISION_2026.md), [`docs/ARCHITECTURE_FINALE.md`](docs/ARCHITECTURE_FINALE.md), [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md), [`docs/decisions/ADR-009-voie-d-no-api-consumption.md`](docs/decisions/ADR-009-voie-d-no-api-consumption.md), [`docs/decisions/ADR-017-reset-phase1-living-macro-entity.md`](docs/decisions/ADR-017-reset-phase1-living-macro-entity.md).

---

## 1. Vision en une phrase

Refonder Ichor en une **entité macro-omnisciente auto-évolutive de qualité institutionnelle premium** — frontend reconstruit from-scratch en design language custom expert (densité progressive, ultra-explicatif, vivant utile, desktop-first + mobile compagnon), backend densifié (14 modèles ML branchés au pipeline, 4 agents Couche-2 livrés via Claude Opus 4.7 local, gisement existant câblé, sources free tier maximales, Polymarket exploité à fond, auto-amélioration adaptive complète Brier→weights+drift+post-mortem+RAG, trader-UX alignée sur la stratégie momentum sessions Londres/NY d'Eliot avec RR3/BE@RR1/partial 90-10/trailing), ops durcies (URL stable, CI bloquant strict, monitoring complet) — **budget strict 200€ Max 20x + 49$ Massive Currencies, reste exclusivement free tier ou public data**.

## 2. Contexte

### 2.1 Ce qui est livré aujourd'hui (Phase 1 Step 2 — vérifié dans le code 2026-05-04)

- **Pipeline brain 4-pass + Pass 5 counterfactual** opérationnel, 8 frameworks asset, Critic Agent gate (alias matching robuste), Brier reconciler nightly.
- **27 sections data_pool** par run (vs 14 annoncées dans SESSION_HANDOFF qui n'a pas été re-synchro post-marathon), **~50 source-IDs distincts** stampés (FRED, Polygon, CFTC, Polymarket, Kalshi, Manifold, BIS, RSS, GDELT, AI-GPR).
- **24 pages web** Next.js 15, **14 composants UI** dans `@ichor/ui`, design cobalt+navy + ambient motion, push iOS VAPID, Cmd+K, raccourcis `?`, mobile drawer, time-machine slider, knowledge graph SVG, shock simulator, /learn 6 chapitres pédago.
- **35+ endpoints API** REST + 1 WebSocket dashboard.
- **11 timers systemd** (5 briefings + 4 collectors + 1 walg + 1 api ; le chiffre « 17 » du README inclut probablement des units-helpers non comptés ici).
- **17 cards persistées**, 76 % approval rate.
- **8 capabilities différenciantes** : 7/8 réellement live ; **divergence cross-venue codée mais non câblée** au pipeline (test unitaire OK, aucun router/CLI ne l'expose).

### 2.2 Ce qui ne fonctionne pas / dette identifiée (à fixer dans cette refonte)

| #   | Problème                                                                                                                             | Source vérifiée                                                                                              |
| --- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------- | -------------------------- |
| 1   | Frontend « pas clean, pas assez poussé, pas assez bien » → refonte from-scratch                                                      | dire d'Eliot 2026-05-04                                                                                      |
| 2   | `tunnel-config.yml` ingress sur `:8765` alors que runner user-mode tourne sur `:8766`                                                | `infra/cloudflare/tunnel-config.yml:14-15` vs `scripts/windows/start-claude-runner-user.ps1:18`              |
| 3   | Theme color triple incohérent (manifest `0a0a0b` / viewport `070B14` / CSS var `04070C`)                                             | `apps/web/public/manifest.webmanifest`, `app/layout.tsx:25`, `app/globals.css:12`                            |
| 4   | `redis_version: "8"` dans `group_vars/all.yml:14` alors que README ansible mentionne 7                                               | `infra/ansible/group_vars/all.yml:14`                                                                        |
| 5   | `postgres_archive_mode: "off"` en défaut, flip manuel attendu                                                                        | `infra/ansible/group_vars/all.yml:30`                                                                        |
| 6   | `claude_runner_url` default = `https://placeholder.cfargotunnel.com`                                                                 | `apps/api/src/ichor_api/config.py:40`                                                                        |
| 7   | `ExecStartPre` du briefing service appelle `ichor-decrypt-secrets` qui n'est nulle part dans le repo                                 | `scripts/hetzner/register-cron-briefings.sh:36`                                                              |
| 8   | `divergence` cross-venue codée mais aucun consommateur live                                                                          | `packages/agents/src/ichor_agents/predictions/divergence.py` ; grep `divergence` dans `apps/api/src` = 0 hit |
| 9   | `flashalpha` collecté sans table de persistance et non remonté au pool                                                               | `apps/api/src/ichor_api/collectors/flashalpha.py`, `cli/run_collectors.py:280-284`                           |
| 10  | `polygon_news` collecté mais pas filtré ticker-linked dans le pool                                                                   | `apps/api/src/ichor_api/services/data_pool.py:656-675`                                                       |
| 11  | `market_data` Stooq daily peuplé mais inexploité par le brain (utilise polygon_intraday seul)                                        | `data_pool.py:282-307`                                                                                       |
| 12  | **Tout `packages/ml` (HMM, FOMC-RoBERTa, FinBERT, VPIN, HAR-RV, DTW, ADWIN) déconnecté du pool brain**                               | aucun import depuis `services/data_pool.py`                                                                  |
| 13  | 4/5 agents Couche-2 vapor (Sentiment/Positioning/CB-NLP/News-NLP)                                                                    | `packages/agents/src/ichor_agents/__init__.py` annonce 5 agents, seul `agents/macro.py` codé                 |
| 14  | 6 modèles ML `planned` sans code (LightGBM, XGBoost, RF, Logistic, Bayesian-NumPyro, MLP-Torch)                                      | `packages/ml/model_registry.yaml:101-156`                                                                    |
| 15  | `sabr_svi.py:44-71` = stub explicite « Phase 0 placeholder, full impl Phase 1 — needs vollib »                                       | `packages/ml/src/ichor_ml/vol/sabr_svi.py`                                                                   |
| 16  | `narrative_tracker.py` = TF naïf alors que VISION delta J prévoyait BERTopic                                                         | commentaire `services/narrative_tracker.py:6-9`                                                              |
| 17  | `causal_propagation.py` Bayes-lite noisy-OR au lieu de pgmpy complet                                                                 | commentaire `services/causal_propagation.py:15`                                                              |
| 18  | `cb_intervention.py` V1 sigmoïde threshold-only, rhetoric weighting reporté V2                                                       | commentaire `services/cb_intervention.py:13`                                                                 |
| 19  | `auto-deploy.yml` non opérationnel (`HETZNER_SSH_PRIVATE_KEY` GitHub secret absent) → déploiements manuels par tar+ssh               | `SESSION_HANDOFF.md:218-220`                                                                                 |
| 20  | URL prod = quick tunnel `*.trycloudflare.com` (URL change à chaque restart) au lieu de `app-ichor.pages.dev` annoncé dans USER_GUIDE | `SESSION_LOG_2026-05-04.md:840-855`                                                                          |
| 21  | Aucun shipper Promtail/Vector → Loki tourne mais reçoit rien                                                                         | `infra/ansible/roles/observability/files/docker-compose.yml`                                                 |
| 22  | `postgres_exporter` scrapé par Prometheus mais aucun rôle ne l'installe                                                              | `infra/ansible/roles/observability/files/prometheus.yml:8-25`                                                |
| 23  | CI Phase 0 entièrement warn-only (`                                                                                                  |                                                                                                              | true`, `continue-on-error`) → aucune barrière qualité bloquante | `.github/workflows/ci.yml` |
| 24  | Aucun test sur les routers FastAPI (pas de tests d'intégration HTTP)                                                                 | `apps/api/tests/`                                                                                            |
| 25  | Brier feedback ne nourrit pas les confluence weights                                                                                 | `SESSION_LOG_2026-05-04.md:917-919`                                                                          |
| 26  | Pas de glossaire / pas de tooltips contextuels riches sur les pages live (seul `/learn` explique)                                    | audit frontend 2026-05-04                                                                                    |
| 27  | `lib/cmdk` listée dep mais palette handcrafted (dead dep)                                                                            | `apps/web/package.json`                                                                                      |
| 28  | `react-query` listée dep mais aucun `useQuery` repéré dans les composants lus                                                        | `apps/web/package.json`                                                                                      |
| 29  | Documentation contradictoire : 13 vs 24 pages, 14 vs 27 sections, 17 vs 11 timers, $249 vs $269 vs $200                              | comparaison SESSION_HANDOFF vs SESSION_LOG vs ADR-017                                                        |
| 30  | 9 collectors `Planned` non implémentés : BLS, ECB SDMX, EIA, BoE IADB, Treasury DTS, VIX live, AAII, Reddit WSB, FINRA SI/ATS        | `apps/api/src/ichor_api/collectors/__init__.py:22-37`                                                        |

### 2.3 Stratégie de trading d'Eliot (à matcher dans l'UX)

- **Style** : trade momentum des sessions de Londres et de New York.
- **Marchés** : forex majors, indices US, gold (XAU/USD).
- **Durée trade** : quelques minutes à quelques heures.
- **Timeframes analyse technique perso** : H1 / M30 / M15 / M5.
- **Setup AT** : recherche d'origine de mouvement passé sur les derniers jours, S/R + bougies pleines marquées, identification d'une zone d'origine vendeuse pour shorts ou acheteuse pour longs.
- **Risk management** :
  - RR cible minimum 3:1
  - Break-Even au RR 1:1
  - Clôture 90 % au RR 3:1
  - Trail des 10 % restants → cible RR 5:1, 10:1, 15:1+
- **Répartition** : analyse technique = 10 % de son process (lui sur TradingView) ; le reste (macro/géopolitique/sentiment/corrélations/positioning/options/CB-NLP) = 90 % qu'Ichor doit couvrir.
- **Rôle d'Ichor** : aider la décision pré-trade (go/no-go pour la session, calibration conviction, identification meilleurs actifs du jour, détection de catalysts, alertes invalidations) — **jamais** générer de signal d'entrée discrétionnaire.

### 2.4 Out-of-scope contractuel (rappel ADR-017)

Ichor ne fait **JAMAIS** : signal generator, backtest, paper trading, ML prédictif sur prix, exécution d'ordres, chiffre BUY/SELL tranchant. Living Macro Entity = pré-trade context only.

## 3. Décisions architecturales validées (Tour d'interview 2026-05-04)

### 3.1 Tout passe par Claude (changement structurel majeur)

- **Décision** : tous les agents (Couche-2 incluse) routent vers **Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5** via le runner local Win11 (Voie D, Max 20x flat $200).
- **Cerebras + Groq** restent installés mais en **fallback uniquement** (déclenchés si Claude Max banni / rate-limited persistant > 30 min).
- **Rationale** : Eliot considère Claude Opus 4.7 comme le meilleur modèle pour analyses macro complexes ; il préfère un seul cerveau premium plutôt que 5 modèles différents avec qualités hétérogènes.
- **Implication coût** : zéro additionnel ($200 flat couvre).
- **Risque ban Anthropic Max 20x** : assumé en conscience par Eliot (`ARCHITECTURE_FINALE.md:14-25`). Mitigation = cadencement strict (voir §3.2), batch sessions, Cerebras/Groq fallback prêt mais désarmé.

### 3.2 Cadencement Claude Max 20x (anti-ban)

| Cadence quotidienne               | Déclencheur                                                              | Modèle                                                            | Notes         |
| --------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------- | ------------- |
| 4 × session cards                 | cron 06h/12h/17h/22h Paris × 8 actifs                                    | Opus 4.7 (Pass 1+2+5), Sonnet 4.6 (Pass 3+4+Critic)               | déjà en place |
| 1 × post-mortem hebdo             | dimanche 18h Paris                                                       | Opus 4.7                                                          | nouveau       |
| 1 × méta-prompt tuning bi-mensuel | 1er + 15 du mois 03h Paris                                               | Opus 4.7                                                          | nouveau       |
| Couche-2 4 agents                 | toutes les 4h (CB-NLP, News-NLP), toutes les 6h (Sentiment, Positioning) | Sonnet 4.6 (CB-NLP, News-NLP), Haiku 4.5 (Sentiment, Positioning) | nouveau       |
| Counterfactual Pass 5             | on-demand UI                                                             | Opus 4.7                                                          | déjà en place |
| Crisis Mode briefing ad-hoc       | déclenché par alert composite                                            | Opus 4.7                                                          | déjà en place |

Total estimé : **~80 calls Claude/jour** (32 cards + 16 Couche-2 + 8 Pass-5 typiques + 1 weekly + ad-hoc). Reste sous le seuil empirique « ordinary individual use » de Max 20x.

### 3.3 Approche refonte frontend

- **Décision** : **from-scratch complet**. Construire `apps/web2/` neuf, migrer page par page, archiver `apps/web/` une fois `apps/web2/` à parité fonctionnelle, puis renommer.
- **Rationale d'Eliot** : « ultra ultra propre, ultra design, ultra bien structuré, intuitif, animations, fonctionnalités graphiques, schémas, illustrations, beaucoup de visuel, ultra explicatif, la perfection ».
- **Pas de bigbang** : `apps/web/` reste UP en parallèle pendant la migration ; deploy preview de `apps/web2/` sur sous-domaine `next.app-ichor.pages.dev` ou similaire pendant la phase de construction.

### 3.4 Design language cible

- **Décision** : **custom expert dérivé** — synthèse experte des trois familles :
  - Densité Bloomberg-tape (data-rich par drill-down)
  - Calme Linear/Stripe (espacement aéré sur la home et les listes)
  - Organique Anthropic-style (motion subtil, glassmorphism léger, palette chaude qui contre la froideur du financier classique)
- **Densité progressive 3 niveaux** :
  - **Home** très aérée — top 5 signaux essentiels du jour, ambient regime quadrant, best opportunities ranked
  - **Pages liste** mid-density — vue d'ensemble par axe (assets, alerts, briefings, sessions)
  - **Drill-down** dense Bloomberg-style — tout l'écosystème de données par actif/session/event
- **Palette héritée + densifiée** :
  - Conservation cobalt+navy actuel (`#3B82F6`, `#04070C` → `#16223A`)
  - Bias `long #34D399` / `short #F87171` / neutral `#94A3B8` conservés
  - **Ajout** d'une couleur tertiaire chaude (ambre `#FBBF24` ?) pour info/warning afin de casser la duotone bleu froid
  - **Réconciliation** des 3 theme color (manifest, viewport, CSS var) sur une seule valeur unique
- **Typographie** : Inter sans + JetBrains Mono mono **chargées via `next/font`** (vs fallback système actuel)
- **Motion** : « vivant utile » — keep ambient orbs régime-colorées, sparklines drawing, transitions de routes, pulse alerts critical, ticker live ; pas de wow factor cinématique gratuit
- **Dark only** confirmé (pas de toggle light)
- **Glass language** conservé (`.ichor-glass`, `.ichor-gradient-border`, `.ichor-grid-bg`)

### 3.5 Pédagogie ultra-explicative

- **Tooltips contextuels au survol** sur **toute métrique technique** : Brier, VPIN, Kyle λ, Amihud, conviction, OAS, GEX, IORB, SOFR, COT, dot plot, rate diff, real yield, breakeven, Sahm rule, etc.
- **Glossaire intégré** : page `/learn/glossary` recherchable + popover anchored sur chaque terme depuis n'importe quelle page.
- **Walkthrough first-time** : sur première visite (cookie / localStorage), tour guidé en 5 étapes (régime quadrant → session card → drill-down asset → alerts → /learn). Skip-able.
- **Page `/learn` enrichie** : passer de 6 chapitres à **12+** (ajouter : trade plan momentum sessions, RR explained, partial exit scheme, Polymarket reading, COT positioning, central banks pipeline, ML stack, Brier explained, Critic Agent role, counterfactual reasoning, divergence cross-venue, knowledge graph reading).
- **« Pourquoi je vois ça » contextuel** sur chaque widget : icône `(?)` qui ouvre une ligne d'explication courte (la viz ↔ le data ↔ pourquoi c'est utile pour ton trade).

### 3.6 Mobile / PWA — desktop-first + compagnon

- **Desktop** = cockpit complet (toutes pages, toute densité)
- **Mobile** = compagnon : push iOS, glance des dernières cards, alertes critical, vue résumé du jour, command palette (Cmd+K → équivalent gesture). Drill-downs profonds **non** disponibles mobile (`<MobileBlocker>` qui suggère « ouvre sur desktop »)
- **PWA** existante conservée + durcie : SW caching strategy révisée, manifest theme color réconcilié, badge API pour push count
- **Pas d'app native iOS/Android v1** (hors scope confirmé)

### 3.7 Auto-amélioration adaptive complète (« entité vivante »)

- **Brier outcomes → ajustement auto des weights** du confluence engine. Pipeline : reconciler nightly écrit `realized_*` → service `confluence_weights_optimizer` recalcule weights par asset+régime via descente de gradient simple (LR=0.05, contrainte sum=1, momentum 0.9) → applique au prochain run. Bornes [0.05, 0.5] par facteur pour éviter dégénérescence.
- **Drift régime ADWIN → alerte + recalibration** : ADWIN sur la série Brier 30j ; détection drift → alert `BIAS_BRIER_DEGRADATION` (existe déjà §2.1 catalog) + trigger `regime_recalibrate.py` qui re-ajuste les centroïdes HMM sur la fenêtre récente.
- **Post-mortem hebdo automatique** : dimanche 18h Paris, Claude Opus 4.7 lit les 7 derniers jours (cards, outcomes, divergences entre prédiction et réalisé, news qui ont fait bouger les actifs), produit un markdown `docs/post_mortem/{YYYY-Www}.md`. Pousse une notif PWA.
- **Méta-prompt tuning bi-mensuel** : 1er + 15 du mois 03h Paris, Claude Opus 4.7 lit les Critic findings des 14 derniers jours, propose des amendements ciblés des system prompts par pass (régime/asset/stress/invalidation). Diff rendu en PR GitHub auto, **pas de merge auto** — Eliot review.
- **RAG sur historique 5 ans** : toutes les cards persistées + outcomes + post-mortems + briefings indexés dans Postgres `pgvector` (extension). Embeddings via **`bge-small-en-v1.5` self-host** sur Hetzner CPU (pas Voyage). Au build du data_pool, retrieval top-5 cards similaires (par macro state) injecté dans le contexte Pass 1. Phase 2 si volume nécessite : passage à `bge-large-en-v1.5`.

### 3.8 Trader UX — alignée stratégie momentum sessions

- **Session cards enrichies** :
  - **Zone d'entrée estimée** : par actif, pour la session prochaine (calcul à partir de mechanisms + correlations + microstructure → Claude Pass 2 extension)
  - **SL invalidation** : niveau qui invalide le scénario (du `invalidation_conditions` Pass 4)
  - **TP RR3** : calculé à partir de `magnitude_pips_low/high`
  - **Cible RR15 trail** : multiplicateur sur magnitude
  - **Scheme partial 90/10** explicite dans la card
- **Page `/today`** (nouvelle) :
  - Best opportunities ranked du jour selon conviction × régime fit × confluence
  - Calendrier d'events filtré sur fenêtre H-4h → H+1h sessions Londres + NY
  - Checklist pre-session « go / no-go » 5 lignes (régime fit ? conviction > 60 ? confluence cohérente ? pas de calendrier conflit ? Polymarket pas en désaccord majeur ?)
- **Alerte 1h avant chaque session** : push iOS « Pre-Londres dans 1h — 3 best opps : EUR/USD long 72%, XAU/USD short 68%, NAS100 long 64% »
- **Mode « focus session »** sur `/sessions/[asset]` pendant la fenêtre active (Londres ou NY) — UI surligne la session courante, masque les autres timeframes

### 3.9 Polymarket — exploitation maximale

- Page `/polymarket` enrichie :
  - **Top movers 24h** (delta probabilité > 5pp)
  - **Whale bets** > $10K (depuis Polymarket trades feed, free API)
  - **Divergence cross-venue** câblée (utiliser `predictions/divergence.py` enfin) : Polymarket vs Kalshi vs Manifold sur même question normalisée → flag divergence > 10pp
  - **Theme impact mapping par actif** : densifier le service `polymarket_impact.py` existant (chaque marché → impact directional sur les 8 actifs avec strength 0-1)
  - **Time-machine sur predictions** : slider 7j / 30j sur les marchés clés (Fed cuts, recession, election) avec overlay des annonces officielles correspondantes
- **Alertes auto** : shift > 5pp en < 24h sur marchés watchlist (`POLYMARKET_PROBABILITY_SHIFT` existe, étendre la watchlist)
- **Alertes whales** : nouveau code alert `POLYMARKET_WHALE_BET` → push si bet > $50K en < 1h

### 3.10 Tests CI bloquant strict (rampe douce 4 semaines)

| Semaine | CI bloquant ajouté                                                                | Cumulatif   |
| ------- | --------------------------------------------------------------------------------- | ----------- |
| 1       | `ruff check` + `ruff format --check` + `eslint` + `prettier --check`              | lint        |
| 2       | `mypy --strict` + `tsc --noEmit`                                                  | + typecheck |
| 3       | `pytest` (couverture min 60% sur `services/`, `brain/`, `agents/`) + `vitest` web | + tests     |
| 4       | `pip-audit` + `pnpm audit --audit-level=high` + `trivy fs`                        | + audit     |

À la fin S4 : tout merge bloqué si l'un des 4 falls. Pré-commit hooks aussi locaux (déjà en place pour gitleaks + ruff + prettier).

### 3.11 Sources free tier — toutes incluses

| Groupe                      | Sources                                                                                                                                                                                                                | Rationale                                                                                |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Stats publiques officielles | BLS (emploi, inflation), ECB SDMX, EIA (pétrole STEO + weekly), BoE IADB (rates), Treasury DTS (cash flows quotidien), Treasury TIC (foreign holdings monthly), BIS public datasets, FINRA short interest + ATS weekly | 8 collectors planned du `__init__.py` à finir + Treasury TIC + BIS datasets              |
| Sentiment retail            | AAII Sentiment Survey CSV weekly, Reddit /r/wallstreetbets + /r/forex + /r/stockmarket + /r/Gold via PRAW OAuth                                                                                                        | Contrarian indicator hedge funds + détection memes/squeezes                              |
| Calendrier + options        | ForexFactory eco-calendar (scrape, fragile), yfinance options chains (gratuit limité, calc put/call ratio + IV skew + risk reversals empiriques)                                                                       | Combler `eco_calendar` planned + options market intel sans coût                          |
| NLP self-host               | HuggingFace `FinBERT-tone` + `FOMC-RoBERTa` + `gtfintechlab/FOMC-RoBERTa` + sentiment news models, `bge-small-en-v1.5` embeddings                                                                                      | Tous tournent CPU sur Hetzner, pas de coût API                                           |
| Tendances                   | Google Trends via `pytrends` (free, fragile API) sur watchlist : « recession », « inflation », « gold price », « EUR/USD », « Fed rate », noms d'actifs                                                                | Proxy attention publique                                                                 |
| Twitter/X (ciblé)           | API free 10k tweets/mo limite stricte → **whitelist comptes officiels uniquement** : @federalreserve, @ECB, @bankofengland, @bankofjapan, @SNB, @PBOC, @BIS_org, Powell speeches accounts, Lagarde, Bailey             | Pas d'analyse de sentiment grand-public, juste tracking discours officiels en temps réel |

### 3.12 14 modèles ML — branchement au pipeline

Ordre de branchement par valeur ajoutée décroissante (8 codés à connecter, 6 `planned` à coder ensuite) :

| Ordre | Modèle                                                       | Status code    | Branchement                                                                                                        | Pass impacté                                                   |
| ----- | ------------------------------------------------------------ | -------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| 1     | **HMM régime 3 états**                                       | scaffolded     | `data_pool` section `regime_ml` (latest state + posterior probs)                                                   | Pass 1 régime (corrobore le quadrant Claude)                   |
| 2     | **FOMC-RoBERTa**                                             | code OK        | `data_pool` section `cb_nlp` (hawkish/dovish score sur N derniers discours Fed)                                    | Pass 1 régime + Pass 2 (mechanisms si CB)                      |
| 3     | **FinBERT-tone**                                             | code OK        | `data_pool` section `news_nlp` (tone aggregate sur N derniers headlines par actif)                                 | Pass 2 asset (mechanisms catalysts)                            |
| 4     | **VPIN microstructure**                                      | code OK        | `data_pool` section `microstructure` (toxicity score live)                                                         | Pass 2 asset (timing window precision)                         |
| 5     | **DTW analogues**                                            | code OK        | `data_pool` section `analogues` (top 3 régimes passés similaires + leur outcome)                                   | Pass 1 + Pass 3 stress (counter-claims via analogues passés)   |
| 6     | **HAR-RV vol forecast**                                      | code OK        | `data_pool` section `vol_forecast` (J+1 RV)                                                                        | Pass 2 asset (magnitude_pips ranges)                           |
| 7     | **ADWIN drift detector**                                     | code OK        | service standalone qui émet alert `CONCEPT_DRIFT_DETECTED`                                                         | Cross-cutting                                                  |
| 8     | **SABR-SVI** (à finir)                                       | stub explicite | Pass 2 asset XAU/indices (IV skew alerts si options data brancée)                                                  | nécessite vollib install                                       |
| 9-14  | LightGBM, XGBoost, RF, Logistic, Bayesian-NumPyro, MLP-Torch | planned        | Bias Aggregator EUR/USD 1h forecast → service `bias_aggregator` qui injecte une 5e source dans `confluence_engine` | Pass 2 EUR/USD initialement, étendre aux autres actifs ensuite |

### 3.13 4 agents Couche-2 — livrés via Claude

Tous routent par le runner local Max 20x. Cadence cf §3.2.

| Agent           | Modèle     | Cadence       | Input                                                                                         | Output                                                                                               |
| --------------- | ---------- | ------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **CB-NLP**      | Sonnet 4.6 | toutes les 4h | derniers discours/communiqués Fed/ECB/BoE/BoJ/SNB/PBoC depuis `cb_speeches`                   | hawkish/dovish score per CB + key shifts identifiés + impact projeté par actif (rate-sensitive)      |
| **News-NLP**    | Sonnet 4.6 | toutes les 4h | dernières news (RSS + GDELT + polygon_news) clusterisées par thème via FinBERT-tone           | top 5 narratives du moment + sentiment per asset + entity extraction (companies, countries, persons) |
| **Sentiment**   | Haiku 4.5  | toutes les 6h | AAII weekly + Reddit WSB+forex+stockmarket+Gold last 6h + Google Trends watchlist             | sentiment retail global + extremes contrarian flags + thématiques émergentes                         |
| **Positioning** | Haiku 4.5  | toutes les 6h | COT positions (latest weekly), FlashAlpha GEX live, Polymarket whales, IV skew options chains | positioning extrêmes par asset + dealer gamma flip risk + smart money divergence vs retail           |

Sortie de chaque agent → table dédiée + section data_pool dédiée → consommée Pass 1+2.

### 3.14 Connexion gisement existant — quick wins

| Quick win                                                                       | Fichier                                                                                             | Effort estimé   |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | --------------- |
| Câbler `divergence` cross-venue au pool + endpoint `/v1/divergences` + page UI  | `packages/agents/.../divergence.py` → `apps/api/.../routers/divergence.py` + `data_pool.py` section | 1 jour          |
| Persister FlashAlpha GEX (table + collector ↔ persist) + remonter au pool       | nouveau `migrations/0008_gex_snapshots.py` + `flashalpha.py` persist + `data_pool.py` section gex   | 1 jour          |
| Filtrer `polygon_news` ticker-linked dans le pool (section asset-specific news) | `data_pool.py:656-675`                                                                              | 0.5 jour        |
| Brancher `market_data` Stooq daily pour DTW analogues historiques 10+ ans       | `services/analogues.py` (nouveau) + `data_pool.py` section                                          | 1 jour          |
| Implémenter les 8 collectors `Planned` restants                                 | `collectors/{bls,ecb_sdmx,eia,boe_iadb,treasury_dts,vix_live,aaii,reddit_wsb,finra}.py`             | 4-5 jours total |

## 4. Stack technique (figée — ne pas réinventer)

| Couche            | Choix                                                                                                                                                                                                                                                              | Notes                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| Backend runtime   | Python 3.12 (Hetzner) / 3.14 (Win11 tooling)                                                                                                                                                                                                                       | conservé                                                    |
| Backend framework | FastAPI                                                                                                                                                                                                                                                            | conservé                                                    |
| API client        | `orval` depuis OpenAPI (à mettre en place dans `apps/web2/`)                                                                                                                                                                                                       | nouveau pour la refonte                                     |
| Frontend          | Next.js 15 App Router                                                                                                                                                                                                                                              | conservé                                                    |
| Frontend lib      | `motion` 12 (framer successor), `lightweight-charts` 5, `react-markdown` + `remark-gfm`, `zustand`, **`@tanstack/react-query` réellement utilisé** (vs déclaré inutilisé), **drop `cmdk` dead dep si palette reste handcrafted** ou re-baser la palette sur `cmdk` | normaliser                                                  |
| CSS               | Tailwind v4 PostCSS                                                                                                                                                                                                                                                | conservé, `@theme` dans `globals.css`                       |
| Composants        | `@ichor/ui` étendu — refondu en design system propre Phase 2                                                                                                                                                                                                       | reconstruire                                                |
| Charts avancés    | candidats : `visx`, `d3` ciblé, `recharts` — pour heatmap interactives, force-graph, globe 3D `react-globe.gl` (delta Q VISION)                                                                                                                                    | à choisir lors de la refonte                                |
| KG viz            | `react-force-graph` (delta K originalement prévu vs SVG actuel)                                                                                                                                                                                                    | upgrade prévue                                              |
| State             | Zustand + TanStack Query                                                                                                                                                                                                                                           | use both                                                    |
| Tests web         | Vitest + Playwright E2E                                                                                                                                                                                                                                            | nouveau Playwright                                          |
| DB                | PG 16 + TimescaleDB 2.26 + Apache AGE 1.5                                                                                                                                                                                                                          | conservé                                                    |
| Cache             | Redis 8.6 AOF                                                                                                                                                                                                                                                      | conservé (rectifier doc 7→8)                                |
| Embeddings        | **`bge-small-en-v1.5` self-host** Hetzner CPU                                                                                                                                                                                                                      | nouveau                                                     |
| Vector store      | `pgvector` extension Postgres                                                                                                                                                                                                                                      | nouveau                                                     |
| Backup            | wal-g 3.0.8 → R2 EU                                                                                                                                                                                                                                                | conservé                                                    |
| Tunnel            | cloudflared user-mode :8766                                                                                                                                                                                                                                        | corriger config :8765→:8766                                 |
| Secrets           | sops 3.12 + age 1.3                                                                                                                                                                                                                                                | conservé + créer le `ichor-decrypt-secrets` script manquant |
| LLM principal     | Claude Opus 4.7 + Sonnet 4.6 + Haiku 4.5 via Max 20x runner local                                                                                                                                                                                                  | confirmé Voie D                                             |
| LLM fallback      | Cerebras + Groq free tiers (uniquement si Claude banni / rate-limit > 30 min)                                                                                                                                                                                      | downgraded de primary à fallback                            |
| ML                | hmmlearn, dtaidistance, river (ADWIN), HuggingFace transformers (FinBERT, FOMC-RoBERTa), LightGBM, XGBoost, sklearn, NumPyro/PyMC, PyTorch (MLP)                                                                                                                   | conservé                                                    |

## 5. Phases d'implémentation (4 phases en parallèle ambitieux)

> Eliot a explicitement demandé « tout backend à la perfection EN PARALLÈLE de frontend perfection ». Les 4 phases tournent simultanément après une semaine 0 de bootstrap commun.

### Semaine 0 — Bootstrap commun (avant les 4 phases)

- Init `apps/web2/` Next.js 15 + Tailwind v4 + shadcn/ui base + design tokens (palette + typo + motion)
- Installer `pgvector` + `bge-small-en-v1.5` self-host
- Créer migration `0008_gex_snapshots.py` + `0009_couche2_outputs.py` + `0010_post_mortems.py` + `0011_pgvector_setup.py` + `0012_confluence_weights_history.py`
- Setup CI rampe S1 (lint bloquant)
- Fix les 5 bugs critiques (tunnel port, theme color triple, claude_runner_url placeholder, secrets script absent, redis version doc)

### Phase A — Frontend redesign from-scratch (8-10 semaines)

Pages migrées dans cet ordre (chaque migration = `apps/web2/` page complète + design system enrichi + pédagogie + tests Playwright) :

1. `/` Home — densité progressive niveau aérée + best opps + macro pulse + ambient regime
2. `/today` (nouveau) — best opps ranked + checklist pre-session + alerte 1h
3. `/sessions` + `/sessions/[asset]` — trade plan complet aligné stratégie momentum
4. `/scenarios/[asset]` — 7 scénarios + Pass 5 trigger
5. `/replay/[asset]` — time-machine slider durci
6. `/calibration` — Brier reliability diagram pédagogique
7. `/macro-pulse` + `/yield-curve` + `/correlations` — densité mid
8. `/polymarket` — exploitation maximale (whales, divergence, time-machine pred markets)
9. `/knowledge-graph` — `react-force-graph` upgrade depuis SVG
10. `/geopolitics` — `react-globe.gl` 3D upgrade depuis equirectangular
11. `/narratives` + `/learn` (12+ chapitres) + `/learn/glossary` (nouveau)
12. `/assets` + `/assets/[code]` — drill-down dense Bloomberg-style
13. `/briefings` + `/news` + `/alerts` — listes mid-density
14. `/admin` + `/sources` — dense

Walkthrough first-time + tooltips contextuels + glossaire intégré ajoutés en transverse.

À la fin de Phase A : `apps/web/` archivé en `archive/web_legacy_v1/`, `apps/web2/` renommé en `apps/web/`.

### Phase B — Connexion gisement existant (3-4 semaines)

- Quick wins § 3.14 (5 items, 7-8 jours)
- Branchement des 8 modèles ML codés au pipeline brain (§3.12 ordre 1-8) — 1 modèle / 2-3 jours
- Couche-2 : 4 agents livrés via Claude (§3.13) — 1 agent / semaine

### Phase C — Sources free tier maximales (3-4 semaines)

- 8 collectors `Planned` à coder (§3.11 stats publiques) — 1 collector / 0.5 jour
- AAII + Reddit WSB collectors (§3.11 sentiment retail) — 2 jours
- ForexFactory eco-calendar scrape + yfinance options chains — 2 jours
- pytrends Google Trends — 1 jour
- Twitter/X whitelist CB officials — 2 jours
- Embeddings + RAG historique 5 ans (`pgvector` + ingestion + retrieval) — 1 semaine
- Auto-amélioration adaptive (§3.7) — 1 semaine (Brier→weights, drift→alert, post-mortem auto, méta-prompt tuning)

### Phase D — Ops hardening (2-3 semaines, en parallèle des phases A/B/C)

- **URL stable** : Cloudflare Pages auto-deploy `apps/web2/` → `app-ichor.pages.dev` (puis `ichor.app` si domaine acheté), retirer le quick tunnel `*.trycloudflare.com`
- **GitHub Action `auto-deploy.yml`** : ajouter `HETZNER_SSH_PRIVATE_KEY` secret, tester déploiement automatique sur push main
- **Promtail / Vector** : déployer un shipper logs vers Loki (ansible role)
- **`postgres_exporter`** : ajouter le rôle ansible + le scraper dans `prometheus.yml` (ou retirer la config de scrape si on garde sans)
- **CI rampe S1→S4** (§3.10) — lint → typecheck → test → audit
- **Tests intégration HTTP routers FastAPI** : couvrir les 35+ endpoints
- **Script `ichor-decrypt-secrets`** : à écrire (currently missing → systemd ExecStartPre échoue au boot)
- **Documentation resync** : SESSION_HANDOFF + PHASE_1_LOG + USER_GUIDE alignés sur l'état réel post-marathon (24 pages, 27 sections, 11 timers, coût exact)
- **Runbooks manquants** : RUNBOOK-012 (Cloudflare quick tunnel down), RUNBOOK-013 (Claude Max quota saturé)

## 6. Comportement attendu — happy paths

### 6.1 Matin Eliot pré-Londres (07h-08h Paris)

1. Cron 06h00 Paris déclenche `run_session_card.py` × 8 actifs (parallel batch)
2. Chaque card flow brain 4-pass → Critic gate → persistance
3. Cron 06h05 → push iOS « 8 cards Pre-Londres prêtes — best opp : EUR/USD long 72% »
4. Eliot ouvre l'app → `/today` → voit best opps ranked du jour + checklist pre-session
5. Drill-down sur best opp → `/sessions/EUR_USD` → trade plan complet (entry zone + SL + TP@RR3 + RR15 trail + scheme partial 90/10) + mechanisms + catalysts + Polymarket overlay + counterfactual button
6. (optionnel) Eliot clique counterfactual « what if Powell hawkish surprise this morning ? » → Pass 5 lance, 30s plus tard la counterfactual reading apparaît dans la même page
7. Eliot ouvre TradingView, fait son analyse technique 10% perso, prend ou pas le trade

### 6.2 Détection Crisis Mode

1. VIX +30% intraday détecté par alerts engine (règle `VIX_PANIC` + composite)
2. Push iOS instantané « CRISIS MODE — VIX +32%, HY OAS widen, 3 alerts critical »
3. UI top bar passe rouge, dashboard reorganisé pour mettre cross-asset stress en haut, ambient regime quadrant force focus sur funding_stress
4. Briefing Crisis ad-hoc déclenché (Claude Opus 4.7) → notification quand prêt
5. Card live mise à jour dans les 5 minutes via WebSocket

### 6.3 Post-mortem hebdo

1. Dimanche 18h Paris, cron `post_mortem_weekly.py` lance
2. Claude Opus 4.7 lit les 7 derniers jours (cards, outcomes, news, divergences)
3. Produit `docs/post_mortem/2026-W18.md` (structure standardisée : top hits, top miss, drift detected, narratives qui ont émergé, calibration drift, suggestions amendments)
4. Push iOS « Post-mortem semaine 18 prêt »
5. Page UI `/post-mortems` (nouvelle) liste l'historique

### 6.4 Méta-prompt tuning bi-mensuel

1. 1er du mois 03h Paris, cron `meta_prompt_tuning.py` lance
2. Claude Opus 4.7 lit les 14 derniers jours de Critic findings
3. Propose des amendements ciblés des system prompts par pass
4. **Crée une PR GitHub auto** avec les diffs (label `auto:meta-prompt-tuning`)
5. Aucun merge auto, Eliot review en console GitHub

## 7. Edge cases & erreurs

| Cas                                       | Comportement attendu                                                                                                                                                      |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Claude Max 20x rate-limit / 429           | retry 3× backoff, puis fallback Cerebras (Macro/Sentiment/Positioning) ou Groq (CB-NLP/News-NLP), log Langfuse, alert Grafana ; si > 30 min persistant → email/push Eliot |
| Claude Max 20x ban (compte révoqué)       | déclenchement runbook `RUNBOOK-008-anthropic-key-revoked.md` + bascule complète Cerebras+Groq + alert critical                                                            |
| Forex source down (Polygon/Stooq)         | switch yfinance fallback (déjà ADR-012), badge `<SourceBadge variant="stale">` UI                                                                                         |
| FRED rate-limit                           | exponential backoff, cache Redis 6h ; OAS HY/IG critique → alerte si gap > 24h                                                                                            |
| Polymarket API renamed (RUNBOOK-005)      | wrapper bascule, freeze divergence détection le temps de re-mapper                                                                                                        |
| WebSocket déconnexion                     | reconnect exponential backoff + replay missed events via REST `/v1/events?since=`                                                                                         |
| Brier dégradation > 15% sur 7j            | trigger ré-entraînement weights, alert `BIAS_BRIER_DEGRADATION` (existe), si persistance 60j → revue manuelle hebdo automatique                                           |
| Concept drift ADWIN détecté               | switch sur model challenger, baseline reste comparé 30j, alert `CONCEPT_DRIFT_DETECTED`                                                                                   |
| Prompt injection détectée dans source NLP | sanitization (control chars, markdown injections, max length, watchlist patterns) ; pattern récurrent → blacklist source ; runbook `RUNBOOK-006-prompt-injection.md`      |
| Cloudflare quick tunnel down              | bascule URL stable Pages (déployée Phase D), runbook nouveau `RUNBOOK-012`                                                                                                |
| Mobile drill-down profond                 | `<MobileBlocker>` qui suggère « ouvre sur desktop » avec lien email-self du link courant                                                                                  |
| pgvector retrieval lent (> 2s)            | EXPLAIN ANALYZE auto-archivé, circuit breaker côté FastAPI, retry sans RAG                                                                                                |
| Twitter/X API quota épuisé (10k/mo)       | fallback : pause collecte jusqu'au prochain reset, bandeau UI « Twitter sources stale »                                                                                   |
| HuggingFace model download échoue         | retry, cache modèle déjà téléchargé, alert ops                                                                                                                            |

## 8. Critères d'acceptation Phase 2 globale

Phase 2 est **done** quand TOUS ces critères passent :

### 8.1 Frontend

- [ ] `apps/web2/` à parité fonctionnelle avec `apps/web/` actuelle (24 pages migrées)
- [ ] Design system custom expert dérivé documenté en Storybook (ou équivalent) avec 14+ composants
- [ ] Tooltips contextuels sur 100% des métriques techniques
- [ ] Glossaire `/learn/glossary` recherchable + 12+ chapitres `/learn`
- [ ] Walkthrough first-time fonctionnel sur première visite
- [ ] Mode focus session pendant Londres / NY
- [ ] PWA mobile compagnon : push iOS testé + glance + alerts critical
- [ ] Theme color réconcilié (un seul `#xxxxxx` partout)
- [ ] Lighthouse score ≥ 95 sur Performance / Accessibilité / Best practices / SEO
- [ ] WCAG 2.2 AA validé sur 5 pages représentatives
- [ ] Tests Playwright E2E sur 3 happy paths (matin Eliot, drill-down asset, counterfactual)

### 8.2 Backend

- [ ] 8 modèles ML codés branchés au data_pool brain (HMM, FOMC-RoBERTa, FinBERT, VPIN, DTW, HAR-RV, ADWIN, SABR-SVI fini)
- [ ] 6 modèles ML `planned` codés (LightGBM, XGBoost, RF, Logistic, Bayesian, MLP) sur EUR/USD au minimum
- [ ] 4 agents Couche-2 livrés via Claude (CB-NLP, News-NLP, Sentiment, Positioning) avec cadence et persistance
- [ ] Divergence cross-venue câblée + endpoint + UI
- [ ] FlashAlpha GEX persisté + remonté au pool
- [ ] polygon_news filtré ticker-linked dans le pool
- [ ] market_data Stooq daily branché en analogues historiques DTW
- [ ] 8 collectors `Planned` codés (BLS, ECB SDMX, EIA, BoE IADB, Treasury DTS, VIX live, AAII, Reddit WSB, FINRA SI/ATS)
- [ ] AAII + Reddit + ForexFactory + yfinance options + pytrends + Twitter/X whitelist CB collectors codés
- [ ] HuggingFace FinBERT-tone + FOMC-RoBERTa self-host inference fonctionnels
- [ ] pgvector + bge-small-en-v1.5 self-host + RAG historique 5 ans branché Pass 1
- [ ] Auto-amélioration : Brier→weights opérationnel, ADWIN drift→alert, post-mortem hebdo, méta-prompt PR auto
- [ ] Trader UX backend : zone d'entrée + SL + TP@RR3 + RR15 trail + scheme 90/10 dans SessionCard schema
- [ ] Polymarket exploitation maximale : whales, divergence, time-machine pred markets, theme impact densifié

### 8.3 Ops

- [ ] URL stable production (Pages auto-deploy)
- [ ] `auto-deploy.yml` opérationnel (HETZNER_SSH_PRIVATE_KEY configuré)
- [ ] Promtail/Vector → Loki shipping logs
- [ ] postgres_exporter installé OU scrape config retirée
- [ ] CI bloquant strict S4 atteint (lint + typecheck + test + audit)
- [ ] Tests intégration HTTP sur 35+ endpoints
- [ ] Script `ichor-decrypt-secrets` écrit et testé
- [ ] SESSION_HANDOFF + PHASE_1_LOG + USER_GUIDE resync sur état réel
- [ ] RUNBOOK-012 (CF quick tunnel down) + RUNBOOK-013 (Max quota saturé) écrits
- [ ] Tunnel-config port aligné sur :8766
- [ ] Theme color réconcilié manifest/viewport/CSS

### 8.4 Qualité

- [ ] Brier score skill > 0.10 vs naive sur 30 derniers jours
- [ ] Approval rate Critic > 80% (vs 76% actuel)
- [ ] Couverture tests > 70% sur services critiques
- [ ] Aucun TODO/FIXME critical en suspens
- [ ] Documentation contradictoire éliminée (un seul chiffre source de vérité par métrique)

## 9. Hors scope v1 (différé v2/v3)

- App native iOS / Android sur app store (PWA suffit v1)
- Voice TTS Azure FR matinal (Sprint N VISION_2026)
- Backtest framework / paper trading / signal generator (interdit ADR-017, jamais)
- Multi-tenant scaffold (single-user Eliot v1)
- 12 actifs supplémentaires au-delà des 8 actuels (v2)
- Voice Q&A bidirectionnel (v3)
- DuckDB analytics layer (si volume nécessite)
- BERTopic full vs current keyword TF tracker (upgrade ciblé v2 si narrative tracker insuffisant)
- pgmpy complet vs Bayes-lite noisy-OR causal (Phase 3)
- Rhetoric weighting CB intervention V2 (au-delà des sigmoïdes thresholds)

> **Agent 24/7 event-driven persistant** = **INCLUS dans v1** (Sprint P originalement Phase 4) car cohérent avec l'auto-amélioration adaptive complète demandée.

## 10. Risques & mitigations

| Risque                                                      | Probabilité              | Impact                       | Mitigation                                                                                                                                                                                                             |
| ----------------------------------------------------------- | ------------------------ | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Claude Max 20x ban                                          | moyenne (zone grise ToS) | critical (Voie D = Max only) | Cerebras + Groq fallback prêts, RUNBOOK-008                                                                                                                                                                            |
| Scope creep (ambition Eliot « tout perfection »)            | haute                    | risque temporel (mois)       | Phases A/B/C/D bornées, gate clair §8 par sous-phase, post-mortem hebdo Claude pour rester aligné                                                                                                                      |
| Perte de données pendant migration `apps/web` → `apps/web2` | basse                    | moyen                        | Pas de bigbang, deux apps tournent en parallèle, archive sur git                                                                                                                                                       |
| Performance dégradée par 14 modèles ML branchés             | moyenne                  | moyen                        | Cache Redis sur ML inference, lazy load par section pool, profiling avant/après                                                                                                                                        |
| pgvector retrieval lent en production                       | moyenne                  | bas-moyen                    | **Index HNSW m=16 ef_construction=64** (cf. `docs/SPEC_V2_AUTOEVO.md` §1.3 ; pgvector 0.7+ benchmarks 30× QPS vs ivfflat à 99 % recall), embeddings small (bge-small 384d), hybrid RRF k=60 (dense + BM25), top-5 only |
| Reddit/Twitter scrape bloqué                                | moyenne                  | bas                          | Multiples user-agents rotation, cache 1h, fallback gracieux                                                                                                                                                            |
| ForexFactory scrape DOM cassé                               | haute                    | bas                          | Best-effort, fallback investing.com, marqué `stale` UI                                                                                                                                                                 |
| HuggingFace download timeout sur Hetzner CPU                | basse                    | bas                          | Cache local + fallback model versions older                                                                                                                                                                            |
| Méta-prompt tuning auto produit régression silencieuse      | moyenne                  | moyen                        | Pas de merge auto, PR GitHub label `auto:meta-prompt-tuning` review humain obligatoire                                                                                                                                 |
| Brier optimizer dégénère sur weights                        | basse                    | moyen                        | Bornes [0.05, 0.5] + LR cap + sanity check sum=1 ± 0.01                                                                                                                                                                |

## 11. Décisions documentées (récap)

| Sujet                  | Choix                                                                                                                              | Rationale                                                           |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Refonte frontend       | from-scratch `apps/web2/`, migration page par page                                                                                 | Eliot : « ultra propre, ultra design, ultra structuré, perfection » |
| Design language        | custom expert dérivé Bloomberg/Linear/Anthropic                                                                                    | flexibilité + ne pas singer                                         |
| Densité info           | progressive 3 niveaux (home aérée → liste mid → drill dense)                                                                       | meilleur compromis trader pro × débutant                            |
| Pédagogie              | ultra-explicative (tooltips + glossaire + walkthrough + /learn 12+)                                                                | Eliot débutant motivé, app doit enseigner                           |
| Mobile                 | desktop-first + mobile compagnon PWA                                                                                               | trader principalement desktop, mobile pour push/glance              |
| Animations             | « vivant utile »                                                                                                                   | éviter wow factor cinématique gratuit                               |
| LLM Couche-2           | tout via Claude (Opus 4.7 + Sonnet 4.6 + Haiku 4.5) Max 20x                                                                        | Eliot : « Claude est le meilleur, exploite-le au maximum »          |
| Cerebras/Groq          | downgraded de primary à fallback                                                                                                   | conservés pour cas ban Anthropic                                    |
| ML branchement         | par valeur ajoutée décroissante (HMM > FOMC-RoBERTa > FinBERT > VPIN > DTW > HAR-RV > ADWIN > SABR-SVI > 6 planned)                | impact pipeline brain max d'abord                                   |
| Sources free tier      | TOUTES (publiques officielles + sentiment retail + calendrier+options + NLP self-host + Trends + Twitter ciblé CB officials)       | Eliot : « omniscient sur tout, le maximum »                         |
| Polymarket             | exploitation maximale (whales, divergence cross-venue, time-machine pred, theme impact densifié)                                   | Eliot : « gros outil d'analyse si on s'en sert bien »               |
| Auto-amélioration      | adaptive complète (Brier→weights + drift→alert + post-mortem hebdo Claude + méta-prompt tuning + RAG 5 ans)                        | Eliot : « entité vivante »                                          |
| Trader UX              | trade plan complet aligné (entry zone + SL + TP@RR3 + RR15 trail + scheme 90/10 + page /today + checklist pre-session + alerte 1h) | Eliot : stratégie momentum sessions Londres/NY explicite            |
| Tests CI               | bloquant strict avec rampe douce S1→S4                                                                                             | « perfection » nécessite barrière qualité                           |
| Sources free Twitter/X | whitelist CB officials uniquement (pas grand public)                                                                               | quota strict 10k/mo, valeur signal vs bruit                         |
| Embeddings             | `bge-small-en-v1.5` self-host pgvector                                                                                             | gratuit, suffisant 384d, Hetzner CPU                                |
| Voice TTS              | reporté v2                                                                                                                         | hors scope v1 explicite                                             |
| App native mobile      | reporté v2                                                                                                                         | PWA suffit, store ROI faible vs effort                              |
| Backtest/signal        | INTERDIT                                                                                                                           | ADR-017 non-négociable                                              |
| Agent 24/7 persistant  | INCLUS v1 (Sprint P avancé depuis Phase 4)                                                                                         | cohérent avec auto-amélioration adaptive complète                   |
| Domaine prod           | `app-ichor.pages.dev` puis `ichor.app` si acheté                                                                                   | URL stable                                                          |

## 12. Notes

- **Documentation à resyncer** en parallèle Phase D : SESSION_HANDOFF.md, PHASE_1_LOG.md, USER_GUIDE.md, README.md doivent tous refléter l'état réel (24 pages, 27 sections data_pool, 11 timers explicites, coût exact). Aujourd'hui ils se contredisent.
- **Tunnel UUID hardcodé** dans `scripts/windows/start-cloudflared-user.ps1:8` (`97aab1f6-bd98-4743-8f65-78761388fe77`) → externaliser dans `infra/secrets/cloudflare.env` chiffré SOPS.
- **NSSM scripts orphelins** (`install-claude-runner-service.ps1`) à archiver puisque user-mode est la voie validée.
- **Backtest_runs orphelin** (migration 0004 conservée, ORM archivé, table morte) → décider à la fin Phase 2 si on écrit `0013_drop_backtest_runs.py` ou si on garde par sûreté.
- **Le SPEC original `docs/SPEC.md`** est conservé comme archive historique Phase 0. Il **N'EST PAS** la référence courante. Cette spec (`SPEC.md` racine) supersede.
- **Le mapping ADR-009 (Voie D) reste non-négociable** : pas d'API consommation Anthropic, le cadencement strict §3.2 + le fallback Cerebras/Groq permettent de tenir.
- **Eliot a explicitement validé** (interview 2026-05-04) chaque décision §3 ; aucune décision ici n'est suggérée sans son OK.

## 13. Recommandation finale

**SPEC ÉCRITE** : `D:\Ichor\SPEC.md` (~13 sections, ~700 lignes denses).

**PROCHAINE ÉTAPE** :

1. **Eliot relit SPEC.md tranquillement** (15-20 min) — modifie / ajoute / supprime selon préférence.
2. **Validation explicite** ou édition manuelle.
3. **`/clear`** la session courante (le contexte d'interview + audit 2026-05-04 pollue la phase implémentation).
4. **Nouvelle session Claude Code** depuis `D:\Ichor\` avec premier message :

   ```
   Implémente Phase 2 d'Ichor selon SPEC.md.
   Commence par Semaine 0 — Bootstrap commun (§5, avant les 4 phases).
   Confirme avant chaque commande destructive ou réseau sortante.
   Référence rapide : VISION_2026.md, ADR-017, ADR-009.
   ```

5. Pour la Phase A (frontend redesign), invoquer le subagent `ui-designer` + skills `canvas-design` / `brand-guidelines` + outils `claude-design` selon la phrase d'Eliot 2026-05-04.

Pourquoi nouvelle session : le contexte d'interview (~50k tokens) + audit profond (~50k tokens additionnels via 5 subagents researcher) pollue la phase implémentation. Une session vierge avec SPEC.md comme référence donne une qualité supérieure et évite la dérive de fin de session que tu as observée toi-même.

---

## 14. Annexes techniques densifiées (2026-05-04)

5 compagnons écrits dans `docs/SPEC_V2_*.md` apportent les détails que ce SPEC survole. Ils sont issus de 5 subagents researcher web 2026 (lectures sourcées Stripe, Bloomberg, Vercel/Geist, Anthropic, IBM CVD-safe, Linear, Aladdin, OpenBB, TradingView, joshyattridge/SMC, Bridgewater, Two Sigma, pgvector 0.7+ benchmarks, RAGAS, DSPy, PostHog, Plausible, Langfuse, OWASP, Hypothesis, Playwright, k6, blue-green systemd, Alembic zero-downtime, Changesets, Storybook 8, syft+grype). Ils sont **autoritaires sur leur scope** — en cas de conflit avec les sections 1-13 ci-dessus, ce sont eux qui gagnent.

| Compagnon                                                | Scope                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Override clé sur SPEC.md principal                                                                                                                                                                                                                                                                                                                             |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`docs/SPEC_V2_DESIGN.md`](docs/SPEC_V2_DESIGN.md)       | Design tokens (palette CVD-safe + typo Geist + spacing/radius/shadow/motion/z-index scales), architecture info par page, comparatif inspirations, anatomie 14 composants existants + 10 nouveaux, micro-interactions, accessibilité WCAG 2.2 AA, animation principles, mobile gates+gestures, anti-patterns                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Bull/bear bleu/orange (CVD-safe) au lieu de vert/rouge ; typographie Geist + Fraunces vs Inter ; densité progressive 3 niveaux concrétisée                                                                                                                                                                                                                     |
| [`docs/SPEC_V2_TRADER.md`](docs/SPEC_V2_TRADER.md)       | SMC algorithmiques (OB, FVG, liquidity sweep, BoS/CHoCH) via lib MIT, multi-timeframe synthesis D1→M15, volume profile par session, CVD futures (verdict honnête), liquidity heatmap, Tokyo fix, order flow profiling, 7 facteurs confluence supplémentaires, anti-confluence flag, format SessionCard institutionnel, hedge funds capabilities mappable                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Format SessionCard 8 blocs Goldman/JPM ; ajout `services/smart_money_structure.py` + `volume_profile.py` + `liquidity_heatmap.py` + `tokyo_fix.py` ; pricing Polygon Currencies $49 **à reconfirmer 2026** (search ne le retrouve pas, voir §1.3.4 du compagnon)                                                                                               |
| [`docs/SPEC_V2_SOURCES.md`](docs/SPEC_V2_SOURCES.md)     | 60 sources free tier sourcées avec URL/quota/format/risque ; top 20 priorités Phase 2 ; 8 sources à éviter ; comparatif HF reproductible vs impossible ; architecture collecte 10 collectors prioritaires ; risques légaux/TOS                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Twitter/X **n'a plus de free tier** depuis fév 2026 → remplacer par Bluesky + Mastodon ; Glassnode free tier inadapté (gated Pro) ; **OpenBB Platform** comme wrapper unifié (pattern à emprunter)                                                                                                                                                             |
| [`docs/SPEC_V2_AUTOEVO.md`](docs/SPEC_V2_AUTOEVO.md)     | RAG state-of-art (chunking 1 card = 1 chunk, BGE-small ONNX/TEI, **HNSW pas ivfflat**, hybrid RRF, reranker BGE-v2-m3 CPU, citation pattern, RAGAS triad eval, anti-leakage temporel) ; Brier optimizer (SGD projeté + bornes + MDE 0.02 holdout 21j ; per-régime V1, per-asset×régime V2) ; méta-prompt **DSPy MIPROv2 + BootstrapFewShot** + eval pré-merge + rollback auto J+7 ; post-mortem template 8 sections ; observability **PostHog Cloud free + Langfuse Hobby free + 15 panels Grafana** ; 5 schémas Postgres + 8 cron timers                                                                                                                                                                                                                                                                                                                                                                                                     | RAG = HNSW pas ivfflat ; chunking = 1 card = 1 chunk ; framework méta-prompt = DSPy MIPROv2 ; observability = PostHog Cloud free (1M events/mo) + Langfuse Hobby free (50k units/mo) ; 5 nouvelles tables (`confluence_weights_history`, `brier_optimizer_runs`, `prompt_versions`, `prompt_evals`, `post_mortems`, `rag_chunks_index`) → migrations 0013-0017 |
| [`docs/SPEC_V2_HARDENING.md`](docs/SPEC_V2_HARDENING.md) | Sécurité (CSP middleware nonce + HSTS + cookies `__Host-` + slowapi+Redis + JWKS durci + audit_log table + prompt injection 4-layers + secrets rotation 60-90j) ; tests (10 propriétés Hypothesis, snapshot Vitest, **Playwright `toHaveScreenshot()` GHA** vs Chromatic, k6 load, schemathesis OpenAPI, 10 happy paths E2E, couvertures cibles 70/60/40/65 %) ; déploiement (**blue-green systemd** templated + nginx upstream switch, **`/livez`+`/readyz`+`/startupz` séparés** vs `/healthz` actuel, feature flags **custom DB** vs PostHog, Alembic `transaction_per_migration=True` + lock_timeout 4s + Squawk lint + expand-migrate-contract) ; docs (**Changesets** monorepo, Storybook 8 + MSW, design system docs séparé, ADR-008 à -011 prévus, RUNBOOK-012 à -015 prévus) ; CI/CD (cache uv+pnpm+Playwright, required checks S4 étendus avec schemathesis+playwright+alembic+squawk+syft/grype, dependabot auto-merge patch only) | Health probes split en 3 ; blue-green Hetzner systemd remplace deploy actuel ; CI bloquant strict S4 inclut **9 vérifs** (lint+typecheck+test+audit+schemathesis+playwright+alembic check+squawk+syft/grype) pas 4 ; SBOM via syft+grype obligatoire                                                                                                           |

**Pour la prochaine session** : la nouvelle session Claude (post-`/clear`) doit charger `D:\Ichor\SPEC.md` + le compagnon adapté à la phase qu'elle implémente (Phase A → DESIGN, Phase B/C → AUTOEVO + TRADER + SOURCES, Phase D → HARDENING). Pas tout charger en même temps.

**Décisions critiques validées 2026-05-04 (interview Eliot)** :

| #   | Sujet             | Décision retenue                                                                                                             | Implication concrète                                                                                                                                                                                                                         |
| --- | ----------------- | ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2   | Typographie       | **Geist Sans (UI) + JetBrains Mono (data/tickers tabular-nums) + Fraunces ou Source Serif 4 (briefings + /learn éditorial)** | Charger via `next/font/google` ou `next/font/local`, palette typographique distinctive Vercel/éditoriale. À retirer Inter du fallback.                                                                                                       |
| 3   | Palette bull/bear | **Vert `#34D399` / rouge `#F87171` conservés + redondance obligatoire `+/−` ET `▲/▼` sur 100 % des affichages**              | Tous les composants chiffrés (BiasBar, AssetCard, ChartCard, sparkline tooltips, tickers EventTicker, etc.) DOIVENT afficher icône + signe + couleur ; lint UI dédiée à mettre en place pour vérifier. Conformité WCAG 1.4.1 par redondance. |
| 4   | OpenBB Platform   | **Copier le pattern, collectors maison** — pas de dépendance AGPLv3                                                          | Architecture provider-abstraction inspirée d'OpenBB dans `apps/api/src/ichor_api/collectors/_provider_base.py` (à créer), mais code des collectors écrit en propre. Préserve la possibilité de fermer/commercialiser Ichor plus tard.        |
| 5   | pgvector index    | **HNSW `m=16, ef_construction=64`**                                                                                          | Migration `0017_pgvector_setup.py` crée index HNSW (pas ivfflat). Cohérent avec recommandation `SPEC_V2_AUTOEVO.md §1.3`.                                                                                                                    |

**Décisions philosophie produit validées 2026-05-04 (interview suite Eliot)** :

| #   | Sujet                                            | Décision retenue               | Implication                                                                                                                                                                                                                                                                                                                                              |
| --- | ------------------------------------------------ | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D   | Chat conversationnel FR                          | **NON** — pas de chatbot dédié | Le « pourquoi » de chaque direction / signal / prédiction DOIT être **inline visible sur le frontend lui-même**. Renforce §3.5 pédagogie : tooltips contextuels + glossaire + walkthrough + « pourquoi je vois ça » sur chaque widget + chaque card explicite ses mechanisms et catalysts en clair, pas en JSON. UI = enseignant, pas chat à interroger. |
| G   | Tracker les trades du trader                     | **NON**                        | Ichor est un **système d'analyse**, pas un journal de trading personnel. Pas de table `user_trades`, pas de calcul P&L, pas de tracking entrées/sorties. Le trader saisit ses trades ailleurs (broker, journal externe). Préserve la séparation : Ichor = pré-trade context ; tools tiers = post-trade tracking.                                         |
| H   | Mode rétroactif "what if I had taken this trade" | **NON**                        | Ichor n'analyse pas l'historique du trader. Reste un outil universel d'analyse macro / fondamentale / géopolitique / sentiment / positioning / corrélations / volume. Aucun couplage à la psychologie ou aux données personnelles d'un user.                                                                                                             |
| I   | Voice TTS Azure FR matinal                       | **NON**                        | Confirmation de l'exclusion §9. Pas de briefing audio v1.                                                                                                                                                                                                                                                                                                |

**Philosophie « Ichor universel » consolidée** (issue de cette interview, à préserver Phase 2+) :

Ichor est un **système d'analyse macro/géopolitique/sentiment/positioning universel** — pas un assistant trader personnalisé. Le scope est :

- ✅ Tout ce qui se passe dans le marché et dans le monde, analysé et synthétisé
- ✅ Couches d'intelligence (4-pass + Pass 5 + Critic + 4 agents Couche-2 + ML 14 modèles + RAG 5 ans)
- ✅ Universalité : tout user trader pourrait théoriquement l'utiliser (single-user Eliot v1 par décision opérationnelle, pas par limitation architecturale)
- ❌ **JAMAIS** : tracker du trader, psychologie, journal de trades, coaching personnel, signal entry/exit, données perso utilisateur autres que paramètres techniques (push subs, theme, etc.)

Cette philosophie renforce les choix précédents :

- ADR-009 Voie D ($200 flat universel, pas usage-billed personnel)
- ADR-017 Living Macro Entity (jamais signal generator)
- Décision 4 OpenBB pattern copié + collectors maison (préserve possibilité commercialisation/partage future)
- Architecture multi-tenant viable Phase 7 si Eliot décide de partager Ichor

---

**Décision 1 — Pricing Polygon/Massive Currencies — CONFIRMÉ 2026-05-04** :
Eliot a souscrit au plan **Massive Currencies $49/mo** (rebrand de Polygon
2025-10-30). Le plan couvre **FX majors + spot metals (XAU/USD)**, ce qui
aligne parfaitement avec le périmètre Phase 1 (5 FX majors + gold).

- Plan : Massive Currencies
- Prix : $49/mo
- Couvre : EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, XAU/USD
- API key : `ICHOR_API_POLYGON_API_KEY` (clé unique, tier upgradé du Starter $29 historique)

**Implication coût total Phase 2** : $200 Max 20x + €20 Hetzner + $49 Massive
= **~$269/mo flat**, conforme à ADR-017 et VISION_2026.

Phase B/C **débloquées** sur cette base. Les indices US (NAS100, US30, SPX500)
restent servis par OANDA practice + yfinance fallback (cf ADR-012).

---

_Document maintenu par Claude Code via skill `/spec`. Met à jour à chaque évolution majeure de la spec ou des décisions architecturales. Annexes V2 sourcées et écrites le 2026-05-04 par 5 subagents researcher._
