# RUNBOOK-005: Polymarket API renamed / WebSocket schema changed

- **Severity**: P2 (informational signal degraded; not blocking briefings)
- **Time to resolve (target)**: 30-60 min

## Trigger

- Collector `polymarket_ws` logs JSON parse errors
- Bias signal weights dropping `polymarket` family from contributions
- Polymarket announcement on their dev channel / Twitter

## Diagnosis

```bash
ssh ichor-hetzner
journalctl -u ichor-collector-polymarket --since "1 hour" --no-pager | tail -30
```

Check Polymarket dev docs:
- https://docs.polymarket.com/
- WS endpoint historically: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- REST historically: `https://gamma-api.polymarket.com/`

## Recovery

1. **Identify the breaking change** by manually pinging the new endpoint
   (or wss URL) with a sample subscription
2. Update `apps/api/src/ichor_api/collectors/polymarket.py`:
   - New URL
   - New schema (Pydantic model in `models/polymarket.py`)
3. Bump the polymarket weight in the Bias Aggregator config to 0 temporarily
   (so we don't fire bad signals):
   ```sql
   UPDATE bias_signals SET weights_snapshot = weights_snapshot - 'polymarket'
   WHERE generated_at > now() - interval '24 hours';
   ```
4. Deploy fix; verify with `journalctl` that messages are parsing
5. Re-enable polymarket weight in aggregator
6. Document the schema change in `docs/decisions/ADR-XXX-polymarket-vN.md`

## Post-incident

- If schema changes are frequent, consider switching to Polymarket's
  GraphQL API which is more schema-stable
- Add JSON-schema validation tests in `apps/api/tests/test_polymarket_schema.py`
