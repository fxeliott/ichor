# RUNBOOK-006: Prompt injection detected in Claude output

- **Severity**: P0 (compliance + data integrity at stake)
- **Time to resolve (target)**: immediate (revoke + investigate)

## Trigger

- Briefing markdown contains:
  - URLs/email addresses NOT in the provided context
  - Instructions to "ignore previous instructions" or similar
  - Promotional content (referrals, "subscribe to my newsletter")
  - Personally identifiable information not in source
- Claude output deviates wildly from persona ichor.md (hyperbole, advice)
- Hash mismatch between expected persona and actual response footer

## Immediate actions (first 5 min)

1. **Suppress the briefing immediately**:
   ```bash
   ssh ichor-hetzner
   sudo -u postgres psql -d ichor <<SQL
   UPDATE briefings
   SET status='failed',
       error_message='SUPPRESSED: prompt-injection detected, see incident log'
   WHERE id = '<BRIEFING-ID>';
   SQL
   ```

2. **Push update to dashboard** to clear stale views:
   ```bash
   redis-cli PUBLISH ichor:briefings:invalidate '{"id":"<BRIEFING-ID>"}'
   ```

## Diagnosis

1. **Source attribution**: was the injection in the assembled context?
   ```sql
   SELECT context_markdown FROM briefings WHERE id = '<BRIEFING-ID>';
   ```
   Look for: external URLs, base64 blobs, "ignore" / "system:" / "assistant:"
   tokens. If yes — the upstream collector was compromised.

2. **Find the upstream**: what data went into the context?
   - News headlines (RSS pollers — Reuters / AP / FT)
   - Polymarket events
   - Reddit OAuth (high risk — user-generated)
   - FOMC PDF text

3. **Check Reddit OAuth specifically**: per AUDIT_V3 §risk-table,
   user-generated content is the highest injection risk vector.

## Recovery

1. **If source identified**: temporarily disable that collector
   ```bash
   sudo systemctl stop ichor-collector-reddit  # example
   ```
2. **Sanitize the input** in the collector code:
   - Strip markdown code fences
   - Limit to N words per snippet
   - Escape `<`, `>`, special tokens
   - Filter URLs to a domain whitelist
3. **Re-enable** with fix deployed
4. **Backfill check**: scan recent briefings for similar injections
   ```sql
   SELECT id, briefing_type, triggered_at,
          briefing_markdown ~* '(http|@|ignore previous|disregard|system:)' AS suspicious
   FROM briefings
   WHERE triggered_at > now() - interval '7 days'
   ORDER BY triggered_at DESC;
   ```
5. **File compliance incident**: AI Disclosure Article 50 EU AI Act may
   require disclosure if any user saw the injected briefing

## Hardening (post-incident)

- Add a server-side validator in `apps/api/src/ichor_api/cli/run_briefing.py`
  that runs the briefing markdown through a regex blocklist before
  inserting status='completed'
- Consider adding a Critic pass via Cerebras: "is this briefing free of
  injection markers?" before publish
- Add `ichor_api/safety/injection_filter.py` module with rule-based +
  regex-based detection
