# Ichor pickup prompt — fresh session after 2026-05-06 marathon

> Copy-paste into a new Claude Code session in `D:\Ichor` after `/clear`.

---

Lis dans cet ordre :
1. `D:\Ichor\CLAUDE.md` (auto-injecté)
2. `~/.claude/projects/D--Ichor/memory/MEMORY.md` puis :
   - `ichor_pending_todos_2026-05-06.md` — ma checklist immédiate
   - `ichor_eliot_directives.md` — mes directives standing
   - `ichor_claude_code_2026_stack.md` — la stack Claude Code project-scoped
   - `ichor_session_2026-05-06_session_cards_recovery.md` — narratif du marathon
3. `D:\Ichor\docs\SESSION_LOG_2026-05-06.md` — le log de session détaillé
4. `D:\Ichor\docs\decisions\ADR-024-session-cards-five-bug-fix.md` — root cause des 5 bugs récents

État production (vérifié 2026-05-06 03:15 CEST) :
- 4-pass session-cards pipeline restauré, 16 cards générées sur 8 assets aujourd'hui
- 49+ timers ichor-* actifs, Living Entity loop chaînée par `After=`
- 27/33 alertes ACTIVE, 4/6 dormant maintenant wired (RR25 + LIQUIDITY_TIGHTENING déployées, FOMC/ECB_TONE code-ready en attendant `pip install transformers torch` sur Hetzner)
- Tests : 959 passants (82 agents + 52 brain + 17 runner + 771 api + 37 web2)
- Migration head : 0027 (extend session_type CHECK pour ny_mid/ny_close)
- Couche-2 5 agents tournent via `claude:haiku` (ADR-023)

Bloqueurs externes :
- A.3 sécurité CF Access tunnel — j'ai besoin que tu génères un service token Cloudflare Access (5 min via dashboard) et me passes les `client_id` + `client_secret`
- A.4 NSSM service IchorClaudeRunner Paused — j'ai besoin que tu lances une commande PowerShell admin (cf `ichor_pending_todos_2026-05-06.md` §A.4)

Sprints D restants (non bloqués) :
- D.1 Brier Optimizer V2 (per-factor SGD sur drivers JSONB column 0026)
- D.3 Port 5 routes web1 → web2 + décommissioner apps/web
- D.4 CI Wave 5 ramp (mypy/pytest blocking)
- Petites finitions : suppression `packages/shared-types` stub, refactor `_VALID_SESSIONS` duplicate, diagnostic audit.log figé depuis 2026-05-01

Mes directives standing (déjà dans la mémoire — résumé) :
- "Le plus qualitatif possible, le plus complet possible, le plus autonome et automatique possible, le plus intelligent omniscient puissant performant maniaque possible"
- Triple expertise : trading + dev + Claude Code
- WebSearch systématique pour l'état du monde
- Pas mélanger, pas halluciner, pas dégraisser — que monter
- Plan Mode + verifier subagent + atomic increments
- `/restate` ou `brief-translator` à >200 mots
- Avant `git push` → toujours montrer le diff complet, jamais sans validation

Quand tu reprends, commence par invoquer le sub-agent `ichor-navigator` (`@ichor-navigator`) avec une question simple pour valider qu'il fonctionne, puis attaque la priorité que je te donne.

Si je dis juste "continue", attaque dans l'ordre de `ichor_pending_todos_2026-05-06.md` :
1. D.1 Brier V2 (sprint conséquent mais autonome)
2. D.3 Port routes web1 (utilise le skill `ichor-dashboard-component`)
3. Petites finitions
4. D.4 CI Wave 5

Les 2 bloqueurs externes (A.3, A.4) restent en attente de moi.
