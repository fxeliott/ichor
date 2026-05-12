#!/usr/bin/env bash
# Register the nightly Vovk-Zhdanov AA Brier aggregator runner on Hetzner.
#
# W115b — ADR-087 Phase D loop #2 (after W114 ADWIN drift, before W116
# post-mortem PBS). Aggregates expert weights for each `(asset, regime)`
# pocket from the recent `session_card_audit` window and upserts them
# into `brier_aggregator_weights` (W115 migration 0043). Records one
# append-only `auto_improvement_log` row per pocket update
# (loop_kind='brier_aggregator').
#
# Scheduled at 03:30 Europe/Paris :
#   * AFTER the reconciler (02:00) so today's session-window outcomes
#     are persisted on the cards' brier_contribution column.
#   * AFTER the RAG incremental embed (03:00) which doesn't compete for
#     DB resources but keeps the nightly cluster compact.
#   * BEFORE markets reopen (Tokyo around 00:00 UTC = 02:00 Paris is
#     already past, then EUR/Asia overlap starts ~07:00 Paris) — gives
#     downstream readers (confluence_engine W115c, TBD) a fresh pocket
#     weight set.
#   * Wall-time : ~1-3 s per pocket × ~8 pockets = ~10-25 s total.
#
# Smoke verify after install :
#   systemctl list-timers ichor-brier-aggregator.timer --no-pager
#   journalctl -u ichor-brier-aggregator.service --since today --no-pager | tail -30
#   psql -d ichor -c "SELECT count(*) FROM brier_aggregator_weights;"
#   psql -d ichor -c "SELECT count(*) FROM auto_improvement_log WHERE loop_kind='brier_aggregator' AND ran_at > now() - interval '1 day';"
#
# ADR-087 invariants this timer respects :
#   * brier_aggregator_weights is MUTABLE by design (Vovk updates every
#     step) — the audit trail lives in auto_improvement_log (immutable
#     trigger from W113 migration 0042).
#   * pocket_version=1 is hard-pinned in the CLI ; W114 tier-2 sequester
#     workflow will bump this in a future round.
#   * loop_kind='brier_aggregator' is one of the 4 CHECK-constrained
#     values in auto_improvement_log.

set -euo pipefail

# OnFailure drop-in dir must exist BEFORE the heredoc writes to it.
mkdir -p /etc/systemd/system/ichor-brier-aggregator.service.d

cat > /etc/systemd/system/ichor-brier-aggregator.service <<'EOF'
[Unit]
Description=Ichor Vovk-AA Brier aggregator (W115b ADR-087 Phase D loop)
After=network-online.target postgresql.service ichor-reconciler.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api/src
EnvironmentFile=/etc/ichor/api.env
# Default --window 200 covers ~25-30 d of session cards at 8/day cadence.
# Sliding-window stateless re-feed makes the cron output deterministic
# given the same DB state — matches the W114 ADWIN drift pattern.
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_brier_aggregator
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
# SuccessExitStatus=0 1 — the CLI returns 0 on success including "no
# eligible pockets" (cold-start before any reconciled cards exist) and
# 1 on partial failure. Both are acceptable for the timer ; real errors
# raise and exit non-zero via Python exception path, caught by OnFailure.
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-brier-aggregator.service.d/notify.conf <<'EOF'
[Unit]
# Phase A.4.b — notify on failure (cf ADR-030 + ROADMAP_2026-05-06)
# Idempotent drop-in. Safe to delete: just rm this file + daemon-reload.
OnFailure=ichor-notify@%n.service
EOF

cat > /etc/systemd/system/ichor-brier-aggregator.timer <<'EOF'
[Unit]
Description=Ichor Vovk-AA Brier aggregator trigger (nightly 03:30 Paris)

[Timer]
OnCalendar=*-*-* 03:30:00 Europe/Paris
Unit=ichor-brier-aggregator.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-brier-aggregator.timer

echo "=== Installed Vovk-AA Brier aggregator timer (W115b) ==="
systemctl list-timers ichor-brier-aggregator.timer --no-pager
