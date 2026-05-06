# SPEC v2 — Auto-amélioration RAG + Brier optimizer + observability product

**Date** : 2026-05-04
**Compagnon de** : `D:\Ichor\SPEC.md` (Phase 2 Ichor, §3.7 auto-amélioration)
**Source** : recherche READ-ONLY web 2026 (pgvector 0.7+, BGE/E5/MTEB, RAGAS, DSPy MIPROv2, PostHog, Plausible, Langfuse, Web Vitals, Grafana LLM, Hypothesis, ChromaDB)

## 1. RAG sur historique 5 ans Ichor — détails techniques

### 1.1 Chunking strategy

**Reco** : pas de pure semantic chunking. Vecta benchmark 02-2026 montre récursif 512 tokens à 69 % vs semantic à 54 % sur 50 papers réels (fragments moyens 43 tokens, "context cliff").

Pour Ichor :

- **1 card = 1 chunk** (les cards font ~1-2k tokens, déjà des unités sémantiques cohérentes — verdict + mechanisms + magnitude + invalidation). PAS de découpage intra-card.
- Pour briefings et post-mortems plus longs : **récursif 512 tokens, overlap 10-20 %** (50-100 tokens), respect headings markdown.

**Métadonnées indexées** : `asset`, `regime_at_emission`, `created_at`, `brier_realized`, `pass_index` (1/2/3/4/5), `card_id`, `card_section`.

**Contextual retrieval** Anthropic-style : préfixer chaque chunk d'un header court avant embedding pour auto-suffisance :

```
[asset=EUR/USD | regime=risk_on | 2025-03-14 | brier=0.18]
```

### 1.2 Embedding model + raison

**Reco** : `bge-small-en-v1.5` (384d) pour démarrage. Argument 2026 : `e5-small-v2` (118M params) overperforme parfois sur RAG production (100 % Top-5, latency 16ms GPU H100), mais BGE garde meilleur écosystème ONNX/TEI et stabilité.

**Caveat** : MTEB v2 (2026) n'est pas comparable à v1, choisir d'après recall@k mesuré sur un golden set Ichor (50-100 paires question-card cible).

**Inference Hetzner CPU** : passer par `text-embeddings-inference` (HuggingFace) ou ONNX via `optimum`. CPU est 10-50× plus lent que GPU mais reste tenable pour index incrémental (cards générées à 80 calls/jour max).

### 1.3 ANN index choice

**Reco** : `hnsw` avec `m=16, ef_construction=64`. **PAS ivfflat** comme la SPEC mentionne actuellement.

pgvector 0.7+ HNSW : 30× QPS et p99 vs ivfflat à 99 % recall sur dbpedia-1M, build time réduit ~150× avec binary quantization, sub-ms latency.

ivfflat reste pertinent si volume > 50M vecteurs OR mémoire RAM contrainte. Pour 5 ans × 8 actifs × ~4 cards/jour = ~58k cards → ridicule pour HNSW. **Choix sans regret**.

`ef_search` runtime : 40-100 ; ajuster sur recall mesuré.

### 1.4 Hybrid search pattern (dense + BM25)

**Reco** : RRF (Reciprocal Rank Fusion) avec k=60 sur deux retrievers parallèles (dense pgvector + BM25). Gain documenté : 65-78 % → 91 % recall@10, fusion <10ms.

**Implémentation Postgres native** : `tsvector` GIN comme baseline (mais `ts_rank` souffre — rewards keyword stuffing, all-terms required). Pour vrai BM25 sans Elasticsearch :

- Extension `pg_textsearch` (Tiger Data, 1.0 stable 2026, build C natif Block-Max WAND, fully transactional)
- OU `pg_search` (ParadeDB)
- OU `vectorchord-bm25`

Toutes gratuites self-host.

**Schéma minimal** :

```sql
embedding vector(384),
content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
CREATE INDEX ... USING gin (content_tsv);
```

**Fetch multiplier** : pull top 30 de chaque retriever avant fusion pour top 5 final.

### 1.5 Reranking — feasible Hetzner CPU ?

**Reco** : OUI mais ciblé.

- Cross-encoder `ms-marco-MiniLM-L-6-v2` ou `bge-reranker-v2-m3` (278M, MiniLM-based)
- CPU latency ~150ms pour 100 paires de 256 tokens, ~350ms pour bge-reranker-v2-m3 sur batches <100
- Acceptable hors trajet utilisateur (Pass 1 backend, pas live UI)
- Ichor a besoin de top-5, pas de top-100, donc CPU reste raisonnable

**Alternative hyper-CPU** : `mxbai-rerank-xsmall` (distillé 0.1B), <10ms CPU lookup, qualité ~95 % du grand modèle.

ColBERTv2 + PLAID (45× speedup CPU vs vanilla) reste un cran trop lourd pour le volume Ichor.

### 1.6 Citation pattern dans Pass 1 prompt

Inclure dans le prompt Pass 1 un bloc `<analogues>` listant les top-5 retrievés sous forme :

```
[card_id, asset, date, regime, verdict, brier_realized, distance]
```

Demander à Claude Opus 4.7 de citer explicitement `card_id` quand il s'en sert :

> "Analogue C-2024-09-12 EUR/USD risk_on Brier 0.14 montre que..."

Le `card_id` cité sert ensuite à l'eval faithfulness et à l'audit.

### 1.7 Eval suite : recall@k + NDCG + faithfulness

**Golden set** : 50-100 questions Q→card_target. Couvrir 8 actifs × 3 régimes × ~4 dates = ~96 cas.

**Métriques retrieval** :

- `Recall@5`
- `NDCG@10`
- `MRR`

NDCG essentielle car cas multi-relevant.

**Métriques génération** : RAGAS triad (`faithfulness`, `context_relevance`, `answer_relevance`). Faithfulness critique pour finance (hallucinated number = exposure). Lock metric definition dans contrat eval.

**LLM-as-judge** : calibrer contre 20 % humain (Eliot ou snapshot), agreement target 0.6-0.8. Coût ~$1 / run de 200 questions avec GPT-4o-mini judge — ou Haiku 4.5 self-judge via Max 20x.

**Tools** : Ragas pour exploration, DeepEval pour CI/CD pytest-native. Benchmark domaine : T²-RAGBench (table reasoning, pertinent pour COT/options data).

### 1.8 Anti-leakage temporal split

**Reco** : filtre `WHERE created_at < :as_of_timestamp` obligatoire à chaque retrieval. Stocker `as_of_timestamp` dans la table `briefings_runs`. Pendant backfill / replay, `as_of` = timestamp historique simulé. Pour live, `as_of = NOW()`.

Index composite `(asset, regime, created_at DESC)` pour accélérer ce filtre.

**Test acceptance obligatoire** : « Un retrieval lancé pour la card du 2024-03-15 ne renvoie aucun chunk avec `created_at >= 2024-03-15` ».

### 1.9 Schema Postgres + index

Voir §6.5.

## 2. Brier weights optimizer

### 2.1 Algorithme recommandé

**Reco V1** : descente de gradient projetée online (variante Flaxman/Zinkevich, regret O(√n)) sur la log-loss ou Brier loss du confluence engine. SPEC §3.7 mentionne déjà LR 0.05 + momentum 0.9 — cohérent. Cap LR = 0.05 conservateur.

**Alternative V2** : Thompson sampling Beta-Bernoulli **par facteur** pour exploration-exploitation des facteurs sous-utilisés. Conjugaison naturelle (succès Bernoulli = card hit dans une bande Brier). Plus complexe à câbler avec contrainte sum=1, mais regret logarithmique. Recommandé en V2 si gradient stagne.

Multi-armed bandit non-stationnaire (MABCO) si on suspecte régime drift fort sur weights — mais ADWIN couvre déjà ce risque côté détection.

### 2.2 Constraint optimization — formule

Weights `w ∈ R^k`, contraintes `sum(w) = 1`, `w_i ∈ [0.05, 0.5]`.

**Étape** : `w' = w - lr * grad(Brier_loss)` puis **projection sur le simplexe tronqué** : clamp [0.05, 0.5] puis renormaliser pour sum=1. Itérer projection 2-3× si bornes violées après renorm (algo de Duchi 2008 sort of).

**Sanity check post-update** : `abs(sum(w) - 1) < 0.01`, sinon rollback à w précédent et alert ops.

### 2.3 A/B testing — holdout, MDE, durée min

**Pattern** : champion-challenger.

- Champion = weights live
- Challenger = nouveaux weights
- Run en shadow sur les nouvelles cards (1 card = 1 obs)
- MDE Brier delta = 0.02 (5 % d'amélioration relative sur baseline ~0.20)

**Sample size** : pour MDE 0.02 sur Brier σ ~0.15, α=0.05, power 0.8, n ≈ 450 obs. À 32 cards/jour = ~14 jours min de holdout. **Réaliste : 21 jours minimum** avant promotion.

Test paired sur les mêmes cards (champion et challenger scorent la même card avec leurs weights respectifs sur les mêmes facteurs réalisés).

### 2.4 Guardrails

- Bornes [0.05, 0.5] (déjà SPEC)
- `sum=1 ± 0.01`
- LR cap = 0.05 max
- Eval suite pré-adoption : Brier moyen 30j challenger ≤ champion + 0.005 (bruit toléré), ECE (expected calibration error) ne dégrade pas > 10 %, approval rate Critic stable
- Rollback automatique si dégradation persistante > 7j (réf SPEC L375 « Brier dégradation > 15 % sur 7j »)

### 2.5 Per-asset × per-régime ou global ?

**Reco V1** : **per-régime global** (3 régimes HMM × 1 vecteur weights = 3 vecteurs). Suffisant pour signaler les contributions différentes des facteurs en risk_on vs risk_off. Données : 5j × ~10 cards/régime/jour × 3 régimes = volumétrie OK.

**V2 si Brier lift stagne** : **per-asset × per-régime** (8 × 3 = 24 vecteurs). Demande ~30 cards/cellule pour stat power → ~3 mois de données par cellule. Pas viable initialement.

Pas de global pur (perd l'info régime, déjà SPEC §3.12 HMM).

### 2.6 Visualisation `/calibration` extended

- Heatmap `weights[factor][regime]` par semaine sur 12 semaines
- Reliability diagram (déjà prévu)
- Time-series Brier moyen 7j rolling par régime
- Tableau weights actuels vs baseline initial avec delta

## 3. Méta-prompt tuning safe

### 3.1 Framework recommandé

**Reco** : DSPy MIPROv2 + BootstrapFewShot. Stanford NLP, mature, license MIT, optimise instructions ET few-shot demos en jointure via Bayesian search Optuna TPE. Coût typique d'un run : ~$2 USD / 10 min sur petites tâches. Pour Ichor tournant via Claude Max 20x runner local : compte des tokens, pas du dollar.

**Pattern** : Layer four bottom-up — start BootstrapFewShot, graduate à MIPROv2 quand on a > 50 exemples.

**Pas custom** sauf si DSPy ne supporte pas le routing Claude runner local — vérification à faire (probable que oui via litellm / openai-compatible adapter).

### 3.2 Eval suite obligatoire pré-merge

- Devset golden 50-100 cards labellisées par Eliot (verdict OK / verdict KO / mechanism manquant / catalyst halluciné)
- Métriques : approval Critic, faithfulness via Ragas, mechanism count F1, hallucination rate
- **Threshold merge** : new ≥ baseline sur tous + amélioration > 2 points sur ≥ 1 métrique

### 3.3 Métriques v1 vs v2

- Approval rate Critic (déjà tracé, baseline 76 %)
- Brier 7j projected sur paires equivalent
- ECE (calibration)
- Length distribution (anti-stripping cas MIPRO « optimise pour court mais perd l'info »)
- Hallucination rate (claims sans citation source)
- Factor coverage (le prompt mentionne-t-il bien les 6 facteurs ?)

### 3.4 Détection régression silencieuse

- Diff text + Diff comportemental sur le devset golden
- Anomaly detection sur la **distribution** des verdicts générés (ex: si v2 produit 95 % verdicts neutral vs 60 % en v1 → régression silencieuse)
- Critic findings count par card : si chute brutale → soit prompt magique, soit Critic biaisé (red flag)

### 3.5 Rollback automatique

- Toujours marker `prompt_version_id` sur chaque card produite
- Cron J+7 post-merge : si delta Brier > +0.01 sustained → revert auto vers `prompt_version_id` précédent + push iOS « auto-rollback méta-prompt vN→vN-1 »
- Garde-fou SPEC §3.7 (« PR auto, pas de merge auto ») cohérent

### 3.6 Cadence

- **Bi-mensuel = OK** pour cycle PR review humain. Pas plus fréquent (bruit + risque overfit Critic findings court terme). Pas moins (stagnation).
- Si Eliot trop occupé pour review → bascule mensuelle.
- **Trigger event-based supplémentaire** : lancer un tuning ad-hoc si ADWIN Brier drift détecté.

## 4. Post-mortem hebdo auto Claude

### 4.1 Structure document standard (template figé)

Sections obligatoires :

1. **Header** : semaine ISO, période exacte, # cards, # alerts, # crisis modes
2. **Top hits** : 5 cards les mieux calibrées (Brier le plus bas), résumé 1 ligne chacune + lien
3. **Top miss** : 5 cards avec biggest Brier delta vs prédit, post-hoc explication
4. **Drift detected** : régimes vs ADWIN, weights drift, sources stale
5. **Narratives émergentes** : top 3 themes News-NLP de la semaine, lien aux cards impactées
6. **Calibration** : Brier moyen 7j vs 30j vs 90j, ECE, approval rate Critic
7. **Suggestions amendments** : items actionables (ex: "considérer downweight VPIN en régime risk_off")
8. **Stats raw** : tableau aggregations

### 4.2 Pattern recognition cross-week

- Comparer narratives W vs W-1, W-4, W-12 — trigger flag si re-émergence après silence (ex: "inflation" revient après 8 semaines)
- Tracker count d'occurrences de mêmes "top miss" patterns → si X actif manqué 3 semaines de suite → escalade `RECURRING_MISS` alert

### 4.3 Eval suite — taux findings actionables

- Eliot annote chaque post-mortem : `actionable=yes/no` par item suggestion
- KPI 6 mois : ≥ 50 % suggestions actionables (sinon prompt post-mortem à retravailler)

### 4.4 UI `/post-mortems`

- Liste paginée par semaine, search texte
- Détail : markdown rendu + sticky TOC + comparaison W-1
- Filter par asset / régime
- Export PDF

## 5. Observability product Ichor

### 5.1 PWA analytics

**Reco** : **PostHog Cloud free tier** (1M events/mo, 5k recordings/mo, 1M flag requests/mo, unlimited seats, hard spend cap configurable). Largement au-dessus du besoin Ichor single-user Eliot. EU hosting dispo (RGPD). Self-host PostHog non recommandé par PostHog eux-mêmes (OSS scale ~100k events/mo seulement).

**Alternative** : Plausible CE (AGPLv3, Docker Compose, ClickHouse + Postgres, ~1-2 GB RAM). Privacy-first, pas de cookies, mais **moins de fonctionnalités** : pas de session replay, pas de funnels avancés, geo city-level demande MaxMind license, pas de feature flags. Pour single-user trader, suffisant si on veut juste page views + events.

**Verdict** : PostHog Cloud free, score session replay décisif pour debug Eliot. Plausible CE en plan B si PostHog free tier dépassé (improbable).

### 5.2 RUM Web Vitals 2026 thresholds

- **LCP < 2.5s**
- **INP < 200ms**
- **CLS < 0.1**

Évalués au p75 CrUX (mobile prioritaire car ranking signal). INP est le plus dur (43 % des sites fail).

**Outils gratuits** : `web-vitals` JS lib (Google), envoi vers PostHog ou Grafana via `/api/rum` endpoint custom + tsdb.

Veille 2026 : Visual Stability Index (VSI) en preview. Pas urgent.

### 5.3 Event tracking schema

Events à instrumenter (dataLayer minimal) :

- `session_card_viewed` (asset, regime, conviction)
- `drill_down_opened` (from_page, to_asset)
- `counterfactual_triggered` (asset, scenario_id)
- `time_machine_scrubbed` (asset, days_back)
- `push_notification_clicked` (alert_code, age_seconds)
- `push_notification_dismissed`
- `walkthrough_completed_step` (step_n)
- `glossary_term_opened` (term)
- `mobile_blocker_shown` (page)
- `cmd_k_opened`, `cmd_k_action_executed`
- `crisis_mode_entered`, `crisis_mode_exited`
- `learn_chapter_completed` (chapter)

### 5.4 LLM tracing Langfuse

**Free Hobby tier** : 50k units/mo (= traces+observations+scores), 30j retention, 2 seats. Ichor : ~80 calls/jour × 4 passes ≈ 9.6k traces/mo + observations enfants ≈ 30-40k units. **Tient dans free tier**.

Self-host coût v3 (ClickHouse) = $400-800/mo, **largement au-dessus du budget**, donc **rester en cloud free**.

**Panels exploitables Langfuse** :

- Cost tracking par agent (CB-NLP, News-NLP, Sentiment, Positioning, Pass 1-5)
- Latency par pass (p50/p95/p99)
- Token usage par modèle (Opus / Sonnet / Haiku)
- Quality scores : evals attachés (Critic approval, faithfulness Ragas)
- User feedback (thumbs Eliot sur cards)
- Failed traces drill-down

**Pattern** : `langfuse.trace(name="session_card", metadata={asset,regime})` parent → spans par pass enfants.

### 5.5 ML model monitoring

- **Drift dashboard Grafana** : panels feature drift par modèle (HMM régime, FOMC-RoBERTa, FinBERT, VPIN…) via PSI (Population Stability Index) ou KS-test 30j vs baseline
- ADWIN drift detector déjà en place → expose son output comme métrique Prometheus `ichor_adwin_drift_detected{model="X"} 0|1`
- Brier per asset × régime → time-series 90j
- Feature importance evolution (LightGBM, XGBoost) : barplot weekly snapshot

### 5.6 Grafana ops dashboards (15 panels listés)

1. **API health** : RPS, latency p95, error rate par endpoint
2. **Postgres** : connexions, slow queries (>1s), bloat, replication lag
3. **TimescaleDB** : compression ratio, hypertable size
4. **pgvector** : index size, latency `<-> ` p95, recall sample
5. **Cron timers** : last run / next run / failure count par timer
6. **Cloudflare tunnel** : up/down status
7. **Claude runner** : queue depth, latency p99, 429 count, fallback rate Cerebras/Groq
8. **Langfuse cost** : tokens cumulés / mois par modèle (alerte 80 % budget)
9. **Brier rolling** : 7d/30d/90d par asset
10. **ADWIN flags** : count par modèle 7j
11. **Web Vitals** : LCP/INP/CLS p75
12. **PWA push** : delivery rate, click-through rate
13. **Sources freshness** : age max par collector (alert > 6h sur sources critiques)
14. **Disk / RAM / CPU Hetzner** (node_exporter classic)
15. **CI status** (lint/typecheck/test/audit) ratio pass via GH webhook → Pushgateway

## 6. Schémas Postgres pour les nouveaux mécanismes

### 6.1 `confluence_weights_history`

```sql
id uuid PK,
created_at timestamptz default now(),
asset text null,         -- null = global
regime text not null,    -- risk_on / risk_off / neutral
weights jsonb not null,  -- {"vpin":0.18,"correl":0.22,...}
brier_30d numeric(6,4),
ece_30d numeric(6,4),
optimizer_run_id uuid REFERENCES brier_optimizer_runs(id),
is_active boolean default false,
INDEX (asset, regime, created_at DESC)
```

### 6.2 `brier_optimizer_runs`

```sql
id uuid PK,
ran_at timestamptz default now(),
algo text,                -- "online_sgd" / "thompson_beta" / ...
lr numeric(5,3),
n_obs int,
brier_before numeric(6,4),
brier_after numeric(6,4),
delta numeric(6,4),
weights_proposed jsonb,
adopted boolean default false,
adoption_decision_at timestamptz,
holdout_period_start timestamptz,
holdout_period_end timestamptz
```

### 6.3 `prompt_versions` + `prompt_evals`

```sql
prompt_versions(
  id uuid PK,
  pass_index int,           -- 1..5 ou critic
  scope text,               -- regime / asset / stress / invalidation
  body text not null,
  parent_id uuid,
  created_at timestamptz,
  source text                -- 'manual' | 'meta_prompt_tuner_auto'
)

prompt_evals(
  id uuid PK,
  prompt_version_id uuid REFERENCES prompt_versions(id),
  devset_id text,
  approval_rate numeric(4,3),
  faithfulness numeric(4,3),
  brier_proj numeric(6,4),
  ece numeric(6,4),
  hallucination_rate numeric(4,3),
  ran_at timestamptz
)
```

### 6.4 `post_mortems`

```sql
id uuid PK,
iso_year int,
iso_week int,
generated_at timestamptz,
markdown_path text,         -- docs/post_mortem/2026-Wnn.md
top_hits jsonb,
top_miss jsonb,
narratives jsonb,
suggestions jsonb,
actionable_count int default 0,
actionable_count_resolved int default 0,
UNIQUE (iso_year, iso_week)
```

### 6.5 `rag_chunks_index`

```sql
id uuid PK,
source_type text,            -- 'card' | 'briefing' | 'post_mortem'
source_id uuid,
asset text,
regime text,
section text,                -- verdict|mechanisms|catalysts|invalidation
content text,
embedding vector(384),
content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
metadata jsonb,              -- {brier_realized, conviction, ...}
created_at timestamptz NOT NULL,  -- = card.created_at, anti-leakage
indexed_at timestamptz default now(),
INDEX hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64),
INDEX gin (content_tsv),
INDEX (asset, regime, created_at DESC)
```

## 7. Cron schedule complet auto-amélioration

| Cron timer                          | Service                                                    | Cadence                    | Côté           |
| ----------------------------------- | ---------------------------------------------------------- | -------------------------- | -------------- |
| `ichor-rag-reindex.timer`           | reindex new cards → `rag_chunks_index`                     | toutes 1h                  | Hetzner        |
| `ichor-brier-optimizer.timer`       | Brier weights gradient run + holdout track                 | quotidien 02h Paris        | Hetzner        |
| `ichor-brier-promote.timer`         | promote challenger si guards OK                            | hebdo lundi 03h Paris      | Hetzner        |
| `ichor-adwin-monitor.timer`         | scan Brier 30j ADWIN, emit drift alert                     | toutes 6h                  | Hetzner        |
| `ichor-post-mortem.timer`           | post-mortem hebdo Claude Opus 4.7                          | dimanche 18h Paris         | Win11 (runner) |
| `ichor-meta-prompt-tuning.timer`    | DSPy MIPROv2 + PR GitHub auto                              | 1er + 15 du mois 03h Paris | Win11 (runner) |
| `ichor-rag-eval.timer`              | Ragas eval suite golden set                                | hebdo dimanche 03h         | Hetzner        |
| `ichor-prompt-rollback-watch.timer` | check delta Brier J+7 post-merge prompt, revert si > +0.01 | quotidien 04h              | Hetzner        |

## 8. Recommandations concrètes pour SPEC.md

À densifier dans §3.7 et §3.10 :

1. **§3.7 RAG L151** : changer "ivfflat" mention dans Risques (L460) → **HNSW m=16 ef_construction=64** (référence pgvector 0.7+ benchmarks).
2. **§3.7 RAG** : ajouter ligne "hybrid search RRF k=60 dense (pgvector HNSW) + BM25 (extension `pg_textsearch` ou tsvector GIN baseline)".
3. **§3.7 RAG** : ajouter "anti-leakage : filtre `WHERE created_at < as_of_timestamp` obligatoire, test acceptance dédié".
4. **§3.7 RAG** : ajouter "eval suite RAGAS triad sur golden set 50-100 questions, lancée hebdo dimanche".
5. **§3.7 RAG** : préciser "chunking : 1 card = 1 chunk (pas de split intra-card) ; briefings/post-mortems récursif 512 tokens overlap 100".
6. **§3.7 Brier weights** : ajouter "MDE Brier 0.02 → holdout shadow 21 jours min avant promotion".
7. **§3.7 Brier weights** : préciser "V1 per-régime (3 vecteurs), V2 per-asset×régime si stagnation".
8. **§3.7 Méta-prompt** : préciser "framework = DSPy MIPROv2 + BootstrapFewShot, eval pré-merge sur golden devset 50 cards Eliot-labellisé".
9. **§3.7 Méta-prompt** : ajouter "rollback automatique J+7 post-merge si Brier delta > +0.01 sustained".
10. **§3.7 Post-mortem** : annexer template document (8 sections fixes §4.1 ci-dessus).
11. **§3.10 ou nouvelle §3.15 Observability** : ajouter section dédiée — PostHog Cloud free, web-vitals JS, Langfuse Hobby free 50k units, Grafana panels listés §5.6.
12. **§4 Stack** : ajouter `pg_textsearch` ou `pg_search` (BM25 extension), `text-embeddings-inference` (TEI HuggingFace), `dspy`, `ragas`, `posthog-js`, `web-vitals`.
13. **§5 Phases** : préciser Phase C semaine RAG = sprint 1 indexation backfill + sprint 2 retrieval Pass 1 + sprint 3 eval suite.
14. **Ajouter `migrations/0013-0017`** : `confluence_weights_history`, `brier_optimizer_runs`, `prompt_versions`, `prompt_evals`, `post_mortems`, `rag_chunks_index`.
15. **§8.2 Acceptance** : ajouter "RAG eval recall@5 > 0.7 et faithfulness > 0.85 sur golden set" et "Brier optimizer holdout signed-off avec MDE 0.02".

## Sources principales

- BGE / E5 : [BGE-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) / [Best Embedding Models 2026 BentoML](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)
- pgvector : [HNSW vs IVFFlat AWS](https://aws.amazon.com/blogs/database/optimize-generative-ai-applications-with-pgvector-indexing-a-deep-dive-into-ivfflat-and-hnsw-techniques/) / [benchmarks 2026 CallSphere](https://callsphere.ai/blog/vector-database-benchmarks-2026-pgvector-qdrant-weaviate-milvus-lancedb)
- Hybrid search : [ParadeDB missing manual](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual) / [Tiger Data pg_textsearch](https://www.tigerdata.com/blog/introducing-pg_textsearch-true-bm25-ranking-hybrid-retrieval-postgres) / [VectorChord BM25](https://blog.vectorchord.ai/hybrid-search-with-postgres-native-bm25-and-vectorchord)
- Chunking : [Firecrawl 2026](https://www.firecrawl.dev/blog/best-chunking-strategies-rag) / [Premai 2026 benchmark](https://blog.premai.io/rag-chunking-strategies-the-2026-benchmark-guide/)
- Reranker : [AIMultiple 2026](https://aimultiple.com/rerankers) / [Markaicode BGE reranker](https://markaicode.com/bge-reranker-cross-encoder-reranking-rag/)
- RAG eval : [Ragas Faithfulness](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/) / [Premai 2026](https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026/)
- DSPy : [Optimizers docs](https://dspy.ai/learn/optimization/optimizers/) / [MIPROv2 API](https://dspy.ai/api/optimizers/MIPROv2/) / [arXiv 2412.15298](https://arxiv.org/html/2412.15298v1)
- Online opt : [Flaxman et al.](https://arxiv.org/abs/cs/0408007) / [Thompson Russo Stanford](https://web.stanford.edu/~bvr/pubs/TS_Tutorial.pdf)
- Brier : [scikit-learn brier_score_loss](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html) / [Ferro Exeter](https://empslocal.ex.ac.uk/people/staff/ferro/Publications/binary.pdf)
- Observability : [PostHog pricing](https://posthog.com/pricing) / [Plausible CE](https://plausible.io/docs/self-hosting) / [Langfuse self-host](https://langfuse.com/pricing-self-host)
- Web Vitals : [corewebvitals.io 2026](https://www.corewebvitals.io/core-web-vitals)
- Grafana LLM : [GenAI Observability docs](https://grafana.com/docs/grafana-cloud/monitor-applications/ai-observability/genai/observability/) / [LLM-Watch plugin](https://github.com/anglerfishlyy/llm-watch-grafana)
