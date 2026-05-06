# RUNBOOK-008: Anthropic Max 20x banned / Claude CLI revoked

- **Severity**: P0 if Couche-1 briefings are user-visible critical
  (otherwise P1 — fallback chain runs degraded mode)
- **Last reviewed**: 2026-05-02
- **Time to resolve (target)**: 30 min to fallback fully active

## Trigger

- `claude -p "ping"` returns 403 / "organization does not have access" /
  "your subscription has been suspended"
- Hetzner cron `ichor-briefing-*.service` exits non-zero with `claude_runner_call_failed`
- claude-runner `/v1/usage` shows 100% subprocess errors over the last hour
- Email from Anthropic about "Terms of Service violation"

## Immediate actions (first 5 min)

1. **Confirm the scope** — is it the OAuth session or the account itself?

   ```bash
   ssh ichor-hetzner
   curl -H "CF-Access-Client-Id: ..." -H "CF-Access-Client-Secret: ..." \
     https://<TUNNEL-UUID>.cfargotunnel.com/v1/usage | jq
   ```

   Then on Win11:

   ```powershell
   claude auth status
   claude -p "ping" --model haiku
   ```

2. **Try a re-login first** (recoverable):

   ```powershell
   claude auth logout
   claude auth login --claudeai
   ```

   Then re-test. If it works, restart the service:

   ```powershell
   Restart-Service IchorClaudeRunner
   ```

3. **If re-login fails OR Anthropic email confirms account action**:
   the Voie D path is dead. Activate fallback chain (next steps).

## Recovery — activate fallback chain (Couche 2 takes over Couche 1)

The architecture (`docs/ARCHITECTURE_FINALE.md`) anticipates this. Per
ADR-009 §"Risk acceptance", the fallback chain is:

```
claude-runner (Max 20x)  ←  primary (now broken)
   ↓ on error
Cerebras free 30 RPM     ←  step-down 1 (degraded quality, same prompt)
   ↓ on error
Groq free 1000 RPD       ←  step-down 2 (further degraded)
   ↓ on error
static template          ←  last resort (timestamp + alerts list, no analysis)
```

### Implementation steps

1. **Verify Cerebras + Groq keys are decryptable** on Hetzner:

   ```bash
   ssh ichor-hetzner
   SOPS_AGE_KEY_FILE=/etc/sops/age/key.txt sops --decrypt /root/infra/secrets/cerebras.env | grep CEREBRAS_API_KEY
   SOPS_AGE_KEY_FILE=/etc/sops/age/key.txt sops --decrypt /root/infra/secrets/groq.env | grep GROQ_API_KEY
   ```

   If either is empty: regenerate at https://cloud.cerebras.ai or https://console.groq.com (5 min each).

2. **Toggle the briefing CLI to fallback mode**:
   In `apps/api/src/ichor_api/cli/run_briefing.py`, the `_post_to_claude_runner`
   call is wrapped in a try/except. The fallback path lives in `packages/agents/`
   `fallback.py` (Cerebras → Groq).

   Set the env var:

   ```bash
   sudo systemctl edit ichor-briefing@.service
   # Add:
   # [Service]
   # Environment=ICHOR_API_DISABLE_CLAUDE_RUNNER=true
   sudo systemctl daemon-reload
   ```

3. **Trigger a manual briefing** to validate Couche-2 fallback works:

   ```bash
   sudo systemctl start ichor-briefing@pre_londres.service
   sudo journalctl -u ichor-briefing@pre_londres.service -f
   ```

4. **Decision point** (Eliot):
   - Wait for Anthropic appeal? (typical 1-7 days, no guarantee)
   - Switch to Voie C (Anthropic API key, supersede ADR-009)? Setup ~15 min:
     - Create new API key at console.anthropic.com (workspace `ichor-prod`)
     - `sops` infra/secrets/anthropic.env, set `ANTHROPIC_API_KEY=...`
     - Refactor `subprocess_runner.py` to call SDK instead of `claude` CLI
     - Set monthly budget cap $25-50 to prevent surprise bills
   - Stay on Cerebras+Groq permanently (free, lower quality)?

## Post-incident

- File appeal with Anthropic if account was suspended (sometimes recoverable)
- If Voie C chosen: write ADR-011 superseding ADR-009
- Update PHASE_0_LOG with the resolution path
- If account was banned for automation pattern: consider running briefings
  less frequently (4/day → 2/day) when the new path is established
