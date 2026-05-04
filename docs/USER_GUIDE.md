# Ichor — Guide utilisateur (Eliot)

> **Dernière mise à jour** : 2026-05-04
> **Pour qui** : Eliot, le seul user de la prod V1.
> **Pré-requis** : un navigateur, idéalement iPhone Safari + ordinateur
> avec Cmd+K reflex.

---

## 1. Workflow type d'une journée de trading

### 06:00 Paris — Le système se réveille tout seul

Tu dors. À 06:00 le timer `ichor-session-cards-pre_londres.timer` se
déclenche sur Hetzner. Le brain orchestrator tourne sur les 8 actifs
séquentiellement (~8 minutes). Chaque carte qui sort en `approved` ou
`amendments` envoie une notif push iPhone.

À 06:08, tu as 5-7 notifications dans ton centre de notif :
```
🔔 Ichor · EUR/USD · pre londres
   SHORT 22% · approved

🔔 Ichor · USD/JPY · pre londres
   NEUTRAL 18% · approved
```
Tap → ouvre directement `/sessions/EUR_USD`.

### 07:30 Paris — Tu te réveilles, tu prends ton café

Tu ouvres `https://app-ichor.pages.dev` (ou en dev :
`pnpm --filter @ichor/web dev` puis `localhost:3000`).

**Ce que tu vois sur `/`** :
- Le quadrant régime macro pulse sur le régime courant
  (haven_bid / funding_stress / goldilocks / usd_complacency)
- Heatmap cross-asset colorée (couleur = direction biais, intensité = conviction)
- 3 cards featured (verdicts approved/amendments)
- Strip alerts critiques si applicable
- Tape Bloomberg en bas qui montre les derniers événements live

### 07:35 — Tu drill-down sur un actif qui t'intéresse

`Cmd+K` → tape "EUR" → Enter, ou clique directement la card.

`/sessions/EUR_USD` te montre :
- LiveChartCard 1-min Polygon (auto-refresh 30s)
- Bouton **▶ Replay temporel** → time-machine slider sur l'historique
- Bouton **🔮 Counterfactual** → "et si Powell avait été dovish ?"
- Mécanismes invoqués cliquables (chaque source URL accessible)
- Catalystes attendus (NFP, CPI, FOMC, etc.)
- Conditions invalidation explicites

### 07:45 — Tu valides ton plan macro avant TradingView

`Cmd+K` → tape "shock" → ouvre `/knowledge-graph`. Tu picks
"Powell hawkish" + P=0.7 → tu vois la propagation Bayes-lite forward
sur la carte causale (XAU/USD impact 79%, etc.).

`Cmd+K` → tape "narratives" → tu vois les top keywords du corpus
48h vs 7j. Tu repères si "fed cut" domine, "recession", "AI capex"...

`Cmd+K` → tape "geopol" → tu vois la heatmap GDELT monde, repère
si une zone géo-sensible bouge (Russia/Ukraine, Israel, etc.).

### 12:00 — Pré-NY tick

Le batch `pre_ny` se lance automatiquement, 8 nouvelles cards.
Toast violet pop sur ton écran : "Nouvelle carte session · USD/JPY · NEUTRAL 25% · approved".
Tu cliques → drill-down rapide pour voir ce qui a changé depuis pré-Londres.

### 22:00 — NY close + reconciliation

Le batch `ny_close` génère 8 cards finales. À 23:15 le reconciler
nightly tourne, fill les colonnes `realized_*` + `brier_contribution`
sur les cards closes du jour. **`/calibration`** s'enrichit
(reliability diagram + skill score).

---

## 2. Pages disponibles (13)

| Page | Quand y aller |
|---|---|
| `/` | Au réveil, vue d'ensemble |
| `/sessions` | Toutes les cards courantes |
| `/sessions/{asset}` | Drill-down un actif (chart + replay + counterfactual) |
| `/replay/{asset}` | Time-machine slider sur l'historique verdicts |
| `/narratives` | Top keywords cb_speeches + news 24h vs 7j |
| `/knowledge-graph` | Carte causale + ShockSimulator |
| `/geopolitics` | Heatmap GDELT monde |
| `/calibration` | Brier track-record reliability diagram |
| `/admin` | Health snapshot — taux d'approval, durées, fraîcheur tables |
| `/briefings` | Liste briefings narratifs (legacy) |
| `/assets` | Liste 8 actifs Phase-1 |
| `/alerts` | Alertes actives |
| `/news` | Flux news brut |

---

## 3. Raccourcis clavier

| Raccourci | Action |
|---|---|
| `Cmd+K` (Mac) / `Ctrl+K` (Win) | Ouvrir command palette |
| `↑ ↓` dans le palette | Naviguer suggestions |
| `Enter` | Exécuter sélection |
| `Esc` | Fermer palette / dismiss toasts |

---

## 4. Capacités UNIQUES (à exploiter)

### Counterfactual Pass 5

Sur n'importe quelle session card, clique 🔮 **Counterfactual**.
Modal s'ouvre. Tape un événement (ex: "Powell hawkish surprise May 2") →
le brain re-derive le verdict en scrubant cet événement. Te montre :
- Original bias vs counterfactual bias
- Delta narrative (1-3 phrases d'explication)
- Drivers dominants si l'événement n'avait pas eu lieu
- Δ confiance

**Quand l'utiliser** : pour tester ton hypothèse macro alternative
("et si la Fed cut au lieu de hold ?") sans recommencer toute l'analyse.

### Causal Shock Simulator

Sur `/knowledge-graph`, panneau Shock simulator. Pick un nœud
(Powell / Lagarde / Ueda / Fed / ECB / BoJ / US10Y / USD / DFII10
/ DXY / WTI), set la probabilité du choc (0-1), clique Propage.

Te montre la propagation forward sur la carte causale avec
probabilité d'impact + nombre de hops par actif.

**Quand l'utiliser** : pour anticiper l'impact d'un événement
attendu (FOMC demain, ECB jeudi, etc.).

### Time-machine Replay

Sur `/replay/{asset}`, slider sur l'historique des verdicts.
Auto-play 0.5x / 1x / 2x / 5x. Les changements de régime / biais /
verdict sont highlightés en émeraude.

**Quand l'utiliser** : valider que les transitions ont du sens,
identifier les patterns de drift, comprendre les épisodes passés.

### Polymarket↔Kalshi↔Manifold divergence

Quand le brain sees un gap > 5pp entre les 3 venues sur la même
question, ça apparaît dans la section `prediction_markets` du
data_pool. Tu peux query directement :
```
GET /v1/data-pool/EUR_USD
```
et regarder la sous-section "prediction_markets" pour voir les écarts.

---

## 5. Activer les push notifications iOS

1. Ouvre Ichor sur ton iPhone Safari (PWA installable)
2. Add to Home Screen depuis le menu partage
3. Re-ouvre depuis l'icône d'accueil
4. Click "🔔 activer push" en haut à droite de la nav
5. Accepte la permission iOS

À chaque carte approved/amendments générée :
- iPhone vibre
- Notif "Ichor · {asset} · {session_type}" + "{BIAS} {conv}% · {verdict}"
- Tap → ouvre `/sessions/{asset}` directement

---

## 6. Vérifier la santé du système

Ouvre `/admin`. Tu dois voir :

### Top KPIs
- **Cartes 24h** : 0 jusqu'au premier batch automatique. Devrait être 32 si tu
  laisses tourner toute une journée (8 actifs × 4 sessions).
- **Cartes total** : nombre cumulé persistées.
- **Dernière carte** : timestamp.
- **Claude-runner** : "configuré" si l'URL est set dans api.env.

### Tables freshness
- **fresh** (vert) : entrée dans la dernière 30 min
- **recent** (vert pâle) : dans les 6h
- **today** (orange) : dans les 24h
- **stale** (gris) : > 24h — anormal sauf pour `cot_positions`
  (Friday-only).

### Per-asset breakdown
Voit le **taux d'approval** par actif. Si EUR/USD est à 33% approved
mais USD/JPY est à 100%, c'est un signal que les frameworks asset-
spécifiques ont des forces / faiblesses différentes.

---

## 7. Voir ce que le brain voit (debug)

```bash
ssh ichor-hetzner 'curl -s http://127.0.0.1:8000/v1/data-pool/EUR_USD' \
  | python3 -c "import json, sys; print(json.load(sys.stdin)['markdown'])" \
  | less
```

Te montre les 14 sections que le brain voit pour un asset, sans
dépenser une session Claude --live.

---

## 8. Lancer une carte --live à la demande

Ssh sur Hetzner :
```bash
ssh ichor-hetzner "set -a; source /etc/ichor/api.env; set +a; \
  cd /opt/ichor/api && /opt/ichor/api/.venv/bin/python -m \
  ichor_api.cli.run_session_card EUR_USD pre_londres --live"
```

Génère une carte avec le claude-runner Win11 (consomme du quota Max 20x).
Persiste dans `session_card_audit`. Push iPhone si tu as activé.

---

## 9. Lancer le batch sur les 8 actifs à la demande

```bash
ssh ichor-hetzner "set -a; source /etc/ichor/api.env; set +a; \
  cd /opt/ichor/api && /opt/ichor/api/.venv/bin/python -m \
  ichor_api.cli.run_session_cards_batch pre_londres --live"
```

8 cards en ~8 minutes (sleep 3s entre chaque pour ménager Max 20x).

---

## 10. Règles non-négociables (ADR-009 + ADR-017 + AMF + EU AI Act)

- **Voie D** : jamais d'API Anthropic à la consommation. Max 20x flat
  uniquement, via le claude-runner Win11.
- **Pas de signal BUY/SELL** : Ichor produit des biais probabilistes,
  jamais d'instruction d'achat/vente.
- **AMF DOC-2008-23** : information générale, pas de conseil personnalisé.
- **EU AI Act Article 50** : DisclaimerBanner permanent en bas de page.
- **Calibration publique** : Brier scores visibles sur `/calibration`.
- **Ichor n'exécute aucun ordre** : tu trades sur TradingView avec ton
  propre risk management.

---

## 11. Quand quelque chose ne marche pas

### Le batch 06:00 n'a pas tourné
```bash
ssh ichor-hetzner "sudo systemctl status ichor-session-cards-pre_londres.timer"
ssh ichor-hetzner "sudo journalctl -u ichor-session-cards@pre_londres.service -n 50 --no-pager"
```

### Une carte est verdict=blocked persistante
Cause typique : data manquante dans le pool. Va voir
`/v1/data-pool/{asset}` pour identifier les sections vides.

### Le claude-runner Win11 ne répond plus
ADR-010 : `claude auth logout && claude auth login --claudeai`.
Vérifier que les Scheduled Tasks `IchorClaudeRunnerUser` +
`IchorCloudflaredUser` sont en Running.

### Push notifications ne marchent plus sur iPhone
1. Va sur `/admin` → vérifie que VAPID est configuré
2. Sur iPhone : Réglages → Notifications → Ichor → autoriser
3. Re-tape "🔔 activer push" depuis l'app

---

## 12. Documents de référence

| Doc | Quand le lire |
|---|---|
| `docs/decisions/ADR-017-reset-phase1-living-macro-entity.md` | La vision contractée |
| `docs/VISION_2026.md` | Les 17 deltas + 5 sprints non-prévus livrés |
| `docs/SESSION_HANDOFF.md` | À chaque `/clear` Claude Code |
| `docs/PHASE_1_LOG.md` | Chronologie des chunks shipped |
| `README.md` | Top-level overview repo |
| `docs/research/macro-frameworks-2026.md` | Les frameworks par actif |

---

*Dernière update : 2026-05-04 après la session marathon de 31 commits.
Tout fonctionne en autonomie 24/7. Le système ne dort pas.*
