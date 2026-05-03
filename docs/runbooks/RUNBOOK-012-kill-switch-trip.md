# RUNBOOK-012: Kill switch tripped

- **Severity** : P1 (no orders being generated, briefings still produced)
- **Last reviewed** : 2026-05-03
- **Time to resolve (target)** : 5-30 min depending on cause

## Trigger

The Ichor risk engine refuses every trade intent with reason
`Kill switch tripped`. Symptoms :

- Grafana panel "Trades today" stuck at 0 since trip time.
- `journalctl -u ichor-api` shows recurring `kill_switch.tripped` lines.
- Dashboard alerts page may show `RISK_KILL_SWITCH_TRIPPED` (Phase 1+).
- Any paper trading process logs `Kill switch tripped (file=..., env=...). All order generation halted.`

## How a trip can happen

Two mechanisms (OR'd) :

1. **File flag present** at the configured path
   (`/etc/ichor/KILL_SWITCH` by default).
2. **Env var truthy** : `ICHOR_KILL_SWITCH` ∈ {`1`, `true`, `yes`, `on`}.

Once tripped *in a process*, the in-process trip lock makes it stay
tripped until the process restarts — even if the file is removed and
env var unset. This is intentional (defends against flap).

## Step 1 — Confirm the trip + identify cause

```bash
ssh ichor-hetzner '
  echo "--- file flag? ---"
  ls -la /etc/ichor/KILL_SWITCH 2>&1 || echo "(not present)"
  echo "--- env var on running services ---"
  for u in ichor-api ichor-briefing@pre_londres ichor-collector-rss; do
    echo "--- $u ---"
    sudo systemctl show "$u" -p Environment 2>&1 | head -3
  done
  echo "--- recent trip log lines (last 1h) ---"
  journalctl --since "1 hour ago" -t systemd-journald --no-pager | grep -i "kill_switch.tripped" | tail -10
'
```

## Step 2 — Decide whether the trip was warranted

Look at the events that immediately preceded the trip :

| Sign | Likely cause | Next step |
|---|---|---|
| Operator manually `touch`ed the file | Intentional, e.g. before a market-open Eliot wants to think | Resume only after Eliot OK |
| Daily DD crossed 5 % | Bad day, system did its job | Investigate strategy ; do not just clear |
| Env var `ICHOR_KILL_SWITCH=1` in a recent systemd drop-in | Maintenance hold | Resume after maintenance |
| `risk.daily_dd_stop` log followed by file flag | Strategy tripped its own sizing | Investigate strategy + bumped DD ; do not silently clear |
| Bug in a model emitting absurd intents | Code bug | Fix bug, redeploy, then clear |

**Do not clear the trip without understanding the cause.** A trip is
designed to make you stop and think. Repeating the cause without
understanding it is how risk policies fail.

## Step 3 — Recovery

Once the cause is understood and addressed :

```bash
ssh ichor-hetzner '
  echo "--- 3a. remove file flag ---"
  sudo rm -f /etc/ichor/KILL_SWITCH
  echo "--- 3b. clear env on systemd unit drop-ins ---"
  for u in ichor-api; do
    sudo systemctl revert "$u" 2>&1 | head -3
  done
  echo "--- 3c. restart services so the in-process trip lock releases ---"
  sudo systemctl restart ichor-api
  # Briefing + collector services are oneshots — they re-evaluate at
  # next timer fire.
  echo "--- 3d. verify clean ---"
  sudo systemctl is-active ichor-api
  curl -sS http://127.0.0.1:8000/healthz/detailed | python3 -m json.tool | head -8
'
```

## Step 4 — Post-incident

- File a record under `docs/incidents/YYYY-MM-DD-kill-switch.md` :
  - Trip cause
  - Time tripped + time cleared
  - Whether any orders were missed (and the missed-EV estimate if
    paper-tracked)
  - Any policy change made as a result
- If a code bug : tag the fix commit + add a regression test.
- If a strategy bug : update the model card with the failure mode +
  cohort + retraining plan.
- If the trip was due to legitimate market conditions : write down
  what reactivated the system + monitor closely for the next 24 h.

## How to manually trip the switch

For drills or planned downtime :

```bash
ssh ichor-hetzner 'sudo touch /etc/ichor/KILL_SWITCH'
```

Recovery is the same as Step 3 above.

## How to test the switch (drill)

Quarterly :

```bash
ssh ichor-hetzner '
  sudo touch /etc/ichor/KILL_SWITCH
  sleep 5
  curl -sS http://127.0.0.1:8000/healthz/detailed | grep -i risk || true
  # Verify logs show the trip
  journalctl -u ichor-api --since "1 minute ago" -n 5
  sudo rm /etc/ichor/KILL_SWITCH
  sudo systemctl restart ichor-api
'
```

Record the outcome under `docs/dr-tests/YYYY-Qn-kill-switch-drill.md`.

## References

- Risk engine code :
  [`packages/risk/src/ichor_risk/engine.py`](../../packages/risk/src/ichor_risk/engine.py)
- Kill switch code :
  [`packages/risk/src/ichor_risk/kill_switch.py`](../../packages/risk/src/ichor_risk/kill_switch.py)
- Design rationale : [ADR-015](../decisions/ADR-015-risk-engine-kill-switch.md)
- Paper-only contract : [ADR-016](../decisions/ADR-016-paper-only-default.md)
