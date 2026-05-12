#!/usr/bin/env bash
# Register the weekly post-mortem PBS aggregator on Hetzner.
#
# W116b — ADR-087 Phase D loop #3. Computes Ahmadian PBS (arXiv:2407.17697)
# per `(asset, regime)` pocket over the trailing 30 d window of cards
# with `realized_scenario_bucket NOT NULL` (W105g backfilled). Writes
# ONE append-only `auto_improvement_log` row per pocket
# (loop_kind='post_mortem'). Surfaces pocket-level skill / no-skill
# vs the equal-weight K=7 baseline.
#
# Scheduled at Sunday 18:00 Europe/Paris :
#   * After the NY close on Friday + Asian open Sunday evening, so a
#     full week of session windows have been reconciled.
#   * NO market data churn at this time → safe to run a longer query
#     against `session_card_audit`.
#   * Wall-time : ~2-5 s per pocket × ~8 pockets = ~15-40 s.
#
# Smoke verify after install :
#   systemctl list-timers ichor-post-mortem-pbs.timer --no-pager
#   journalctl -u ichor-post-mortem-pbs.service --since "1 week ago" --no-pager | tail -50
#   psql -d ichor -c "SELECT count(*) FROM auto_improvement_log WHERE loop_kind='post_mortem' AND ran_at > now() - interval '14 days';"
#
# ADR-087 invariants this timer respects :
#   * loop_kind='post_mortem' is one of the 4 CHECK-constrained values.
#   * No mutation of session_card_audit — the aggregator is READ-only on
#     business data, WRITE-only on the audit table.
#   * Addendum promotion to `pass3_addenda` is DEFERRED to W116c (which
#     needs LLM-generated text). This round-20 timer emits aggregates only.

set -euo pipefail

# OnFailure drop-in dir must exist BEFORE the heredoc writes to it.
mkdir -p /etc/systemd/system/ichor-post-mortem-pbs.service.d

cat > /etc/systemd/system/ichor-post-mortem-pbs.service <<'EOF'
[Unit]
Description=Ichor post-mortem PBS aggregator (W116b ADR-087 Phase D)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api/src
EnvironmentFile=/etc/ichor/api.env
# Default --window-days 30 = enough cards per pocket (8/day × 30 = 240
# upper bound) for stable PBS aggregates, short enough to surface
# recent drift.
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_post_mortem_pbs
TimeoutStartSec=900
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-post-mortem-pbs.service.d/notify.conf <<'EOF'
[Unit]
# Phase A.4.b — notify on failure.
OnFailure=ichor-notify@%n.service
EOF

cat > /etc/systemd/system/ichor-post-mortem-pbs.timer <<'EOF'
[Unit]
Description=Ichor post-mortem PBS trigger (weekly Sunday 18:00 Paris)

[Timer]
OnCalendar=Sun *-*-* 18:00:00 Europe/Paris
Unit=ichor-post-mortem-pbs.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-post-mortem-pbs.timer

echo "=== Installed post-mortem PBS timer (W116b) ==="
systemctl list-timers ichor-post-mortem-pbs.timer --no-pager
