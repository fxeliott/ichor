# ADR-010: claude -p returns 403 "organization access" — investigation needed

- **Status**: Pending Eliot action (re-login Claude Code)
- **Date**: 2026-05-02
- **Decider**: TBD (Eliot to verify after `claude auth login` redo)

## Context

Live end-to-end test of the claude-runner local service hit:

```
claude -p "test" --output-format json --model haiku --no-session-persistence
```

Returns:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": true,
  "api_error_status": 403,
  "result": "Your organization does not have access to Claude. Please login again or contact your administrator."
}
```

`claude auth status` reports the account as healthy:
```json
{
  "loggedIn": true,
  "authMethod": "claude.ai",
  "apiProvider": "firstParty",
  "email": "delahoussejulien78@gmail.com",
  "orgId": "be384137-2a35-416f-bb1a-3d12bb04d194",
  "subscriptionType": "max"
}
```

Reproduced on all model aliases (`haiku`, `sonnet`, `opus`, `claude-sonnet-4-6`,
no-flag). Same 403, identical message. Not a CLI flag issue.

## Hypotheses

1. **OAuth token desync** — `loggedIn: true` may be cached, but the
   refresh token might have expired silently. Fix: `claude auth logout && claude auth login`.
2. **Anthropic flagged the OAuth for automation pattern** — Per the warning
   in ARCHITECTURE_FINALE: "Anthropic has cut OpenClaw and 3rd-party agents
   of Max in April 2026". Running `claude -p` headless from a bash session
   may be triggering the same heuristic. The Voie D mitigation (briefings
   grouped 4×/day) hasn't been load-tested yet.
3. **Org-level access toggle** — Anthropic added per-org access controls
   recently. The default org "delahoussejulien78@gmail.com's Organization"
   might need explicit Claude Code access enabled at console.claude.com.
4. **Anthropic transient outage** — checked status pages: nothing reported
   2026-05-02 17:30 UTC.

Eliot's interactive Claude Code session worked earlier today (used to write
a lot of Ichor code), so the blocker likely landed in the last few hours.

## Action required from Eliot

Try in this order (each takes <2 min):

```powershell
# 1. Refresh login (most likely fix)
claude auth logout
claude auth login --claudeai

# 2. If 1 doesn't fix it: check the org settings
# Open https://claude.ai/settings/organization
# Verify "Claude Code access" is enabled for personal org

# 3. If neither: long-lived token (different code path)
claude setup-token
# Follow the browser flow, copy the token
# Configure the service: nssm set IchorClaudeRunner AppEnvironmentExtra ICHOR_RUNNER_CLAUDE_AUTH_TOKEN=<token>
# (would require subprocess_runner to honor the token via --auth-token flag if it exists)
```

After the fix, retest:
```bash
curl -X POST http://127.0.0.1:8765/v1/briefing-task \
  -H "Content-Type: application/json" \
  -d '{"briefing_type":"pre_londres","assets":["EUR_USD"],"context_markdown":"ping","model":"haiku","effort":"low"}'
```

## Consequences if unresolved

- Voie D Couche 1 (qualitative briefings via Max 20x) **non-functional** until fixed.
- Couche 2 (Cerebras + Groq) + Couche 3 (ML local) keep working.
- Phase 0 W3 step 23 (1-week consumption test of Max 20x) blocked.
- Phase 1 launch blocker.

If permanent (account flagged), fallback options:
- Switch to ANTHROPIC_API_KEY mode (Voie C, $25-50/mo prod) — supersedes ADR-009.
- Switch to free Cerebras+Groq for ALL agents (lower quality but $0).

## References

- `apps/claude-runner/logs/stderr.log` (post-redeploy)
- `docs/ARCHITECTURE_FINALE.md` "Anthropic risk accepted in conscience" section
- `docs/decisions/ADR-009-voie-d-no-api-consumption.md`
