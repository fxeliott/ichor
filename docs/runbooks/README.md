# Operational runbooks

Step-by-step recovery procedures for incidents. Each runbook is
self-contained — assume the on-call (= Eliot) is woken at 3am with adrenaline
and slow brain. Be procedural, list every command, link to dashboards.

## Naming convention

`RUNBOOK-NNN-short-slug.md` — sequential, never reordered.

## Index

| ID | Trigger | Status |
|----|---------|--------|
| 001 | Hetzner host down (no SSH, no HTTPS) | ⬜ TBD Phase 0 W2 |
| 002 | SSH key compromise / forced rotation | ⬜ TBD Phase 0 W2 |
| 003 | Postgres corruption / wal-g restore from R2 | ⬜ TBD Phase 0 W2 (after first wal-g basebackup) |
| 004 | Cloudflare R2 bucket inaccessible | ⬜ TBD Phase 0 W2 |
| 005 | Polymarket API renamed / breaking change | ⬜ TBD Phase 1 |
| 006 | Prompt injection detected in Claude output | ⬜ TBD Phase 1 |
| 007 | Brier score degradation > 15% in 7 days | ⬜ TBD Phase 1 (needs predictions_audit table) |
| 008 | Anthropic API key revoked / Max 20x banned | ⬜ TBD Phase 0 W3 (after Voie D vs C decision) |
| 009 | Azure TTS quota exceeded → Piper fallback | ⬜ TBD Phase 0 W4 |
| 010 | Hetzner region outage (NBG1) | ⬜ TBD Phase 1 |
| 011 | LDA.gov migration cutover (post 2026-06-30) | ⬜ TBD before deadline |

## Template

```markdown
# RUNBOOK-NNN: <event title>

- **Severity**: P0 (service down) | P1 (degraded) | P2 (alert only)
- **Last reviewed**: YYYY-MM-DD by <name>
- **Time to resolve (target)**: <minutes>

## Trigger

<How does this incident announce itself? Specific alert ID + dashboard link.>

## Immediate actions (first 5 min)

1. ...
2. ...

## Diagnosis

<Specific commands to run + expected outputs.>

## Recovery

<Step-by-step. Include commands.>

## Post-incident

- Update incident log
- File post-mortem if SEV >= P1
- Update this runbook if a step was missing or wrong
```
