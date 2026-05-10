# Guide actions manuelles Eliot — 2026-05-10

> **Toi seul peux faire ces actions** parce qu'elles requièrent ta connexion à un compte (Cloudflare, Anthropic, GitHub) ou des privilèges admin Win11 (NSSM, suppression de fichier verrouillé).
>
> **Ce que Claude a déjà fait pour toi** : push origin main (22 commits), `pnpm install` apps/web2, `pre-commit install` (hook actif), cleanup 3/4 worktrees orphelins, 6 commits W85→W91 + 5 ADRs.
>
> **Format** : chaque action = pré-requis + étapes click-par-click + comment savoir que c'est fait + temps estimé.

## Table des matières

| #   | Action                                                                             | Priorité                           | Temps           | Pré-requis              |
| --- | ---------------------------------------------------------------------------------- | ---------------------------------- | --------------- | ----------------------- |
| 1   | [PRE-1 CF Access service token](#1-pre-1-cf-access-service-token)                  | **CRITIQUE** (bloque Cap5 STEP-6)  | 15 min          | Compte Cloudflare actif |
| 2   | [Anthropic "Help improve Claude" OFF](#2-anthropic-help-improve-claude-toggle-off) | **CRITIQUE** (privacy + EU AI Act) | 3 min           | Compte claude.ai logué  |
| 3   | [NSSM IchorClaudeRunner restore](#3-nssm-ichorclauderunner-restore)                | Moyen (workaround marche déjà)     | 10 min          | Powershell admin        |
| 4   | [Cleanup worktree zealous-banzai](#4-cleanup-worktree-zealous-banzai-physique)     | Bas (50 MB, gitignoré)             | 2 min           | Reboot Win11 d'abord    |
| 5   | [WGC W75 license decision](#5-wgc-w75-license-decision)                            | Bas (collecteur deferred)          | 5 min recherche | —                       |
| 6   | [GitHub Dependabot 3 vulnerabilities](#6-github-dependabot-3-vulnerabilities)      | Moyen                              | 5 min check     | Compte GitHub logué     |

---

## 1. PRE-1 CF Access service token

### Pourquoi c'est critique

Le tunnel Cloudflare `claude-runner.fxmilyapp.com` qui pointe vers ton PC Win11 est aujourd'hui **public** (`require_cf_access=false`). N'importe qui qui devine l'URL peut **drainer ton quota Claude Max 20x** en lançant des requêtes briefings depuis l'extérieur. Une fois Cap5 STEP-6 wired (intégration test e2e), le risque devient critique car les requêtes deviennent automatisées + plus fréquentes.

CF Access service token = jeton d'identification (client_id + client_secret) que Cloudflare valide au edge **avant** que la requête ne touche ton PC. Sans le bon header, Cloudflare retourne 401.

### Pré-requis

1. **Compte Cloudflare actif** (tu en as un, c'est le compte ID `6bc2ed8d6d675701a9a54f4f3d9b2499`).
2. **Cloudflare Zero Trust** activé sur ce compte. **Probablement pas encore activé** d'après l'audit `~/.claude/projects/D--Ichor/memory/ichor_cloudflare_api_limits.md:55-63`. Free up to 50 users.
3. **Domaine `fxmilyapp.com`** déjà dans Cloudflare (oui, vérifié zone ID).

### Étapes (Tier 1 — activer Cloudflare Access)

1. Va sur https://one.dash.cloudflare.com (Zero Trust dashboard).
2. **Si premier login** : Cloudflare te demande de créer un "team name". Choisis quelque chose comme `ichor-team`. Tu seras le seul user.
3. Choisis le **plan Free** (50 users gratuits — largement assez pour Ichor solo).
4. Click "Save" pour activer Zero Trust.

**Validation** : tu vois maintenant un menu de gauche avec "Access", "Gateway", "WARP", etc.

### Étapes (Tier 2 — créer une Access Application)

1. Toujours sur Zero Trust dashboard, click **Access** dans le menu de gauche → **Applications**.
2. Click bouton **"Add an application"** en haut à droite.
3. Choisis le type **"Self-hosted"**.
4. Remplis le formulaire :
   - **Application name** : `Ichor Claude Runner` (titre humain).
   - **Session Duration** : `24 hours` (par défaut OK).
   - **Application domain** : tape `claude-runner.fxmilyapp.com`. Cloudflare devrait auto-détecter ton zone.
   - Path : laisse vide (toute l'app).
5. Click **"Next"**.

### Étapes (Tier 3 — créer la policy + le service token)

6. Sur l'écran **"Add policies"** :
   - **Policy name** : `Ichor Service Token Only`.
   - **Action** : `Service Auth` (PAS "Allow" — service auth = uniquement les tokens, pas les humains).
   - **Configure rules** : section **Include**, choisis **"Service Token"** dans le menu, puis **"Any service token"**.
   - Click **"Save policy"**.
7. Click **"Next"**, puis **"Add application"** sur l'écran de récap. Application créée.

### Étapes (Tier 4 — créer le service token)

8. Toujours dans Zero Trust → **Access** → **Service Auth** (sous-menu).
9. Onglet **"Service Tokens"**. Click **"Create Service Token"**.
10. Nom : `ichor-runner-token-2026-05-10`.
11. Duration : `Non-expiring` (sinon 1 an et il faut renouveler).
12. Click **"Generate token"**.
13. **CRITIQUE** : Cloudflare te montre maintenant **`Client ID`** + **`Client Secret`**. Le secret n'est affiché **qu'une seule fois**. Copie-les immédiatement dans un endroit sûr (ton vault USB `E:\YONE_DATA\yone-secrets-vault.md`).

### Étapes (Tier 5 — wire les tokens dans Win11 claude-runner)

14. Sur Win11, ouvre **PowerShell elevated** (clic droit → "Run as Administrator").
15. Edit le fichier de config claude-runner. Ouvre `D:\Ichor\scripts\windows\start-claude-runner-standalone.bat` dans VS Code.
16. Ajoute ces 3 lignes après les autres `set ICHOR_RUNNER_*` (au début, après `@echo off`) :
    ```bat
    set ICHOR_RUNNER_REQUIRE_CF_ACCESS=true
    set ICHOR_RUNNER_CF_ACCESS_TEAM_DOMAIN=ichor-team.cloudflareaccess.com
    set ICHOR_RUNNER_CF_ACCESS_APPLICATION_AUD=<APP_AUD>
    ```
    Remplace `ichor-team` par ton team name si tu as choisi autre chose étape 2.
    `<APP_AUD>` est l'AUD tag de l'application Access — tu le trouves dans le **Dashboard CF → Access → Applications → click sur "Ichor Claude Runner" → Overview → Application Audience (AUD) Tag**. C'est un long string hex.
17. Save le `.bat`.

### Étapes (Tier 6 — wire les tokens côté Hetzner / apps/api)

18. Login SSH Hetzner : `ssh ichor-hetzner`.
19. Edit `/etc/ichor/api.env` : `sudo nano /etc/ichor/api.env`.
20. Ajoute ces 2 lignes :
    ```
    ICHOR_API_CF_ACCESS_CLIENT_ID=<le client_id de l'étape 13>
    ICHOR_API_CF_ACCESS_CLIENT_SECRET=<le client_secret de l'étape 13>
    ```
21. Save (`Ctrl+O`, Enter, `Ctrl+X`).
22. Restart le service api : `sudo systemctl restart ichor-api`.

### Validation

23. Sur ton PC Win11, **redémarre claude-runner** :
    - Tâches en arrière-plan (Win + R, tape `taskmgr`) → trouve le process `python.exe` qui tourne le runner → End task.
    - Re-lance `D:\Ichor\scripts\windows\start-claude-runner-standalone.bat` (double-clic depuis Explorer).
24. Test : `curl -H "CF-Access-Client-Id: <client_id>" -H "CF-Access-Client-Secret: <client_secret>" https://claude-runner.fxmilyapp.com/healthz`.
    Doit retourner `{"status":"ok",...}`.
25. Test négatif : `curl https://claude-runner.fxmilyapp.com/healthz` (sans headers) doit retourner **401 Unauthorized**.

### Rollback (si tu as fait une erreur)

- Sur Hetzner : retire les 2 lignes ajoutées à `/etc/ichor/api.env`, restart `ichor-api`.
- Sur Win11 : retire les 3 `set` lignes du `.bat`, redémarre claude-runner.
- Le système retourne à l'état pré-PRE-1 (public mais fonctionnel).

### Quoi faire après

Une fois validé, tu peux dire à Claude "PRE-1 fait, lance Cap5 STEP-6 e2e test". Cap5 sera 6/6.

---

## 2. Anthropic "Help improve Claude" toggle OFF

### Pourquoi c'est critique

Par défaut, le plan Claude Max 20x active le partage anonymisé de tes conversations pour entraîner Claude. Pour Ichor, ça signifie :

- Tes briefings macro (Pass 1-4) entrent dans le training set Anthropic pour 5 ans.
- Tes prompts data-pool (qui contiennent de la donnée FRED, Polymarket, MyFXBook) sont stockés.
- Cap5 STEP-6 (post-PRE-1) enverra des `query_db` sur `session_card_audit` rows qui finissent dans training.

EU AI Act §50 et l'audit interne Ichor exigent que tu sois **opt-out**.

### Pré-requis

Compte claude.ai logué avec le plan Max 20x.

### Étapes

1. Va sur https://claude.ai (logué).
2. Clic sur **ton avatar** en bas à gauche.
3. Click **Settings**.
4. Onglet **Privacy** dans la sidebar.
5. Cherche le toggle **"Help improve Claude"**. Probablement intitulé "Allow Anthropic to use your conversations to train models" ou similaire.
6. **Désactive** le toggle (slider à gauche / gris).
7. Cherche aussi **"Help improve Claude Code"** (toggle séparé pour le CLI). **Désactive aussi**.
8. Anthropic peut afficher un dialog de confirmation. Confirme **"Disable"** / **"Don't share"**.

### Validation

- Recharge la page Settings → Privacy. Les toggles doivent rester OFF.
- Date de dernière modification visible sous le toggle.

### Note importante

D'après la doc Anthropic 2026 (cf research W88) : **les conversations existantes** stockées avant l'opt-out **ne sont pas effacées** automatiquement. Pour les supprimer, il faut soumettre une demande GDPR/CCPA via https://privacy.claude.com → "Submit a privacy request".

Pour Ichor, pas critique : les briefings de la dernière semaine sont des analyses macro génériques sans donnée perso identifiable. Mais si tu veux être paranoïaque, soumets une demande de purge.

### Quoi faire après

Aucune action côté code Ichor. Juste vérifier 1× par mois que le toggle reste OFF (Anthropic peut le re-flipper sur upgrade plan).

---

## 3. NSSM IchorClaudeRunner restore

### Pourquoi c'est utile (mais pas critique)

Aujourd'hui claude-runner Win11 tourne en **standalone uvicorn** lancé par `start-claude-runner-standalone.bat` dans ton dossier Startup. Ça marche mais :

- Si le process plante, il ne redémarre PAS automatiquement.
- Pas de logs systématiques (juste stdout console).
- Pas de monitoring.

Le service NSSM `IchorClaudeRunner` est **paused** depuis 2026-05-02 parce que sa env list a perdu `ICHOR_RUNNER_ENVIRONMENT=development`. Restaurer ça fait revenir le service complet (auto-restart + logs + Win11 service control).

### Alternative plus moderne (recommandée)

Migrer vers **Servy** (https://github.com/aelassas/servy) qui est mieux maintenu que NSSM (NSSM unmaintained depuis 2017, RUNBOOK-014 le mentionne). Mais 2-3h de migration. Le NSSM existant marche encore après le fix env var.

Je recommande **NSSM restore** pour l'instant (10 min), Servy migration plus tard si besoin.

### Pré-requis

PowerShell **as Administrator** (clic droit → Run as Admin).

### Étapes

1. Ouvre PowerShell admin.
2. Vérifie l'état actuel du service :
   ```powershell
   nssm status IchorClaudeRunner
   ```
   Tu devrais voir `SERVICE_PAUSED`.
3. Vérifie l'env list actuelle :
   ```powershell
   nssm get IchorClaudeRunner AppEnvironmentExtra
   ```
   Tu devrais voir des variables comme `ICHOR_RUNNER_HOST=127.0.0.1` etc., **mais pas** `ICHOR_RUNNER_ENVIRONMENT=development`.
4. Set la variable manquante :
   ```powershell
   nssm set IchorClaudeRunner AppEnvironmentExtra `
     "ICHOR_RUNNER_ENVIRONMENT=development" `
     "ICHOR_RUNNER_HOST=127.0.0.1" `
     "ICHOR_RUNNER_PORT=8765" `
     "ICHOR_RUNNER_REQUIRE_CF_ACCESS=true"
   ```
   (Adapte les valeurs si tu as d'autres env vars dans le `.bat` — ce set REMPLACE l'env list, donc liste TOUTES les variables nécessaires. Inclus le `REQUIRE_CF_ACCESS=true` si tu as fait l'action 1 PRE-1.)
5. Stop le standalone uvicorn (qui tourne sur 8766) :
   ```powershell
   Get-Process python | Where-Object { $_.MainWindowTitle -like "*claude-runner*" } | Stop-Process -Force
   ```
6. Restart le service NSSM :
   ```powershell
   nssm restart IchorClaudeRunner
   ```
7. Check status :
   ```powershell
   nssm status IchorClaudeRunner
   ```
   Doit afficher `SERVICE_RUNNING`.

### Validation

```powershell
curl http://127.0.0.1:8765/healthz
```

Doit retourner `{"status":"ok",...}`. Note le port **8765** (NSSM) vs 8766 (standalone uvicorn). Tu peux aussi tester via le tunnel CF : `curl https://claude-runner.fxmilyapp.com/healthz`.

### Important — retirer le startup standalone

Une fois NSSM restoré, retire `start-claude-runner-standalone.bat` de ton dossier Startup pour éviter le double-runner :

1. Win + R → `shell:startup` → Enter.
2. Trouve le shortcut/lien vers `start-claude-runner-standalone.bat`.
3. Delete-le. Le service NSSM prend le relai au boot.

### Rollback

Si NSSM ne démarre pas correctement :

```powershell
nssm set IchorClaudeRunner Start SERVICE_DISABLED
```

Puis remets le `start-claude-runner-standalone.bat` dans Startup folder, et reboot. Tu reviens à l'état standalone.

---

## 4. Cleanup worktree zealous-banzai (physique)

### Pourquoi (bas)

Branche git déjà deletée + worktree déregistré du registre git. Reste juste 50 MB de `.venv` Python sur disque qui résiste à la suppression à cause d'un **Win11 file lock** (probablement antivirus en train de scanner des `.pyc`).

### Étapes

**Méthode 1 — reboot Win11** :

1. Reboot.
2. Open PowerShell.
3. ```powershell
   Remove-Item -Path 'D:\Ichor\.claude\worktrees\zealous-banzai-efc1c7' -Recurse -Force
   ```
4. Doit fonctionner après reboot (le file lock est libéré).

**Méthode 2 — sans reboot, désactiver antivirus temporairement** :

1. Win + I → Privacy & Security → Windows Security → Virus & threat protection.
2. Click "Manage settings" sous "Real-time protection".
3. Toggle OFF "Real-time protection" (Windows te demande UAC + un dialog).
4. ```powershell
   Remove-Item -Path 'D:\Ichor\.claude\worktrees\zealous-banzai-efc1c7' -Recurse -Force
   ```
5. **CRITIQUE** : re-toggle ON "Real-time protection" immédiatement après.

### Validation

```powershell
Test-Path D:\Ichor\.claude\worktrees\zealous-banzai-efc1c7
```

Doit retourner `False`.

---

## 5. WGC W75 license decision

### Contexte

W75 = collecteur World Gold Council quarterly XLSX (`gold-demand-by-country` hub). Sub-agent recherche a mappé tout :

- URL : `gold.org/download/file/{ID}/GDT_Tables_Q{N}{YY}_EN.xlsx`
- License : "Strict — extract requires explicit WGC consent for systematic extraction".

### Décision à prendre

**Option A** — Considérer "private research" framing OK :

- Tu utilises les données pour ton trading personnel single-user.
- Pas de redistribution, pas de publication.
- Pas de monétisation directe.
- Peut tomber sous "fair use" / "internal research" dans la plupart des juridictions.
- **Risque** : si WGC fait un audit, ils pourraient te demander d'arrêter.

**Option B** — Demander consent explicite :

- Email à `[email protected]` (probablement) ou via leur "Contact" form.
- Texte type :
  > Subject : Request for systematic extraction permission — single-user research
  > Body : I am Eliot Pena, an individual trader (FR). I would like to systematically extract the quarterly Gold Demand Trends XLSX from gold-demand-by-country/ for my private macro analysis (no redistribution, no commercial use, single-user). May I request your written consent for automated quarterly download ?
- Délai réponse : probablement 1-3 semaines.

**Option C** — Skip ce collecteur :

- Pas de WGC data dans data-pool.
- Tu te bases sur d'autres sources (Polymarket, FRED gold price, etc.) qui couvrent partiellement.

### Recommandation Claude

**Option B** si tu vises long-terme + zéro risque. **Option A** si tu accepts the risk faible et veux la data tout de suite.

**Option C** si tu peux vivre sans (ce qui est probablement le cas — la matrice cross-asset W79 ne dépend pas de WGC).

### Quoi faire après

Si Option A ou B et accord obtenu : ouvre un ticket "W92 candidate WGC collector" pour Claude, qui pourra implémenter le collecteur (~3-4h Claude).

Si Option C : marquer le sub-agent W75 research comme **DECLINED — Option C** dans `D:/Ichor/CLAUDE.md` "Things subtly broken or deferred" section, supprimer la mention.

---

## 6. GitHub Dependabot 3 vulnerabilities

### Pourquoi

GitHub a détecté 3 vulnérabilités sur le repo `fxeliott/ichor` lors du push de cette session :

- 2 moderate
- 1 low

### Étapes

1. Va sur https://github.com/fxeliott/ichor/security/dependabot
2. Tu verras une liste de 3 alertes. Pour chacune :
   - **Click** sur l'alerte pour voir le détail.
   - Note la **dépendance** concernée (probablement un package npm dans `apps/web2/pnpm-lock.yaml` ou un package Python dans `apps/api/pyproject.toml`).
   - Note la **CVE** (CVE-YYYY-NNNNN) et la **version fixée** (e.g. "Upgrade to >= X.Y.Z").
3. Pour chaque alerte :
   - **Si moderate ou low + dépendance non-critique** : ouvrir un ticket "W92 dependabot fix" pour Claude qui bumpera les versions.
   - **Si moderate ou low + dépendance critique** (ex: Next.js, FastAPI, anthropic-related) : escalader en priority haute.
4. **Alternative** — clic "Create Dependabot pull request" sur chaque alerte. GitHub crée automatiquement un PR qui bump la version. Tu peux merge directement ou attendre que Claude review.

### Recommandation

Pour 3 alertes (2 moderate + 1 low), 5 min suffisent à juste cliquer "Create Dependabot pull request" sur chaque, puis dire à Claude "review les 3 PRs Dependabot" qui les valide en parallèle.

### Validation

Page `https://github.com/fxeliott/ichor/security/dependabot` doit afficher 0 alerte open après merge des PRs.

---

## Résumé priorités

| Priorité | Action                           | Quand faire                                |
| -------- | -------------------------------- | ------------------------------------------ |
| 🔥 ASAP  | 1. PRE-1 CF Access service token | Avant prochain commit (sécurité quota Max) |
| 🔥 ASAP  | 2. Anthropic "Help improve" OFF  | Avant prochain prompt important (privacy)  |
| ⚠ Soon   | 6. Dependabot 3 vulnerabilities  | Cette semaine                              |
| OK       | 3. NSSM restore                  | Cette semaine (workaround marche)          |
| OK       | 5. WGC W75 decision              | Quand tu veux                              |
| Bas      | 4. Cleanup zealous-banzai        | Au prochain reboot                         |

Une fois 1 + 2 fait, dis à Claude **"PRE-1 fait + Anthropic OFF, lance Cap5 STEP-6 e2e"** → Cap5 = 6/6, le système est prêt pour la production.

---

## Notes finales

- **Ne fais jamais 1 et 2 en même temps**. Sépare-les pour pouvoir rollback indépendamment.
- **Garde une trace** de chaque changement dans ton vault USB `E:\YONE_DATA\yone-secrets-vault.md` (RUNBOOK-015 secrets rotation log).
- **Si tu as un doute** sur une étape : screenshot l'écran et envoie-le à Claude qui te dira quoi faire.
- **Toutes ces actions sont réversibles** sauf "Anthropic GDPR purge request" qui est définitif.

Bonne chance.
