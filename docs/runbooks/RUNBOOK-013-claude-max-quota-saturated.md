# RUNBOOK-013: Claude Max 20x quota saturated (rate-limited but not banned)

- **Severity**: P1 — degrades briefing freshness; not catastrophic if fallback chain runs
- **Last reviewed**: 2026-05-04
- **Time to resolve (target)**: 30 min to fallback active; 4-5 h to natural quota reset

## Trigger

- `claude -p "ping"` returns `429` with body containing `"rate_limit_exceeded"` or `"5-hour rolling cap reached"` (NOT `"organization does not have access"` — that's a ban, see [RUNBOOK-008](RUNBOOK-008-anthropic-key-revoked.md)).
- Hetzner cron `ichor-briefing-*.service` exits `claude_runner_call_failed` with HTTP 429 in journalctl.
- claude-runner `/v1/usage` (`http://localhost:8766/v1/usage`) shows `"messages_remaining": 0` or `"reset_at": "..."` ≥ 30 min in the future.
- [Anthropic status page](https://status.anthropic.com) shows degraded service across plans (less likely but check).

## Distinguish from RUNBOOK-008 (account ban)

|                      | RUNBOOK-013 (this) — quota saturated | RUNBOOK-008 — banned               |
| -------------------- | ------------------------------------ | ---------------------------------- |
| HTTP code            | 429                                  | 403 / 401 with "suspended"         |
| Recovers in          | 4-5 hours (rolling cap) / next week  | Manual review by Anthropic         |
| Email from Anthropic | no                                   | yes — "Terms of Service violation" |
| Action               | wait OR fallback                     | immediate fallback + escalation    |

If unsure, run the diagnostic in [RUNBOOK-008 §1](RUNBOOK-008-anthropic-key-revoked.md).

## Immediate actions (first 5 min)

### 1. Confirm it's a quota issue, not a ban

```powershell
# On Win11
claude -p "ping" --model haiku
# If 429: read the response. Look for "rolling 5-hour cap" or "weekly cap".
# If 403: stop, run RUNBOOK-008 instead.
```

```bash
# From Hetzner
curl -fsS http://localhost:8766/v1/usage \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" | jq
```

The runner exposes the 5-hour rolling and the 7-day rolling counters. If
`reset_at` is within 30 min, **option A** (wait) may be acceptable.

### 2. Estimate impact

Skip fallback only if:

- `reset_at` < 30 min from now, AND
- Next scheduled briefing is more than 30 min away, AND
- No counterfactual Pass 5 expected from Eliot in that window.

Otherwise → fallback (next section).

## Fallback activation

Same chain as RUNBOOK-008 §"Recovery", but **transient** (we expect to
revert to Claude as soon as quota resets).

### 1. Toggle fallback flag in feature_flags table

After Phase D, this becomes a single SQL update on `feature_flags`:

```sql
INSERT INTO feature_flags (key, enabled, rollout_pct, description, updated_by)
VALUES (
  'couche2_fallback_active', TRUE, 100,
  'Force Cerebras/Groq for all Couche-2 calls (RUNBOOK-013 active)',
  'oncall'
)
ON CONFLICT (key) DO UPDATE
SET enabled = TRUE, rollout_pct = 100,
    updated_at = now(), updated_by = 'oncall';
```

Until Phase D, edit `apps/api/src/ichor_api/services/llm_router.py` (when
it lands) or set `ICHOR_API_FORCE_FALLBACK=true` in `/etc/ichor/api.env`
and restart `ichor-api`.

### 2. Verify Cerebras + Groq tokens decryptable on Hetzner

```bash
ssh ichor-hetzner
SOPS_AGE_KEY_FILE=/etc/sops/age/key.txt sops --decrypt /opt/ichor/infra/secrets/cerebras.env | grep CEREBRAS_API_KEY
SOPS_AGE_KEY_FILE=/etc/sops/age/key.txt sops --decrypt /opt/ichor/infra/secrets/groq.env | grep GROQ_API_KEY
```

If empty/missing: regenerate at <https://cloud.cerebras.ai> or
<https://console.groq.com>. Re-encrypt with SOPS:

```bash
sops --encrypt --in-place infra/secrets/cerebras.env
git add infra/secrets/cerebras.env && git commit -m "rotate cerebras key (RUNBOOK-013)"
```

### 3. Trigger a sanity briefing

```bash
ssh ichor-hetzner
sudo systemctl start ichor-briefing-pre_londres.service
journalctl -u ichor-briefing-pre_londres.service -f
```

The service should now log `llm_provider=cerebras` (or groq) and complete
without 429.

### 4. Notify Eliot

```bash
# Or use the push system if available:
curl -X POST http://localhost:8000/v1/push/test \
  -H "Content-Type: application/json" \
  -d '{"title":"RUNBOOK-013 active","body":"Couche-2 on Cerebras/Groq fallback. Briefings degraded quality. Reset at HH:MM."}'
```

## Recovery — switching back to Claude

### 1. Confirm quota reset

```powershell
claude -p "ping" --model haiku
# Should return success with no 429.
```

```bash
curl -fsS http://localhost:8766/v1/usage  # messages_remaining > 0
```

### 2. Disable fallback flag

```sql
UPDATE feature_flags
SET enabled = FALSE, rollout_pct = 0,
    updated_at = now(), updated_by = 'oncall'
WHERE key = 'couche2_fallback_active';
```

Or unset the env var and restart `ichor-api`.

### 3. Verify a briefing runs through Claude

```bash
sudo systemctl start ichor-briefing-pre_ny.service
journalctl -u ichor-briefing-pre_ny.service -n 100 | grep -E "llm_provider|elapsed_ms"
```

Should show `llm_provider=claude` and elapsed_ms in the typical range.

## Long-term mitigation

If RUNBOOK-013 fires more than once a quarter, options:

1. **Reduce Couche-2 cadence** — drop Sentiment + Positioning to every 12h
   (currently 6h per [`SPEC.md §3.2`](../../SPEC.md)).
2. **Defer counterfactual Pass 5 to off-peak** — only allow it outside
   the 06h/12h/17h/22h cards burst.
3. **Move 1 agent permanently to Cerebras** — pick the lowest-quality-need
   agent (probably Sentiment) and accept a permanent fallback.

Decision pending observation: keep this runbook live and revisit at the
end of Phase 2.

## References

- [`SPEC.md §3.1, §3.2, §3.13, §7`](../../SPEC.md)
- [ADR-009 (Voie D)](../decisions/ADR-009-voie-d-no-api-consumption.md)
- [ADR-021 (Couche-2 via Claude)](../decisions/ADR-021-couche2-via-claude-not-fallback.md)
- [RUNBOOK-008](RUNBOOK-008-anthropic-key-revoked.md) (companion — account ban)
- Anthropic status page: <https://status.anthropic.com>
