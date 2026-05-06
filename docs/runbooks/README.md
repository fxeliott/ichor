# Operational runbooks

Step-by-step recovery procedures for incidents. Each runbook is
self-contained — assume the on-call (= Eliot) is woken at 3am with adrenaline
and slow brain. Be procedural, list every command, link to dashboards.

## Naming convention

`RUNBOOK-NNN-short-slug.md` — sequential, never reordered.

## Index (2026-05-06 — 13 runbooks, all written)

| ID  | File                                                                 | Trigger                                                |
| --- | -------------------------------------------------------------------- | ------------------------------------------------------ |
| 001 | [Hetzner host down](RUNBOOK-001-hetzner-host-down.md)                | No SSH, no HTTPS — full host outage                    |
| 002 | [SSH key rotation](RUNBOOK-002-ssh-key-rotation.md)                  | SSH key compromise / forced rotation                   |
| 003 | [Postgres corruption](RUNBOOK-003-postgres-corruption.md)            | DB corruption → wal-g restore from R2                  |
| 004 | [R2 bucket inaccessible](RUNBOOK-004-r2-bucket-inaccessible.md)      | Cloudflare R2 EU outage / credentials revoked          |
| 005 | [Polymarket renamed](RUNBOOK-005-polymarket-renamed.md)              | Polymarket Gamma API renamed / breaking change         |
| 006 | [Prompt injection](RUNBOOK-006-prompt-injection.md)                  | Prompt injection detected in Claude / news ingestion   |
| 007 | [Brier degradation](RUNBOOK-007-brier-degradation.md)                | Brier score degradation > 15 % vs prior 14 d           |
| 008 | [Anthropic key revoked](RUNBOOK-008-anthropic-key-revoked.md)        | Anthropic Max 20x suspended / banned                   |
| 009 | [Azure TTS quota](RUNBOOK-009-azure-tts-quota.md)                    | Azure Neural TTS quota exceeded → Piper fallback       |
| 010 | [wal-g restore drill](RUNBOOK-010-walg-restore-drill.md)             | Quarterly DR exercise procedure                        |
| 011 | [Collector stalled](RUNBOOK-011-collector-stalled.md)                | One ingestion source has not written in > N hours      |
| 012 | [CF quick tunnel down](RUNBOOK-012-cf-quick-tunnel-down.md)          | Cloudflare Tunnel `claude-runner.fxmilyapp.com` down   |
| 013 | [Claude Max quota saturated](RUNBOOK-013-claude-max-quota-saturated.md) | Max 20x weekly cap hit — degrade to fallback chain  |

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
