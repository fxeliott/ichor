# RUNBOOK-011: Collector cron stalled or returning empty

- **Severity** : P3 (degraded context for briefings; not blocking the pipeline)
- **Last reviewed** : 2026-05-03
- **Time to resolve (target)** : 15-30 min

## Trigger

- `/news` page shows no items < 4 h old (normal cadence : new rows every 15 min)
- Grafana panel "Collector lag" exceeds 30 min
- Manual SQL probe :
  ```sql
  SELECT source, max(fetched_at) AS last_fetch
  FROM news_items
  GROUP BY source
  ORDER BY last_fetch ASC;
  ```
- systemd timer "next" timestamp is in the past + service "last result"
  shows `failure`

## Diagnosis

### Step 1 — check timer state

```bash
ssh ichor-hetzner '
  systemctl list-timers --all | grep ichor-collector
  systemctl status ichor-collector-rss.timer
  systemctl status ichor-collector-polymarket.timer
'
```

If timers are inactive : `sudo systemctl enable --now ichor-collector-{rss,polymarket}.timer`.

### Step 2 — look at the last service run logs

```bash
ssh ichor-hetzner '
  journalctl -u "ichor-collector@rss.service" --since "1 hour ago" -n 50
  journalctl -u "ichor-collector@polymarket.service" --since "1 hour ago" -n 50
'
```

Common patterns :

| Log signature | Likely cause | Fix |
|---|---|---|
| `dns lookup error` / `Name or service not known` | DNS hiccup | Re-run; transient |
| `503 Service Unavailable` from a feed | Source's CDN down | Wait, fall back to other feeds |
| `403 Forbidden` from a feed | UA blocked or rate-limited | Tweak `user_agent` in `rss.py`, add backoff |
| `parse_failed: not well-formed XML` | Source serves HTML now (URL changed) | Update / remove the feed entry in `DEFAULT_FEEDS` |
| `polymarket.shape_unexpected slug=<X>` | Slug renamed | Update `WATCHED_SLUGS` (see RUNBOOK-005) |
| `psycopg2.errors.UniqueViolation` | guid_hash collision (very unlikely) | Check `(source, guid_hash, fetched_at)` index — should be NEVER |

### Step 3 — manual dry-run

```bash
ssh ichor-hetzner '
  sudo -u ichor bash -c "
    cd /opt/ichor/api/src && \
    source /opt/ichor/api/.venv/bin/activate && \
    set -a && source /etc/ichor/api.env && set +a && \
    timeout 60 python -m ichor_api.cli.run_collectors all
  "
'
```

This prints what would have been persisted, without touching DB. If the
dry-run shows N items but persistence is empty, the bug is in the
persistence path; if dry-run is also empty, the issue is upstream.

### Step 4 — verify Postgres + TimescaleDB OK

```bash
ssh ichor-hetzner '
  sudo -u postgres psql -d ichor -c "SELECT count(*) FROM news_items WHERE fetched_at > now() - interval '"'"'1 hour'"'"';"
  sudo -u postgres psql -d ichor -c "SELECT * FROM timescaledb_information.hypertables;"
'
```

If the count is 0 over the last hour but timers fire successfully, suspect
silent persistence failure (check `journalctl` for SQLAlchemy traces).

## Recovery

### A. Single source down, others fine — degrade gracefully

Edit `apps/api/src/ichor_api/collectors/rss.py` :

```python
DEFAULT_FEEDS: tuple[FeedSource, ...] = (
    # Comment out the broken one:
    # FeedSource("bbc_business", "...", "news"),
    ...other still-working feeds...
)
```

Commit with body : "Disable <source> feed pending RUNBOOK-011 investigation".
Push, redeploy (manual SCP for now, GitHub Actions auto-deploy when
HETZNER_SSH_PRIVATE_KEY secret is set).

### B. All RSS sources down — backbone outage

Probably DNS or network issue. Check :
```bash
ssh ichor-hetzner 'curl -sI https://www.federalreserve.gov/feeds/press_all.xml -m 5 | head -3'
```

If 200 : code bug, run dry-run with `--verbose` and inspect.
If non-200 : wait 30 min + retry. If still down after 2 h : open RUNBOOK-005
(source rename / unavailable).

### C. Polymarket slug renamed

Per RUNBOOK-005, polymarket frequently renames slugs. Update
`WATCHED_SLUGS` in `polymarket.py` with the new slugs (find them by going
to polymarket.com, search the market, copy slug from URL).

### D. DB write failure

Check disk space + Postgres health :
```bash
ssh ichor-hetzner '
  df -h /var/lib/postgresql
  sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('"'"'ichor'"'"'));"
  sudo -u postgres psql -c "SELECT * FROM pg_stat_activity WHERE state != '"'"'idle'"'"';"
'
```

If disk is full : alert RUNBOOK-001 (Hetzner down imminent) — purge old
chunks via TimescaleDB `drop_chunks`.

## Post-incident

- If a feed is permanently dead, remove it from `DEFAULT_FEEDS` AND record
  the removal date in the file's docstring.
- If a slug renamed, also bump
  `packages/ml/model_cards/...` references if any.
- File a record under `docs/incidents/YYYY-MM-DD-collector-<source>.md` if
  downtime > 1 h or if news context was missing for ≥ 1 briefing.
- Consider adding the failed source to a "watch" alert :
  - Define `COLLECTOR_LAG_HIGH` in `apps/api/src/ichor_api/alerts/catalog.py`
  - Trigger when `max(fetched_at) - now() > 60 min` for any single source
