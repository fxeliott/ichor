# Guide actions manuelles Eliot — 2026-05-10 (W94 refonte ULTRA débutant)

> **Toi seul peux faire ces actions** parce qu'elles requièrent ta connexion à un compte (Cloudflare, Anthropic, GitHub) ou des privilèges admin Win11.
>
> **Ce que Claude a déjà fait pour toi** (cumul session) : push origin main (24 commits W85→W93b), `pnpm install` apps/web2, `pre-commit install` actif (hook ichor-invariants vert), cleanup 4/5 worktrees, 5 ADRs (077-081), 9 invariants doctrinaux CI-guarded, **gh api PUT** active automated-security-fixes Dependabot, mailto: link WGC pré-encodé, sub-agent W93 deep-research T&C 2026 + adresse contact officielle.
>
> **Audit W93** révèle : NSSM service `RUNNING` (§3 OBSOLETE), Hetzner CF Access credentials DÉJÀ wired (§1 Tier 1+4+6 DONE), reste juste §1 Tier 2-3+5 (CF dashboard click + 1 commande PowerShell).
>
> **Format W94** : chaque section commence par "Pour les non-devs" (1 paragraphe contexte humain), puis click-by-click avec layout 2026 réel + table "Ce qui PEUT MAL TOURNER + fix".

## Table des matières

| #   | Action                                                                             | Priorité                           | Temps   | Pré-requis             |
| --- | ---------------------------------------------------------------------------------- | ---------------------------------- | ------- | ---------------------- |
| 1   | [PRE-1 CF Access — Tier 2-3 + Tier 5 only](#1-pre-1-cf-access-service-token)       | **CRITIQUE** (Tier 1+4+6 DONE)     | 8 min   | Compte CF logué        |
| 2   | [Anthropic "Help improve Claude" OFF](#2-anthropic-help-improve-claude-toggle-off) | **CRITIQUE** (privacy + EU AI Act) | 3 min   | Compte claude.ai logué |
| 3   | ~~NSSM restore~~ **OBSOLETE — service RUNNING**                                    | (skip)                             | (skip)  | (skip)                 |
| 4   | [Cleanup worktree zealous-banzai](#4-cleanup-worktree-zealous-banzai)              | Bas (50 MB)                        | 2 min   | Reboot Win11 d'abord   |
| 5   | [WGC W75 license decision](#5-wgc-w75-license-decision)                            | Bas (collecteur deferred)          | 3-5 min | iCloud Mail web        |
| 6   | [GitHub Dependabot 3 vulnerabilities](#6-github-dependabot-3-vulnerabilities)      | Moyen                              | 0-5 min | Compte GitHub logué    |

---

## 1. PRE-1 CF Access service token

### Audit W93 — état réel (vérifié par Claude SSH 2026-05-10)

**DÉJÀ FAIT (ne refais pas)** :

- Tier 1 : Cloudflare Zero Trust activé (sinon Hetzner n'aurait pas de credentials).
- Tier 4 : Service token créé. `client_id` + `client_secret` présents dans `/etc/ichor/api.env` Hetzner.
- Tier 6 : Hetzner side wired. `ichor-api` consomme les vars.

**À FAIRE PAR TOI** :

- Tier 2 : créer l'**Access Application** dans le dashboard CF (attacher le token au hostname).
- Tier 3 : créer la **policy "Service Auth"** sur l'application.
- Tier 5 : flip le flag Win11 NSSM (script auto fourni).

**Validation actuelle** : `curl https://claude-runner.fxmilyapp.com/healthz` retourne `HTTP 200` **sans auth** = tunnel public. Une fois Tier 2+3+5 faits, **401**.

### Pour les non-devs : c'est quoi exactement Cloudflare Access ?

Imagine que ton PC Win11 a une **porte d'entrée internet** (`claude-runner.fxmilyapp.com`) qui permet à Hetzner d'envoyer des requêtes Claude. Aujourd'hui cette porte est **non verrouillée** : n'importe qui qui devine l'URL peut frapper et drainer ton quota Claude Max 20x.

**Cloudflare Access** = un videur de boîte de nuit posté devant la porte. Tu lui donnes une liste : "laisse passer uniquement les gens qui montrent ce badge précis (notre service token)". Tout autre visiteur reçoit refus poli (HTTP 401) sans même que ton PC le sache.

Le **service token** = paire de longs codes alphanumériques :

- `client_id` (genre `f3481230f02f...d.access`) = le badge.
- `client_secret` (64 chars hex) = la signature secrète qui prouve que le badge est authentique.

Hetzner les envoie dans 2 headers HTTP (`CF-Access-Client-Id` + `CF-Access-Client-Secret`). Cloudflare les vérifie au edge (Paris, avant que ça arrive à ton PC), génère un **JWT** (jeton signé numériquement, comme un passeport temporaire 24h).

Pourquoi critique maintenant : Cap5 STEP-6 va automatiser des appels au runner. URL publique + appels automatisés = quelqu'un qui scrape pourrait drainer ton quota Max en quelques heures.

### Pré-requis

1. Tu es logué sur **Cloudflare** (https://dash.cloudflare.com) avec le compte qui possède `fxmilyapp.com`.
2. Tu as **PowerShell as Administrator** prêt à ouvrir (clic droit menu Démarrer → "Run as administrator" → UAC accepte → fenêtre bleue avec barre titre **"Administrator: Windows PowerShell"**).
3. Tu as **D:\Ichor** sur disque local (déjà OK).

### Tier 1 — Zero Trust ✅ DÉJÀ FAIT

Si tu veux retrouver ton **team name** : va sur `https://one.dash.cloudflare.com`. En haut à gauche sous le logo Cloudflare, un nom genre `eliot-team` ou sous-domaine `eliot-team.cloudflareaccess.com`. C'est ton team domain. Note-le pour Tier 5.

### Tier 2 — créer une Access Application (5 min)

**Pour les non-devs** : on dit à Cloudflare "voici une application web (le runner Claude) que je veux protéger ; à partir de maintenant, ne laisse passer aucune requête sans badge valide". L'application = la porte. La policy (Tier 3) = la liste des badges autorisés.

**Note layout 2026** : Cloudflare a réorganisé le menu en 2026. L'ancien `Access > Applications` est devenu `Access controls > Applications`. Le bouton de création s'appelle parfois "Add an application" parfois "Create new application" — les deux mènent au même formulaire.

#### Étapes click-by-click

1. Va sur `https://one.dash.cloudflare.com`. Tu arrives sur le dashboard Zero Trust.
2. Dans le menu de **gauche**, cherche **Access controls** (icône bouclier ou cadenas). Click → sous-menu se déplie avec **Applications**, **Policies**, **Service credentials**, **Tunnels**, etc.
   - Si tu vois **"Access"** tout court (pas "Access controls") : ancien layout, click dessus c'est pareil.
3. Click **Applications**. Page liste les applications déjà protégées (vide si première fois).
4. En **haut à droite**, gros bouton bleu **"Add an application"** (ou **"Create new application"**). Click.
5. Page **"Select an application type"** s'ouvre avec tiles :
   - Self-hosted and private (ou juste "Self-hosted")
   - SaaS
   - Private network
   - Infrastructure

   **Click le tile "Self-hosted"** = "j'héberge le serveur moi-même" (ton PC Win11 derrière le tunnel).

6. Formulaire **"Add a self-hosted application"** s'ouvre.

#### Remplir le formulaire

7. **Application name** : tape exactement `Ichor Claude Runner`.
8. **Session Duration** : laisse `24 hours`.
9. Section **"Add public hostname"** (parfois pliée — click pour déplier) :
   - **Subdomain** : tape `claude-runner`
   - **Domain** : dropdown → sélectionne `fxmilyapp.com`
   - **Path** : LAISSE VIDE

   Visuellement : `[claude-runner] . [fxmilyapp.com ▼] / [           ]`

   Si `fxmilyapp.com` n'apparaît pas dans le dropdown : ton compte CF n'a pas la zone activée. Stop, screenshot Win+Shift+S, envoie-le moi.

10. Section **"Identity providers"** : dé-coche TOUT si quelque chose est coché. On veut SEULS les service tokens.
11. Section **"Instant Auth"** : laisse OFF.
12. En bas, click bouton bleu **"Next"**.

#### Validation visuelle après Tier 2

Tu dois voir un écran **"Add policies"** avec titre "Configure policies for Ichor Claude Runner". Si page d'erreur rouge ou "domain conflict" : screenshot → envoie-moi.

### Tier 3 — créer la policy "Service Auth" (3 min)

**Pour les non-devs** : maintenant que la porte existe, on définit la **règle de filtrage** du videur. 3 actions possibles : **Allow** (humain qui se logge), **Block** (refuse), **Service Auth** (laisse passer UNIQUEMENT si service token valide). On veut Service Auth.

#### Étapes click-by-click

13. Sur l'écran "Add policies" :
    - **Policy name** : tape `Ichor Service Token Only`.
    - **Action** : dropdown → **`Service Auth`**.
      - **PIÈGE** : ne choisis PAS "Allow". Allow = humain qui doit se logger. Service Auth = robot avec token. Pour Ichor c'est le robot Hetzner, donc Service Auth.
    - **Session duration** : laisse `Same as application session timeout`.
14. Section **"Configure rules"**, sous-section **"Include"** :
    - Click **"+ Add include"** (ou "Add" / "+").
    - Selector dropdown → **"Service Token"**.
    - Value dropdown à droite → **"Any Access Service Token"** (ou "Any service token").

    Visuellement : `Include: [Service Token ▼]   [Any Access Service Token ▼]`

15. **Exclude** et **Require** : LAISSE VIDES.
16. En bas → **"Next"**.
17. Écran récap suivant ("Setup" / "Cookie settings") → **"Next"** sans rien changer.
18. Dernier écran "Review and add" → bouton **"Add application"** en bas à droite.

#### Validation visuelle après Tier 3

Retour sur la liste Applications avec `Ichor Claude Runner` apparaît avec statut vert "Active". Erreur rouge → screenshot.

### Tier 4 — service token ✅ DÉJÀ FAIT

Le service token existe et ses credentials sont dans `/etc/ichor/api.env` Hetzner. `client_id` = `f3481230f02f4964f4bac5a42b9b776d.access`. Tu n'as PAS besoin du secret pour Tier 5 ; seul l'**AUD tag** de l'application Access créée au Tier 2 est nécessaire.

### Tier 5 — récupérer AUD tag + flip Win11 NSSM (5 min)

**Pour les non-devs** : l'**AUD tag** (Application Audience Tag) = long code hex 64 chars qui identifie de façon unique TON application Access (Tier 2). Le service Win11 doit le connaître pour valider que les JWT reçus sont bien destinés à NOTRE application. C'est l'équivalent du "numéro de table" dans un restaurant.

#### Récupérer l'AUD tag

19. Sur la liste Applications, click **`Ichor Claude Runner`** (la ligne entière, ou bouton "Configure").
20. Page Overview → cherche section **"Application Audience (AUD) Tag"** (sous Overview ou Settings → onglet en haut).
21. Tag affiché comme `a1b2c3d4e5f6...` 64 chars hex avec bouton **Copy**. Click Copy → colle dans Notepad ou ton vault.

#### Récupérer le team domain

22. Dashboard Zero Trust → menu gauche scroll en bas → **Settings** (icône engrenage).
23. Cherche **"Team domain"** ou **"General"** → tu vois `https://eliot-team.cloudflareaccess.com`. Note la partie `eliot-team.cloudflareaccess.com` (sans `https://`).
    - Layout 2026 alternatif : si pas dans Settings General, cherche sous **Reusable components → Custom pages → Team domain**.

#### Flip Win11 NSSM via script auto

Claude a préparé un script PowerShell qui fait le flip atomiquement (lit env actuel, conserve vars existantes, ajoute REQUIRE_CF_ACCESS=true + TEAM_DOMAIN + APPLICATION_AUD, restart NSSM, smoke-test healthz).

24. Ouvre **PowerShell as Administrator** :
    - Menu Démarrer → tape `powershell` → click droit "Windows PowerShell" → **"Run as administrator"** → UAC accepte.
    - Vérifie barre titre = **"Administrator: Windows PowerShell"**. Sinon recommence.
25. Lance :

    ```powershell
    cd D:\Ichor
    .\scripts\windows\enable-cf-access-runner.ps1 `
        -TeamDomain "eliot-team.cloudflareaccess.com" `
        -ApplicationAud "<colle-le-AUD-tag-64-chars-hex>"
    ```

    Remplace par TES valeurs (étape 21 + 23).

26. Script affiche 4 étapes (statut NSSM, env actuel, env nouveau, restart). Si vert :
    ```
    DONE. CF Access enforcement is now ACTIVE.
    ```
    → gagné.

#### Validation post-Tier 5

27. Test négatif :

    ```powershell
    curl.exe -i https://claude-runner.fxmilyapp.com/healthz
    ```

    **Doit retourner `HTTP/2 401`** (ou 403). Si `200` :
    - `nssm status IchorClaudeRunner` doit dire `SERVICE_RUNNING`.
    - Tier 2+3 bien terminés (l'app apparaît dans la liste CF).
    - Attends 2 min (propagation CF edge).

28. Test positif (avec token, depuis Hetzner) :
    ```bash
    ssh ichor-hetzner "sudo grep ICHOR_API_CF_ACCESS /etc/ichor/api.env"
    ```
    Récupère `CLIENT_ID` + `CLIENT_SECRET`. Puis :
    ```bash
    curl -i -H "CF-Access-Client-Id: <client_id>" \
            -H "CF-Access-Client-Secret: <client_secret>" \
            https://claude-runner.fxmilyapp.com/healthz
    ```
    **Doit retourner `HTTP/2 200`** + body JSON `{"status":"ok",...}`.

### Rollback

PowerShell admin :

```powershell
nssm set IchorClaudeRunner AppEnvironmentExtra `
  "ICHOR_RUNNER_HOST=127.0.0.1" `
  "ICHOR_RUNNER_PORT=8765" `
  "ICHOR_RUNNER_LOG_LEVEL=INFO" `
  "ICHOR_RUNNER_CLAUDE_BINARY=C:\Users\eliot\.local\bin\claude.exe" `
  "ICHOR_RUNNER_ENVIRONMENT=development" `
  "ICHOR_RUNNER_REQUIRE_CF_ACCESS=false"
nssm restart IchorClaudeRunner
```

Retour à l'état pré-flip (public mais fonctionnel).

### Ce qui PEUT MAL TOURNER + comment fix

| Symptôme                                      | Cause                                       | Fix                                                        |
| --------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------- |
| Bouton "Add an application" introuvable       | Mauvais dashboard                           | Va sur `https://one.dash.cloudflare.com`                   |
| Dropdown Domain ne montre pas `fxmilyapp.com` | Zone pas active sur ce compte               | Switch compte (haut droite) vers celui qui a fxmilyapp.com |
| Action "Service Auth" pas dans dropdown       | Bug temporaire CF                           | Reload F5, recommence Tier 3                               |
| `nssm` introuvable PowerShell                 | Pas dans PATH                               | `where.exe nssm` ; sinon path complet                      |
| `curl.exe` pas reconnu                        | Win11 a `curl` alias vers Invoke-WebRequest | Utilise `curl.exe` explicitement                           |
| Test négatif tjrs 200 après 5 min             | Cache CF edge                               | Wait 30 min ou Caching > Purge Everything                  |
| AUD tag introuvable                           | Mauvais onglet                              | Cherche Overview, Settings, Application Configuration      |

### Quoi faire après

Dis à Claude **"PRE-1 fait, lance Cap5 STEP-6 e2e"** → Cap5 = 6/6.

---

## 2. Anthropic "Help improve Claude" toggle OFF

### Pour les non-devs : c'est quoi ce toggle ?

Anthropic a changé sa politique en sept 2025. Avant : conversations stockées 30 jours puis supprimées. Maintenant : toggle "Help improve Claude" ON par défaut (même sur Max 20x payant) → **conversations entrent dans le training set Anthropic 5 ans**. Si tu l'éteins, retour à 30 jours.

Pour Ichor : briefings macro (Pass 1-4), prompts data-pool (FRED/Polymarket/MyFXBook), Cap5 STEP-6 (`query_db` sur `session_card_audit`) — tout ça finit dans Claude future. EU AI Act §50 + audit interne Ichor exigent **opt-out**.

**Note 2026** (jurisprudence US v. Heppner fév 2026) : conversations consumer-plan AI **ne sont PAS protégées** par secret professionnel. "Discoverable" en justice. Pas critique pour Ichor (analyses macro non confidentielles), bon à savoir.

### Pré-requis

Tu es logué sur https://claude.ai avec ton compte Max 20x. Avatar visible bas-gauche sidebar = logué.

### Étapes click-by-click (Layout claude.ai 2026)

1. Va sur https://claude.ai. Écran chat principal avec sidebar gauche + zone chat centre.
2. **En bas à gauche**, click sur ton **avatar** (cercle initiale ou photo). Menu pop-up vers haut :
   ```
   ┌─────────────────────┐
   │ Settings            │
   │ Upgrade plan        │
   │ Help & support      │
   │ Log out             │
   └─────────────────────┘
   ```
3. Click **Settings**.
4. Modal Settings → sidebar gauche affiche : Profile, Account, Appearance, **Privacy**, Data controls, etc.
   Click **Privacy**.
5. Zone droite → cherche toggle **"Help improve Claude"** (parfois "Allow Anthropic to use your conversations to train models") :
   ```
   Help improve Claude                    [● ▬▬]  ← ON (bleu, à droite)
   ```
6. **Click le toggle** → glisse à gauche, devient gris :
   ```
   Help improve Claude                    [▬▬ ●]  ← OFF (gris, à gauche)
   ```
7. **Cherche aussi "Help improve Claude Code"** (toggle séparé pour le CLI), souvent juste en-dessous. **Désactive aussi**.
8. Anthropic peut afficher dialog confirmation **"Are you sure?"** → bouton "Disable" / "Don't share" → confirme.

### Validation

Recharge Settings → Privacy. Toggles **doivent rester OFF (gris à gauche)**. "Last modified: today" sous les toggles.

### Suppression conversations passées (optionnel, GDPR)

**Note importante 2026** : conversations existantes stockées avant l'opt-out **ne sont pas effacées rétroactivement**. Pour purger :

1. Va sur https://privacy.anthropic.com (redirige peut-être vers privacy.claude.com).
2. Click "Submit a privacy request".
3. Choisis "Delete my data" / "GDPR Article 17".
4. Délai 30 jours max.

Pour Ichor : pas critique. Optionnel paranoïa.

### Ce qui PEUT MAL TOURNER + comment fix

| Symptôme                                  | Cause                              | Fix                                      |
| ----------------------------------------- | ---------------------------------- | ---------------------------------------- |
| Pas d'onglet Privacy                      | A/B test UI                        | Cherche dans Account ou Data controls    |
| Toggle Claude Code absent                 | Pas encore lancé Claude Code logué | OK, prochaine fois — toggle web suffit   |
| Toggle se re-flip ON après quelques jours | Bug post-upgrade plan              | Vérifier 1× par mois (rappel calendrier) |
| Avatar bas-gauche introuvable             | Mode mobile / sidebar collapsed    | Click hamburger (3 lignes) haut-gauche   |

### Quoi faire après

Aucune action côté code Ichor. Vérifier 1× par mois.

---

## 3. ~~NSSM IchorClaudeRunner restore~~ — OBSOLETE

**Audit W93 (Claude SSH 2026-05-10)** : `nssm status IchorClaudeRunner` retourne `SERVICE_RUNNING`. Variable `ICHOR_RUNNER_ENVIRONMENT=development` présente. **Le service tourne. Tu n'as RIEN à faire ici.**

**Note W94 — clarification dual-runner** : audit `~/.cloudflared/config.yml` :

```yaml
ingress:
  - service: http://127.0.0.1:8765
```

Le tunnel CF cible bien **NSSM port 8765**, PAS le standalone uvicorn 8766. Donc :

- Standalone uvicorn 8766 = orphelin local (rien ne l'utilise externally).
- NSSM 8765 = sert le trafic Hetzner via tunnel.

Tu peux **killer le standalone** sans casser quoi que ce soit. Procédure (PowerShell) :

```powershell
Get-NetTCPConnection -LocalPort 8766 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

Et retire `start-claude-runner-standalone.bat` de ton dossier Startup (`shell:startup` dans Win+R) pour qu'il ne se relance pas au boot.

Optional cleanup — pas urgent. ~50 MB RAM gagné.

---

## 4. Cleanup worktree zealous-banzai

### Pour les non-devs : pourquoi c'est bloqué

Branche git supprimée + worktree déregistré du registre git. Mais le dossier `D:\Ichor\.claude\worktrees\zealous-banzai-efc1c7\` reste sur disque (50 MB de `.venv` Python). Pourquoi pas de simple `Remove-Item` ?

Win11 a un **file lock** : Windows Defender en train de scanner les `.pyc` Python compilés tient un handle ouvert → système refuse suppression jusqu'à ce que handle se libère. Le `.venv` contient ~5000 fichiers, scanner antivirus en a souvent un en main.

**Solution la plus propre** : **redémarrage** Win11 libère tous les handles.

### Reboot proprement Win11 (vraiment important)

**ATTENTION** : sur Win11, **Shutdown ≠ Restart** à cause de "Fast Startup". Shutdown sauve l'état du noyau dans hyberfil.sys et le re-charge → file locks restent. **Restart** force un cycle complet noyau → c'est CELUI-LÀ qu'il faut.

#### Procédure Reboot click-by-click

1. **Sauvegarde tout** (VS Code, browser tabs).
2. Click **Démarrer** (logo Windows bas-gauche).
3. Click icône **Power** (cercle avec trait vertical) bas-droite du menu Démarrer.
4. 3 options :
   ```
   ┌─────────────────┐
   │ Sleep           │
   │ Shut down       │
   │ Restart         │  ← celui-ci
   └─────────────────┘
   ```
5. Click **Restart** (PAS "Shut down").
6. Win11 redémarre. Wait 1-2 min jusqu'à login screen. Login.

### Étapes après reboot

7. Ouvre **PowerShell** (pas besoin admin).
8. Lance :
   ```powershell
   Remove-Item -Path 'D:\Ichor\.claude\worktrees\zealous-banzai-efc1c7' -Recurse -Force
   ```
9. Doit s'exécuter sans erreur (avertissements ignorables sur fichiers déjà absents).

### Validation

```powershell
Test-Path D:\Ichor\.claude\worktrees\zealous-banzai-efc1c7
```

Doit retourner **`False`**.

### Méthode alternative (sans reboot)

Désactive temporairement Windows Defender real-time protection :

1. Settings → Privacy & Security → Windows Security → Virus & threat protection → "Manage settings".
2. Toggle OFF "Real-time protection" (UAC accepte).
3. `Remove-Item -Recurse -Force` la commande.
4. **CRITIQUE** : re-toggle ON immédiatement.

### Ce qui PEUT MAL TOURNER + comment fix

| Symptôme                                        | Cause                                            | Fix                                                                             |
| ----------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------- |
| `Remove-Item` "Access denied" même après reboot | Programme se relance au boot et tient un fichier | Resource Monitor → CPU → "Associated Handles" → search "zealous" → kill process |
| Win11 fait "Updates and restart"                | Updates en attente                               | OK, force cycle complet, encore mieux                                           |
| Tu cliques "Shut down" par erreur               | Fast Startup → locks restent                     | Re-démarre via Restart cette fois                                               |

---

## 5. WGC W75 license decision

### Pour les non-devs : de quoi on parle ?

W75 = **collecteur de données** qu'on voulait écrire pour récupérer le rapport **"Gold Demand Trends"** trimestriel du **World Gold Council** (WGC, organisme de référence mondial sur l'or). Ces XLSX contiennent stats par pays sur demande or (joaillerie, banques centrales, ETF) — utile pour la matrice cross-asset Ichor pour les pairs XAU.

**Le problème** : WGC interdit dans ses Terms & Conditions le **scraping automatisé sans consentement écrit préalable**. Download manuel par un humain est OK ("personal, non-commercial use"), mais script auto à 04:00 chaque trimestre = "automated retrieval" → consent requis.

### Trois options

**Option A — "private research" framing (risque léger)** :

- Trading personnel single-user.
- Pas de redistribution, pas de monétisation.
- "Fair use" / "internal research" possible.
- **Risque** : WGC pourrait demander d'arrêter (cease & desist letter). Aucun cas public d'enforcement WGC trouvé.

**Option B — demander consent explicite (clean, 1-3 semaines)** :

- Email à `[email protected]` (cité explicitement T&C).
- Délai 1-3 semaines.
- Si accord : email de consent archive → bullet-proof.

**Option C — skip ce collecteur (zéro risque)** :

- Pas de WGC data.
- Tu te bases sur Polymarket, FRED gold price, COMEX positioning.
- Perte d'un signal utile mais non critique.

### Recommandation Claude (post W93 deep-research)

**Option B** = voie clean. Délai mais légalement bullet-proof. Option A = risque pratique faible mais violation contractuelle. Option C = zéro risque, perte signal acceptable.

Si tu choisis **Option B**, voici la procédure malgré la complication iCloud Mail.

### Pour les non-devs : pourquoi le `mailto:` lien peut ne pas marcher chez toi

Tu utilises **iCloud Mail dans le navigateur** (web, pas app native). Win11 quand tu cliques `mailto:[email protected]` essaie d'ouvrir TON application email par défaut système :

- App Outlook native Win11 → vide
- Microsoft Mail → vide
- Aucune app configurée → erreur

**iCloud Mail web ne s'enregistre PAS comme handler mailto:** dans Windows. Donc le lien ne peut pas ouvrir iCloud Mail dans le browser automatiquement.

**Solution** : copier-coller manuel.

### Procédure manuelle copy-paste (recommandée pour iCloud)

1. Ouvre iCloud Mail navigateur : https://www.icloud.com/mail
2. Login si nécessaire.
3. Click **"Compose"** (icône crayon, en haut) ou **"New message"**.
4. Champ **"À" / "To"** :
   ```
   [email protected]
   ```
5. Champ **"Subject" / "Sujet"** :
   ```
   Permission request — quarterly download of GDT Tables XLSX for private research
   ```
6. Corps message :

   ```
   Dear World Gold Council team,

   I am Eliot Pena, an individual private trader based in France, and I am
   writing to request your explicit consent for a limited, automated retrieval
   of the Gold Demand Trends quarterly XLSX tables (4 downloads per year)
   from Goldhub.

   The use case is strictly single-user private macro research feeding my own
   discretionary trading decisions. I commit to:

     - no redistribution, no publication, no commercial use, no derivative product;
     - no public sharing of the raw data or any transformation thereof;
     - citation of "World Gold Council, Metals Focus" wherever the data informs my notes;
     - immediate cessation of any automated retrieval upon your request, with
       no further action required on your part.

   If a different channel or a formal license is more appropriate for this
   scope, I would be grateful for your guidance.

   Thank you for your time.

   Kind regards,
   Eliot Pena
   eliott.pena@icloud.com
   ```

7. Vérifie que **From:** est bien `eliott.pena@icloud.com`.
8. Click **Send**.

### Validation

- Email apparaît dans dossier "Sent" / "Envoyés" iCloud.
- Possible auto-reply "Thanks for your inquiry, we'll get back to you within X days".

### Ce qui PEUT MAL TOURNER + comment fix

| Symptôme                            | Cause                                      | Fix                                                                   |
| ----------------------------------- | ------------------------------------------ | --------------------------------------------------------------------- |
| Lien mailto ouvre Outlook/Mail vide | iCloud pas configuré comme handler système | Procédure manuelle copy-paste ci-dessus                               |
| Email rejeté par WGC mailbox        | Adresse obsolète                           | Cherche https://www.gold.org/contact-us — utilise leur form           |
| Pas de réponse après 4 semaines     | Mailbox engorgée                           | Follow-up court : "Subject: RE: Permission request — gentle reminder" |
| Réponse en allemand/chinois         | Redirect interne WGC                       | Reply en anglais, garde subject original                              |

### Quoi faire après

- Option A ou B + accord : ouvre ticket "W92 candidate WGC collector" pour Claude (~3-4h).
- Option C : marquer W75 **DECLINED — Option C** dans `D:/Ichor/CLAUDE.md`.

Sources : [WGC Terms](https://www.gold.org/terms-and-conditions), [Goldhub data hub](https://www.gold.org/goldhub/data/gold-demand-by-country).

---

## 6. GitHub Dependabot 3 vulnerabilities

### Pour les non-devs : c'est quoi Dependabot ?

**Dependabot** = robot officiel GitHub qui scanne automatiquement `package.json` (npm), `pyproject.toml` (Python), etc. Quand il détecte un package avec **vulnérabilité connue** (CVE, base publique des trous sécurité), il :

1. Crée une **Pull Request** automatique pour upgrader vers version safe.
2. Affiche une **alerte** dans l'onglet Security du repo.

C'est sûr (officiel GitHub) et passif (jamais merge tout seul sans ton OK).

### Audit W93 (Claude `gh api` 2026-05-10)

- ✅ `vulnerability-alerts` activé sur `fxeliott/ichor`.
- ✅ `automated-security-fixes` activé (`{"enabled":true,"paused":false}`).
- ⏳ Au moment de l'audit : 0 PR Dependabot. **Dependabot scanne périodiquement, créera les PRs dans les minutes/heures suivantes**.

### Important — changement 2026 : commands deprecated

Depuis **27 janvier 2026**, GitHub a déprécié les commandes commentaires Dependabot :

- `@dependabot merge` ❌
- `@dependabot squash and merge` ❌
- `@dependabot close` ❌

**À la place** : boutons natifs GitHub UI (squash and merge), `gh CLI`, ou bouton "auto-merge".

### Pré-requis

Logué sur https://github.com avec compte `fxeliott`. 2FA recommandé.

### Étape 1 — vérifier les Dependabot PRs (refresh dans qq heures)

1. Va sur https://github.com/fxeliott/ichor/pulls
2. Cherche celles avec :
   - **Auteur** : `dependabot[bot]` (badge bot bleu à côté du nom)
   - **Avatar** : icône Dependabot (robot vert/jaune)
   - **Titre type** : `chore(deps): bump <package> from <old> to <new>` ou `[Security] Bump <package> from X to Y`

   Layout 2026 :

   ```
   ┌─────────────────────────────────────────────────────────────────────┐
   │ [icône bot] [Security] Bump axios from 1.5.0 to 1.7.4              │
   │ #142 opened 3 hours ago by dependabot[bot]   [security][dependencies] │
   │ Bumps axios from 1.5.0 to 1.7.4. Resolves CVE-2024-XXXXX (HIGH)    │
   └─────────────────────────────────────────────────────────────────────┘
   ```

3. Tu devrais voir 3 PRs (correspond aux 3 vulns : 2 moderate + 1 low).

### Étape 2 — review chaque PR (5 min total)

**Pour les non-devs** : on vérifie 3 choses :

1. **C'est bien Dependabot officiel** (pas un fake).
2. **Le bump est mineur** (1.5.0 → 1.7.4 = OK ; 1.x → 2.x = MAJOR, peut casser).
3. **Les tests CI passent** (icône verte ✓ en bas).

#### Click-by-click

4. Click le titre PR pour ouvrir.
5. Header PR : à gauche du nom "dependabot[bot]" il y a badge **"bot"** bleu. Si humain (pas badge bot) → STOP, screenshot.
6. Lis titre : `1.5.0 → 1.7.4` (mineur ou patch) → SAFE. `1.x → 2.x` (MAJOR) → review prudent : "Files changed" → vérifie pas de breaking change visible.
7. Scroll en bas → section **"Checks"** :
   ```
   ┌────────────────────────────────────────────┐
   │ ✓ All checks have passed                   │
   │   ✓ python (3.12) — 4 jobs                  │
   │   ✓ web2 (build) — 2 jobs                   │
   │   ✓ shell-lint                              │
   │   ✓ audit                                   │
   └────────────────────────────────────────────┘
   ```
   Tous **doivent être verts ✓**. Si rouge ✗ ou jaune ⏳ :
   - **Jaune** : tests en cours, attends 5-10 min reload.
   - **Rouge** : régression réelle. Click le check rouge → "Details" → lis l'erreur. Si pas sûr, screenshot → Claude.

### Étape 3 — merge la PR

8. Si tout vert : juste au-dessus des checks, bouton vert :

   ```
   ┌────────────────────────────────────────────┐
   │   [▼ Squash and merge]   ← clique          │
   └────────────────────────────────────────────┘
   ```

   Dropdown ▼ → 3 options :
   - "Create a merge commit"
   - "Squash and merge" ← **utilise**
   - "Rebase and merge"

   Click **"Squash and merge"**.

9. Fenêtre confirmation avec titre commit + body pré-remplis. Laisse tels quels. Click **"Confirm squash and merge"**.
10. PR passe statut **Merged** (badge violet).
11. Répète 4-10 pour chaque PR Dependabot.

### Étape 4 — vérification finale

12. https://github.com/fxeliott/ichor/security/dependabot
13. Doit afficher **0 alerte open** (ou nombre réduit si pas toutes merge-able).

### Si dans 24h aucune PR n'apparaît

Cause possible : `.github/dependabot.yml` manquant ou ne couvre pas tous les écosystèmes (npm + pip).

Demande à Claude : "Claude, crée `.github/dependabot.yml` pour Ichor". Contenu minimal :

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/apps/web2"
    schedule:
      interval: "weekly"
  - package-ecosystem: "pip"
    directory: "/apps/api"
    schedule:
      interval: "weekly"
```

### Méthode alternative — auto-merge

Sur PR Dependabot, à côté de "Squash and merge", bouton **"Enable auto-merge (squash)"**. Click → confirm. PR mergée auto quand checks finissent. Pour Ichor je recommande **manuel** — tu vois ce qui rentre.

### Ce qui PEUT MAL TOURNER + comment fix

| Symptôme                                              | Cause                      | Fix                                                                    |
| ----------------------------------------------------- | -------------------------- | ---------------------------------------------------------------------- |
| Aucune PR après 48h                                   | Config absent ou désactivé | Crée `.github/dependabot.yml`                                          |
| PR avec checks rouges (test_invariants_ichor.py fail) | Régression réelle bump     | NE MERGE PAS. Demande à Claude "investigate dependabot PR #XX failure" |
| Bump MAJOR sur dep critique (FastAPI, Next.js)        | Breaking changes possibles | Demande Claude review avant merge                                      |
| Bouton "Squash and merge" gris                        | Branch protection          | Vérifie CODEOWNERS / checks / pas conflit                              |
| Comment "@dependabot merge" ignoré                    | Deprecated jan 2026        | Bouton UI natif                                                        |

### Quoi faire après

`https://github.com/fxeliott/ichor/security/dependabot` doit afficher **0 alerte open** = mission accomplie.

---

## Résumé priorités (post-W94)

| Priorité | Action                          | Quand                                      |
| -------- | ------------------------------- | ------------------------------------------ |
| 🔥 ASAP  | §1 PRE-1 CF Access (Tier 2-3+5) | Avant prochain commit (sécurité quota Max) |
| 🔥 ASAP  | §2 Anthropic "Help improve" OFF | Avant prochain prompt important            |
| ⚠ Soon   | §6 Dependabot 3 PRs merge       | Quand PRs apparaissent (qq heures)         |
| OK       | §5 WGC decision (A/B/C)         | Quand tu veux                              |
| Bas      | §4 Cleanup zealous-banzai       | Au prochain reboot                         |

**Total ~13 min cumulé** (vs ~40 min initial).

Une fois §1+§2 done, dis à Claude **"PRE-1 fait + Anthropic OFF, lance Cap5 STEP-6 e2e"** → Cap5 = 6/6, le système est prêt pour la production.

---

## Notes finales

- **Ne fais jamais §1 et §2 en même temps**. Sépare-les pour rollback indépendant.
- **Garde une trace** dans ton vault USB `E:\YONE_DATA\yone-secrets-vault.md` (RUNBOOK-015).
- **Si tu as un doute** : screenshot Win+Shift+S → envoie à Claude.
- **Toutes ces actions sont réversibles** sauf "Anthropic GDPR purge request" qui est définitif.

Bonne chance.
